from __future__ import annotations

# ============================================================
# Checkin.py — Daily Check-in на task.simplechain.com
#
# ⚠️  ВАЖНО: укажи URL сайта с тасками в переменной TASK_BASE_URL!
#     Пример: TASK_BASE_URL = 'https://task.simplechain.com'
#
# Сброс чек-ина: 00:00:00 UTC (= 03:00 по МСК)
# Очки: 60 pts/день + стрик-бонусы (3/7/14/30/50/60/80 дней)
# Авторизация: EIP-191 подпись nonce-сообщения → JWT Bearer token
# ============================================================

import datetime
import time
from datetime import timedelta

import requests
from eth_account.messages import encode_defunct
from loguru import logger
from web3 import Web3

from config.settings import config
from core.bot import Bot
from utils.inputs import (
    cell_date_to_txt, cell_value_to_txt,
    get_date_from_txt, get_value_from_txt,
    input_pause, input_cycle_amount, input_cycle_pause, start_pause,
)
from utils.logging import init_logger
from utils.utils import (
    get_accounts, random_sleep, get_user_agent,
    prepare_proxy_requests, select_and_shuffle_profiles,
)

# ============================================================
TASK_BASE_URL      = 'https://task.simplechain.com'  # ← УКАЖИ URL САЙТА
COOLDOWN_HOURS     = 23                              # часов кулдауна (сброс в 00:00 UTC = 03:00 МСК)
MAX_RETRIES        = 3                               # число попыток при ошибке
MAX_CHECKINS       = 30                              # максимум чек-инов (0 = без лимита)

VISIT_TASK_ID      = 'TK-202604-DT-0007'            # Visit Official Website (30 pts/день)

FILE_CHECKIN_DATE  = 'checkin_date.txt'              # трекинг: дата последнего чек-ина
FILE_CHECKIN_COUNT = 'checkin_count.txt'             # трекинг: количество чек-инов
# ============================================================


# ---------------------------------------------------------------------------
# Авторизация: nonce → подпись → JWT token
# ---------------------------------------------------------------------------

def _get_nonce(account) -> dict | None:
    """POST /api/v1/get/nonce → {message, nonce}"""
    headers = {
        'Content-Type':     'application/json',
        'User-Agent':       account.user_agent,
        'X-Requested-With': 'XMLHttpRequest',
        'Origin':           TASK_BASE_URL,
        'Referer':          f'{TASK_BASE_URL}/',
    }
    proxies = prepare_proxy_requests(account.proxy)
    try:
        resp = requests.post(
            f'{TASK_BASE_URL}/api/v1/get/nonce',
            json={'address': account.address},
            headers=headers, proxies=proxies, timeout=30,
        )
        data = resp.json()
        if data.get('code') == 0:
            return data.get('data')
        logger.error(f'{account.profile_number} get/nonce — ошибка: {data.get("message")}')
    except requests.exceptions.ConnectionError as e:
        logger.error(f'{account.profile_number} get/nonce — ошибка соединения: {e}')
    except requests.exceptions.Timeout:
        logger.error(f'{account.profile_number} get/nonce — таймаут запроса')
    except Exception as e:
        logger.error(f'{account.profile_number} get/nonce — неизвестная ошибка: {e}')
    return None


def _sign_message(account, message: str) -> str:
    """Подписать сообщение приватным ключом (EIP-191)."""
    w3  = Web3()
    msg = encode_defunct(text=message)
    sig = w3.eth.account.sign_message(msg, private_key=account.private_key)
    return '0x' + sig.signature.hex()


def _login(account, message: str, signature: str) -> str | None:
    """POST /api/v1/login {address, message, signature} → JWT token."""
    headers = {
        'Content-Type':     'application/json',
        'User-Agent':       account.user_agent,
        'X-Requested-With': 'XMLHttpRequest',
        'Origin':           TASK_BASE_URL,
        'Referer':          f'{TASK_BASE_URL}/',
    }
    proxies = prepare_proxy_requests(account.proxy)
    try:
        resp = requests.post(
            f'{TASK_BASE_URL}/api/v1/login',
            json={'address': account.address, 'message': message, 'signature': signature},
            headers=headers, proxies=proxies, timeout=30,
        )
        data = resp.json()
        if data.get('code') == 0:
            token = data.get('data', {}).get('token')
            if token:
                logger.info(f'{account.profile_number} Авторизация успешна')
                return token
        logger.error(f'{account.profile_number} login — ошибка: {data.get("message")} | reason: {data.get("reason")}')
    except requests.exceptions.ConnectionError as e:
        logger.error(f'{account.profile_number} login — ошибка соединения: {e}')
    except requests.exceptions.Timeout:
        logger.error(f'{account.profile_number} login — таймаут запроса')
    except Exception as e:
        logger.error(f'{account.profile_number} login — неизвестная ошибка: {e}')
    return None


def _authenticate(account) -> str | None:
    """Полный цикл авторизации: nonce → подпись → токен."""
    nonce_data = _get_nonce(account)
    if not nonce_data:
        return None
    message = nonce_data.get('message', '')
    if not message:
        logger.error(f'{account.profile_number} Пустое сообщение nonce')
        return None
    random_sleep(1, 2)
    signature = _sign_message(account, message)
    random_sleep(1, 2)
    return _login(account, message, signature)


# ---------------------------------------------------------------------------
# Статус чек-ина
# ---------------------------------------------------------------------------

def _get_checkin_status(account, token: str) -> dict | None:
    """GET /api/v1/campaign/checkin/status → {todayChecked, currentStreak, totalCheckins, ...}"""
    headers = {
        'Content-Type':     'application/json',
        'User-Agent':       account.user_agent,
        'X-Requested-With': 'XMLHttpRequest',
        'Origin':           TASK_BASE_URL,
        'Referer':          f'{TASK_BASE_URL}/',
        'Authorization':    f'Bearer {token}',
    }
    proxies = prepare_proxy_requests(account.proxy)
    try:
        resp = requests.get(
            f'{TASK_BASE_URL}/api/v1/campaign/checkin/status',
            headers=headers, proxies=proxies, timeout=30,
        )
        data = resp.json()
        if data.get('code') == 0:
            return data.get('data')
        if resp.status_code in (401, 403):
            logger.error(f'{account.profile_number} checkin/status — токен истёк')
        else:
            logger.error(f'{account.profile_number} checkin/status — ошибка: {data.get("message")}')
    except Exception as e:
        logger.error(f'{account.profile_number} checkin/status — ошибка: {e}')
    return None


# ---------------------------------------------------------------------------
# Выполнение чек-ина
# ---------------------------------------------------------------------------

def _do_checkin(account, token: str) -> bool:
    """POST /api/v1/campaign/checkin {} → выполнить чек-ин."""
    headers = {
        'Content-Type':     'application/json',
        'User-Agent':       account.user_agent,
        'X-Requested-With': 'XMLHttpRequest',
        'Origin':           TASK_BASE_URL,
        'Referer':          f'{TASK_BASE_URL}/',
        'Authorization':    f'Bearer {token}',
    }
    proxies = prepare_proxy_requests(account.proxy)
    try:
        resp = requests.post(
            f'{TASK_BASE_URL}/api/v1/campaign/checkin',
            json={},
            headers=headers, proxies=proxies, timeout=30,
        )
        data   = resp.json()
        code   = data.get('code')
        msg    = data.get('message', '')
        reason = data.get('reason', '')

        if code == 0:
            return True

        msg_lower    = str(msg).lower()
        reason_lower = str(reason).lower()

        if resp.status_code in (401, 403) or 'unauthorized' in reason_lower:
            logger.error(f'{account.profile_number} campaign/checkin — 401, токен истёк')
        elif 'already' in msg_lower or 'completed' in msg_lower or 'today' in msg_lower:
            logger.warning(f'{account.profile_number} Чек-ин уже выполнен сегодня: {msg}')
        elif resp.status_code == 429:
            logger.error(f'{account.profile_number} campaign/checkin — rate limit (429): {msg}')
        elif resp.status_code >= 500:
            logger.error(f'{account.profile_number} campaign/checkin — серверная ошибка [{resp.status_code}]: {msg}')
        else:
            logger.error(f'{account.profile_number} campaign/checkin — code={code} reason={reason}: {msg}')

    except requests.exceptions.ConnectionError as e:
        logger.error(f'{account.profile_number} campaign/checkin — ошибка соединения: {e}')
    except requests.exceptions.Timeout:
        logger.error(f'{account.profile_number} campaign/checkin — таймаут запроса')
    except Exception as e:
        logger.error(f'{account.profile_number} campaign/checkin — неизвестная ошибка: {e}')
    return False


# ---------------------------------------------------------------------------
# Visit Official Website (30 pts/день)
# ---------------------------------------------------------------------------

def _do_visit_website(account, token: str) -> bool:
    """POST /api/v1/task/complete {taskId: VISIT_TASK_ID} → Visit Official Website."""
    headers = {
        'Content-Type':     'application/json',
        'User-Agent':       account.user_agent,
        'X-Requested-With': 'XMLHttpRequest',
        'Origin':           TASK_BASE_URL,
        'Referer':          f'{TASK_BASE_URL}/',
        'Authorization':    f'Bearer {token}',
    }
    proxies = prepare_proxy_requests(account.proxy)
    try:
        resp = requests.post(
            f'{TASK_BASE_URL}/api/v1/task/complete',
            json={'taskId': VISIT_TASK_ID},
            headers=headers, proxies=proxies, timeout=30,
        )
        data   = resp.json()
        code   = data.get('code')
        msg    = data.get('message', '')
        reason = data.get('reason', '')

        if code == 0:
            logger.success(f'{account.profile_number} Visit Website выполнен (+30 pts) 🌐')
            return True

        msg_lower    = str(msg).lower()
        reason_lower = str(reason).lower()

        if 'already' in msg_lower or 'completed' in msg_lower:
            logger.warning(f'{account.profile_number} Visit Website уже выполнен сегодня')
        elif 'condition' in reason_lower or 'eligib' in reason_lower:
            logger.warning(f'{account.profile_number} Visit Website — условие не выполнено (нужен Twitter+Telegram/Discord): {msg}')
        elif resp.status_code in (401, 403):
            logger.error(f'{account.profile_number} Visit Website — 401, токен истёк')
        else:
            logger.error(f'{account.profile_number} Visit Website — code={code} reason={reason}: {msg}')

    except requests.exceptions.ConnectionError as e:
        logger.error(f'{account.profile_number} Visit Website — ошибка соединения: {e}')
    except requests.exceptions.Timeout:
        logger.error(f'{account.profile_number} Visit Website — таймаут запроса')
    except Exception as e:
        logger.error(f'{account.profile_number} Visit Website — неизвестная ошибка: {e}')
    return False


# ---------------------------------------------------------------------------
# Основная логика чек-ина с ретраями
# ---------------------------------------------------------------------------

def checkin(bot: Bot) -> bool:
    """Авторизация + чек-ин с MAX_RETRIES попытками. Возвращает True при успехе."""
    account = bot.account

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Авторизация
            token = _authenticate(account)
            if not token:
                logger.warning(f'{account.profile_number} Попытка {attempt}/{MAX_RETRIES} — не удалось авторизоваться')
                random_sleep(5, 10)
                continue

            random_sleep(2, 4)

            # Проверяем статус (логируем стрик, пропускаем если уже чек-ин сегодня)
            status = _get_checkin_status(account, token)
            if status:
                streak     = status.get('currentStreak', 0)
                total      = status.get('totalCheckins', 0)
                today_done = status.get('todayChecked', False)
                next_bonus = status.get('nextBonusDay', 0)
                next_pts   = status.get('nextBonusPoints', 0)
                logger.info(
                    f'{account.profile_number} Статус: стрик={streak} дней | '
                    f'всего={total} | следующий бонус через {next_bonus} дней (+{next_pts} pts)'
                )
                if today_done:
                    logger.warning(f'{account.profile_number} API подтвердил: чек-ин уже выполнен сегодня')
                    return False

            random_sleep(2, 4)

            # Выполняем чек-ин
            success = _do_checkin(account, token)
            if success:
                new_status     = _get_checkin_status(account, token)
                total_checkins = new_status.get('totalCheckins', 0) if new_status else 0
                logger.success(
                    f'{account.profile_number} Чек-ин выполнен! '
                    f'Стрик: {new_status.get("currentStreak", 0) if new_status else "?"} дней | '
                    f'Всего: {total_checkins} 🎯'
                )
                if total_checkins:
                    cell_value_to_txt(bot, total_checkins, FILE_CHECKIN_COUNT)

                # Visit Official Website (+30 pts)
                random_sleep(2, 4)
                _do_visit_website(account, token)

                return True

            logger.warning(f'{account.profile_number} Попытка {attempt}/{MAX_RETRIES} — неудача')

        except Exception as e:
            logger.error(f'{account.profile_number} Попытка {attempt}/{MAX_RETRIES} — ошибка: {e}')

        if attempt < MAX_RETRIES:
            random_sleep(5, 15)

    logger.error(f'{account.profile_number} Чек-ин не выполнен после {MAX_RETRIES} попыток')
    return False


# ---------------------------------------------------------------------------
# Фильтр аккаунтов — кулдаун 23 часа (сброс в 00:00 UTC = 03:00 МСК)
# ---------------------------------------------------------------------------

def accounts_filter(accounts) -> list:
    result     = []
    limit_date = datetime.datetime.now() - timedelta(hours=COOLDOWN_HOURS)
    for acc in accounts:
        # Фильтр по лимиту чек-инов
        if MAX_CHECKINS > 0:
            total = get_value_from_txt(acc, FILE_CHECKIN_COUNT) or 0
            if total >= MAX_CHECKINS:
                logger.info(f'{acc.profile_number} Достигнут лимит чек-инов: {total}/{MAX_CHECKINS}, пропускаем')
                continue

        # Фильтр по кулдауну
        last = get_date_from_txt(acc, FILE_CHECKIN_DATE)
        if last and last > limit_date:
            next_run = last + timedelta(hours=COOLDOWN_HOURS)
            logger.info(
                f'{acc.profile_number} Чек-ин уже был {last:%Y-%m-%d %H:%M}, '
                f'следующий после {next_run:%Y-%m-%d %H:%M}'
            )
            continue
        result.append(acc)
    logger.info(f'Отфильтровано {len(result)} аккаунтов для чек-ина!')
    return result


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def worker(account) -> None:
    account.user_agent = get_user_agent()
    with Bot(account) as bot:
        success = checkin(bot)
        if success:
            cell_date_to_txt(bot, FILE_CHECKIN_DATE)
            logger.success(f'Активность завершена! Даты в {FILE_CHECKIN_DATE}, счётчик в {FILE_CHECKIN_COUNT}. 🔥')


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
        time.sleep(delay)

    for cycle in range(cycle_amount):
        active = accounts_filter(accounts)
        if not active:
            logger.warning('Все аккаунты уже сделали чек-ин — кулдаун не истёк!')
            break

        logger.info(f'Активных аккаунтов для чек-ина: {len(active)}')

        for account in active:
            worker(account)
            random_sleep(pause)

        logger.success(f'Цикл {cycle + 1}/{cycle_amount} завершён ✅')
        if cycle < cycle_amount - 1:
            random_sleep(cycle_pause)




if __name__ == '__main__':
    main()
