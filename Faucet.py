from __future__ import annotations

import datetime
import time
from datetime import timedelta

import requests
from loguru import logger

from config import Chains
from config.settings import config
from core.bot import Bot
from utils.inputs import (
    cell_date_to_txt, get_date_from_txt,
    input_pause, input_cycle_amount, input_cycle_pause, start_pause,
)
from utils.logging import init_logger
from utils.utils import get_accounts, random_sleep, get_user_agent, prepare_proxy_requests, select_and_shuffle_profiles

# ============================================================
FAUCET_BASE_URL  = 'https://www.simplechain.com'
CAPTCHA_URL      = f'{FAUCET_BASE_URL}/api/getCaptchaImage'
CLAIM_URL        = f'{FAUCET_BASE_URL}/api/front/walletClaimRecord/save'

COOLDOWN_MINUTES = 1440   # 24 часа
MAX_RETRIES      = 3
FILE_FAUCET_DATE = 'faucet_date.txt'
# ============================================================


# ---------------------------------------------------------------------------
# Получение UUID и картинки капчи
# ---------------------------------------------------------------------------

def _get_captcha_info(account) -> dict | None:
    """
    GET /api/getCaptchaImage
    Ответ: {code: 200, data: {img: "base64...", uuid: "...", captchaOnOff: bool}}
    """
    headers = {
        'User-Agent': account.user_agent,
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'{FAUCET_BASE_URL}/developer/faucet',
    }
    proxies = prepare_proxy_requests(account.proxy)

    try:
        resp = requests.get(CAPTCHA_URL, headers=headers, proxies=proxies, timeout=30)
        data = resp.json()
        if data.get('code') == 200:
            return data.get('data')
        logger.error(f'{account.profile_number} getCaptchaImage — неожиданный ответ: {data}')
    except requests.exceptions.ConnectionError as e:
        logger.error(f'{account.profile_number} getCaptchaImage — ошибка соединения: {e}')
    except requests.exceptions.Timeout:
        logger.error(f'{account.profile_number} getCaptchaImage — таймаут запроса')
    except requests.exceptions.JSONDecodeError as e:
        logger.error(f'{account.profile_number} getCaptchaImage — невалидный JSON: {e}')
    except Exception as e:
        logger.error(f'{account.profile_number} getCaptchaImage — неизвестная ошибка: {e}')

    return None


# ---------------------------------------------------------------------------
# Решение image captcha через 2Captcha (base64)
# ---------------------------------------------------------------------------

def _solve_image_captcha(account, img_base64: str, timeout: int = 120) -> str | None:
    api_key = config.two_captcha_token
    if not api_key:
        logger.error(f'{account.profile_number} TWO_CAPTCHA_TOKEN не задан в .env!')
        return None

    # Убираем data:image/...;base64, если присутствует
    if ',' in img_base64:
        img_base64 = img_base64.split(',', 1)[1]

    headers  = {'User-Agent': account.user_agent}
    proxies  = prepare_proxy_requests(account.proxy)

    # Отправить задачу
    try:
        resp = requests.post(
            'https://2captcha.com/in.php',
            data={'key': api_key, 'method': 'base64', 'body': img_base64, 'json': 1},
            headers=headers,
            proxies=proxies,
            timeout=20,
        )
        result = resp.json()
        if result.get('status') != 1:
            logger.error(f'{account.profile_number} 2Captcha: ошибка отправки задачи: {result}')
            return None
        task_id = result['request']
        logger.info(f'{account.profile_number} 2Captcha задача #{task_id}, ждём решения...')
    except Exception as e:
        logger.error(f'{account.profile_number} 2Captcha: ошибка при отправке задачи: {e}')
        return None

    # Опрос результата
    for _ in range(timeout // 5):
        time.sleep(5)
        try:
            poll = requests.get(
                'https://2captcha.com/res.php',
                params={'key': api_key, 'action': 'get', 'id': task_id, 'json': 1},
                headers=headers,
                proxies=proxies,
                timeout=15,
            ).json()

            if poll.get('status') == 1:
                logger.success(f'{account.profile_number} 2Captcha image captcha решена 🎯')
                return poll['request']

            if poll.get('request') != 'CAPCHA_NOT_READY':
                logger.error(f'{account.profile_number} 2Captcha: ошибка при опросе: {poll}')
                return None
        except Exception as e:
            logger.error(f'{account.profile_number} 2Captcha: ошибка при опросе: {e}')
            return None

    logger.error(f'{account.profile_number} 2Captcha: таймаут ожидания решения')
    return None


# ---------------------------------------------------------------------------
# Фильтр аккаунтов — кулдаун 24 часа
# ---------------------------------------------------------------------------

def accounts_filter(accounts) -> list:
    result = []
    limit_date = datetime.datetime.now() - timedelta(minutes=COOLDOWN_MINUTES)
    for acc in accounts:
        last = get_date_from_txt(acc, FILE_FAUCET_DATE)
        if last and last > limit_date:
            next_run = last + timedelta(minutes=COOLDOWN_MINUTES)
            logger.info(
                f'{acc.profile_number} Фосет уже получен {last:%Y-%m-%d %H:%M}, '
                f'следующий запуск после {next_run:%Y-%m-%d %H:%M}'
            )
            continue
        result.append(acc)
    logger.info(f'Отфильтровано {len(result)} аккаунтов для активности!')
    return result


# ---------------------------------------------------------------------------
# Одна попытка получить фосет
# ---------------------------------------------------------------------------

def _do_claim(bot: Bot) -> bool:
    # Шаг 1: получить UUID и картинку капчи
    random_sleep(1, 3)
    captcha_info = _get_captcha_info(bot.account)
    if captcha_info is None:
        logger.error(f'{bot.account.profile_number} Не удалось получить данные фосета (getCaptchaImage)')
        return False

    uuid         = captcha_info.get('uuid', '')
    captcha_on   = captcha_info.get('captchaOnOff', True)
    img_base64   = captcha_info.get('img', '')

    # Шаг 2: решить капчу если включена
    captcha_code = ''
    if captcha_on:
        if not img_base64:
            logger.error(f'{bot.account.profile_number} Капча включена, но поле img пустое')
            return False
        captcha_code = _solve_image_captcha(bot.account, img_base64)
        if not captcha_code:
            logger.error(f'{bot.account.profile_number} Не удалось решить капчу')
            return False

    # Шаг 3: отправить запрос на клейм
    payload = {
        'walletAddress': bot.account.address,
        'uuid':          uuid,
        'tokenType':     1,
        'claimAmount':   0.1,
        'captchaCode':   captcha_code,
        'network':       'production',
    }
    headers = {
        'Content-Type':    'application/json',
        'User-Agent':      bot.account.user_agent,
        'X-Requested-With': 'XMLHttpRequest',
        'Origin':          FAUCET_BASE_URL,
        'Referer':         f'{FAUCET_BASE_URL}/developer/faucet',
    }
    proxies = prepare_proxy_requests(bot.account.proxy)

    try:
        resp      = requests.post(CLAIM_URL, json=payload, headers=headers, proxies=proxies, timeout=30)
        resp_data = resp.json()

        code = resp_data.get('code')
        msg  = resp_data.get('message', '')

        if resp.status_code == 200 and code == 200:
            logger.success(f'{bot.account.profile_number} Фосет получен: {msg} 🎯')
            return True

        # Известные ошибки — логируем отдельно
        msg_lower = str(msg).lower()
        if '24' in msg_lower or 'cooldown' in msg_lower or 'already' in msg_lower or 'wait' in msg_lower:
            logger.warning(f'{bot.account.profile_number} Кулдаун не истёк: {msg}')
        elif 'captcha' in msg_lower or 'code' in msg_lower:
            logger.error(f'{bot.account.profile_number} Неверная капча: {msg}')
        elif resp.status_code == 429:
            logger.error(f'{bot.account.profile_number} Превышен rate limit (429): {msg}')
        elif resp.status_code >= 500:
            logger.error(f'{bot.account.profile_number} Серверная ошибка [{resp.status_code}]: {msg}')
        elif resp.status_code == 0 or not msg:
            logger.error(f'{bot.account.profile_number} Фосет недоступен [{resp.status_code}]: пустой ответ')
        else:
            logger.error(
                f'{bot.account.profile_number} Ошибка фосета [{resp.status_code}] code={code}: {msg}'
            )

    except requests.exceptions.ConnectionError as e:
        logger.error(f'{bot.account.profile_number} Ошибка соединения с фосетом: {e}')
    except requests.exceptions.Timeout:
        logger.error(f'{bot.account.profile_number} Таймаут запроса к фосету')
    except requests.exceptions.JSONDecodeError as e:
        logger.error(f'{bot.account.profile_number} Невалидный JSON в ответе фосета: {e}')
    except Exception as e:
        logger.error(f'{bot.account.profile_number} Неизвестная ошибка при клейме: {e}')

    return False


# ---------------------------------------------------------------------------
# Клейм с retry (до MAX_RETRIES попыток)
# ---------------------------------------------------------------------------

def claim_faucet(bot: Bot) -> bool:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if _do_claim(bot):
                return True
            logger.warning(
                f'{bot.account.profile_number} Попытка {attempt}/{MAX_RETRIES} — неудача, повтор...'
            )
        except Exception as e:
            logger.error(
                f'{bot.account.profile_number} Попытка {attempt}/{MAX_RETRIES} — ошибка: {e}'
            )
        if attempt < MAX_RETRIES:
            random_sleep(5, 10)

    logger.error(f'{bot.account.profile_number} Фосет не получен после {MAX_RETRIES} попыток')
    return False


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def worker(account) -> None:
    account.user_agent = get_user_agent()  # один UA на весь запуск аккаунта
    with Bot(account, chain=Chains.SRW_TESTNET) as bot:
        success = claim_faucet(bot)
        if success:
            cell_date_to_txt(bot, FILE_FAUCET_DATE)
            logger.success('Фосет завершён 🔥')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    init_logger()
    accounts     = get_accounts()
    accounts     = select_and_shuffle_profiles(accounts)
    pause        = input_pause()
    cycle_amount = input_cycle_amount()
    cycle_pause  = input_cycle_pause()
    delay        = start_pause()

    if delay:
        random_sleep(delay)

    for cycle in range(cycle_amount):
        active = accounts_filter(accounts)
        if not active:
            logger.warning('Все аккаунты уже получили фосет — кулдаун не истёк!')
            if cycle < cycle_amount - 1:
                random_sleep(cycle_pause)
            continue

        logger.info(f'Активных аккаунтов для фосета: {len(active)}')

        for account in active:
            worker(account)
            random_sleep(pause)

        logger.success(f'Цикл {cycle + 1}/{cycle_amount} завершён ✅')
        if cycle < cycle_amount - 1:
            random_sleep(cycle_pause)


if __name__ == '__main__':
    main()
