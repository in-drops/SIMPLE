from __future__ import annotations

import math
import random
import secrets

from eth_utils import to_checksum_address
from loguru import logger

from config import Chains
from core.bot import Bot
from core.onchain import Onchain
from models.amount import Amount
from utils.inputs import (
    cell_date_to_txt, get_date_from_txt,
    increase_counter_in_txt, get_value_from_txt,
    input_pause, input_cycle_amount, input_cycle_pause, start_pause,
)
from utils.logging import init_logger
from utils.utils import get_accounts, random_sleep, select_and_shuffle_profiles, get_user_agent

# ============================================================
TRANSFER_COUNT_MIN    = 1
TRANSFER_COUNT_MAX    = 5
TRANSFER_FILTER_LIMIT = 20    # лимит суммарных трансферов за все запуски
GAS_RESERVE           = 0.01  # резерв SRW для газа — при необходимости увеличить
MAX_ERRORS            = 3

FILE_FAUCET_DATE      = 'faucet_date.txt'
FILE_TRANSFERS_COUNT  = 'transfers_count.txt'
FILE_TRANSFERS_DATE   = 'transfers_date.txt'
# ============================================================


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def human_round(amount: float) -> float:
    """Округление до 2–4 значимых цифр — число выглядит как набранное человеком."""
    if amount == 0:
        return 0.0
    magnitude = math.floor(math.log10(abs(amount)))
    sig_digits = random.randint(2, 4)
    decimal_places = sig_digits - magnitude - 1
    decimal_places = max(0, min(decimal_places, 8))
    return round(amount, decimal_places)


def generate_random_evm_address() -> str:
    """Случайный EVM-адрес с EIP-55 checksum."""
    return to_checksum_address('0x' + secrets.token_bytes(20).hex())


def calculate_transfer_amounts(balance: float, count: int) -> list[float]:
    """
    SRW — не ETH. Каждая сумма = 1–5% от оставшегося баланса.
    Итого все трансферы не превышают баланс - GAS_RESERVE.
    """
    available = max(balance - GAS_RESERVE, 0.0)
    if available <= 0:
        return []
    amounts = []
    remaining = available
    for _ in range(count):
        if remaining <= 0:
            break
        pct = random.uniform(0.01, 0.05)
        val = human_round(remaining * pct)
        if val <= 0:
            break
        amounts.append(val)
        remaining -= val
    return amounts


def _has_faucet_success(account) -> bool:
    """
    Возвращает True, если у аккаунта есть хотя бы одна успешная запись фосета.
    get_date_from_txt возвращает datetime(2000, ...) когда записи нет.
    """
    last = get_date_from_txt(account, FILE_FAUCET_DATE)
    return last.year != 2000


# ---------------------------------------------------------------------------
# Фильтр аккаунтов
# ---------------------------------------------------------------------------

def accounts_filter(accounts) -> list:
    result = []
    for acc in accounts:
        # Условие 1: хотя бы один успешный фосет
        if not _has_faucet_success(acc):
            logger.info(
                f'{acc.profile_number} Фосет ещё не выполнялся — трансфер пропускается'
            )
            continue

        # Условие 2: не превышен общий лимит трансферов
        count = get_value_from_txt(acc, FILE_TRANSFERS_COUNT) or 0
        if count >= TRANSFER_FILTER_LIMIT:
            logger.info(
                f'{acc.profile_number} Лимит трансферов ({count}/{TRANSFER_FILTER_LIMIT}), пропускаем'
            )
            continue

        result.append(acc)

    logger.info(f'Активных аккаунтов для трансферов: {len(result)}')
    return result


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def worker(account) -> None:
    account.user_agent = get_user_agent()  # один UA на весь запуск аккаунта

    with Bot(account, chain=Chains.SRW_TESTNET) as bot:
        onchain = Onchain(bot.account, Chains.SRW_TESTNET)
        balance = onchain.get_balance()
        symbol  = Chains.SRW_TESTNET.native_token  # SRW

        logger.info(
            f'{account.profile_number} Баланс: {balance.ether:.6f} {symbol} | '
            f'Газовый резерв: {GAS_RESERVE} {symbol}'
        )

        if balance.ether <= GAS_RESERVE:
            logger.warning(
                f'⚠️ {account.profile_number} Баланс ниже газового резерва ({GAS_RESERVE} {symbol}), пропускаем'
            )
            return

        count   = random.randint(TRANSFER_COUNT_MIN, TRANSFER_COUNT_MAX)
        amounts = calculate_transfer_amounts(balance.ether, count)

        if not amounts:
            logger.warning(
                f'⚠️ {account.profile_number} Недостаточно баланса для трансферов: {balance.ether:.6f} {symbol}'
            )
            return

        logger.info(f'{account.profile_number} Запланировано {len(amounts)} трансферов: {amounts}')

        errors = 0
        for i, amount_val in enumerate(amounts):
            try:
                recipient = generate_random_evm_address()
                amount    = Amount(amount_val, decimals=18)
                tx_hash   = onchain.send_token(to_address=recipient, amount=amount, token=None)

                logger.success(
                    f'{account.profile_number} Трансфер {i + 1}/{len(amounts)}: '
                    f'{amount_val} {symbol} → {recipient[:10]}... | tx: {tx_hash} 🎯'
                )
                increase_counter_in_txt(bot, FILE_TRANSFERS_COUNT)
                cell_date_to_txt(bot, FILE_TRANSFERS_DATE)

            except Exception as e:
                errors += 1
                logger.error(
                    f'{account.profile_number} Ошибка трансфера {i + 1}/{len(amounts)}: {e}'
                )
                if errors >= MAX_ERRORS:
                    logger.warning(
                        f'⚠️ {account.profile_number} Достигнут лимит ошибок ({MAX_ERRORS}), пропускаем аккаунт'
                    )
                    break
                continue

            # Пауза между трансферами (кроме последнего)
            if i < len(amounts) - 1:
                random_sleep(30, 60)

        logger.success(f'{account.profile_number} Активность завершена! Данные в {FILE_TRANSFERS_COUNT} 🔥')


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
            logger.warning('⚠️ Нет аккаунтов для трансферов (нет фосета или достигнут лимит)!')
            break

        for account in active:
            worker(account)
            random_sleep(pause)

        logger.success(f'Цикл {cycle + 1}/{cycle_amount} завершён ✅')
        if cycle < cycle_amount - 1:
            random_sleep(cycle_pause)



if __name__ == '__main__':
    main()
