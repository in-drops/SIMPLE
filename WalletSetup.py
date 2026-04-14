import random
import time
import types

from loguru import logger

from core.browser.ads import Ads
from core.browser.chainbox import Chainbox
from models.account import Account
from utils.inputs import (
    cell_value_to_txt, get_value_from_txt,
    input_pause, input_cycle_amount, input_cycle_pause, start_pause,
)
from utils.logging import init_logger
from utils.utils import get_accounts, select_and_shuffle_profiles, random_sleep

# ВАЖНО: перед запуском установить is_browser_run = True в config/settings.py

STATUS_FILE = 'chainbox_status.txt'
MAX_ATTEMPTS = 2
RETRY_WAIT = 300  # 5 минут в секундах


def accounts_filter(accounts: list[Account]) -> list[Account]:
    filter_accounts = []
    for account in accounts:
        status = get_value_from_txt(account=account, filename=STATUS_FILE)
        if status == 'SUCCESS':
            continue
        filter_accounts.append(account)
    logger.info(f'Отфильтровано {len(filter_accounts)} аккаунтов для создания кошельков!')
    return filter_accounts


def worker(account: Account) -> None:
    for attempt in range(MAX_ATTEMPTS):
        ads = None
        chainbox = None
        success = False

        try:
            ads = Ads(account)
            chainbox = Chainbox(ads, account)
            chainbox.import_wallet()

            bot_wrapper = types.SimpleNamespace(account=account)
            cell_value_to_txt(bot_wrapper, 'SUCCESS', STATUS_FILE)
            logger.success(f'Активность завершена! Статусы в {STATUS_FILE}. 🔥')
            success = True

        except Exception as e:
            logger.error(f'{account.profile_number}: Ошибка создания кошелька (попытка {attempt + 1}/{MAX_ATTEMPTS}): {e}')

            if chainbox and ads:
                try:
                    chainbox.remove_extension()
                except Exception as remove_err:
                    logger.warning(f'⚠️ {account.profile_number}: Ошибка удаления расширения: {remove_err}')

        finally:
            if ads:
                try:
                    ads.close_browser()
                except Exception:
                    pass

        if success:
            return

        if attempt < MAX_ATTEMPTS - 1:
            logger.info(f'{account.profile_number}: Ожидание 5 минут перед повторной попуткой...')
            time.sleep(RETRY_WAIT)

    logger.error(f'{account.profile_number}: Не удалось создать кошелёк после {MAX_ATTEMPTS} попыток')


def main():
    from config.settings import config
    config.is_browser_run = True

    init_logger()
    accounts = get_accounts()
    accounts_for_work = select_and_shuffle_profiles(accounts)
    pause = input_pause()
    cycle_amount = input_cycle_amount()
    cycle_pause = input_cycle_pause()
    time.sleep(start_pause())

    for i in range(cycle_amount):
        filter_accounts = accounts_filter(accounts_for_work)
        random.shuffle(filter_accounts)

        for account in filter_accounts:
            worker(account)
            random_sleep(pause)

        logger.success(f'Цикл {i + 1} завершен, обработано {len(filter_accounts)} аккаунтов! ✅')
        logger.info(f'Ожидание перед следующим циклом {cycle_pause / 60:.0f} минут!')
        random_sleep(cycle_pause)




if __name__ == '__main__':
    main()
