
# SimpleChain

- Web https://www.simplechain.com/home
- Twitter https://x.com/SimpleChain_RWA
- Telegram @SimpleChain_Official
- Explorer https://testnet-explorer.simplechain.com/


## ВАЖНО!!! Перед первым запуском софта необходимо:

- убедиться в правильности активации виртуального окружения VENV

- установить библиотеки командой: pip install -r requirements.txt

- расположить файл `accounts.xlsx` должен находиться в папке config/data/...

- расположить файл `.env` должен находиться в папке config/...

## ВАЖНО!!! Все софты в новых проектах постоянно обновляются (бывает, в день по несколько раз)... 
## Поэтому перед запуском того, либо иного софта, всегда необходимо делать обновление "Master > Update Project"!
## Если на момент обновления софта у вас уже запущены активности в нём, то обновление к ним не применится и активности нужно будет перезапустить в PowerShell.



## Старт 15.04.26:

### Перед запуском скриптов установите себе в ADS расширение ChainBox Wallet https://chromewebstore.google.com/detail/chainbox/fafipkjpodjefcmagnidcibkhlgajann

- `WalletSetup.py` — импорт кошельков Chainbox
    - Открывает профиль ADS, импортирует кошелёк по seed-фразе из `accounts.xlsx`
    - Пропускает профили, у которых кошелёк уже создан (`chainbox_status.txt` = SUCCESS)
    - При ошибке — удаляет расширение и повторяет попытку (макс. 2 попытки, пауза 5 мин)


## Обновление 15.04.26:

- `Checkin.py` — Daily Check-in + Visit Official Website на https://task.simplechain.com
    - Ежедневный чек-ин и посещение сайта (для аккаунтов с привязанным Twitter+Telegram/Discord)
    - Сброс в 00:00 UTC (03:00 МСК), кулдаун 23 часа
    - Бонусы за стрик: 3/7/14/30/50/60/80 дней
    - Фильтр: `MAX_CHECKINS = 30` — скрипт пропускает аккаунты, достигшие лимита (0 = без лимита)

- `Faucet.py` — Daily Faucet на https://www.simplechain.com/developer/faucet
    - Ежедневный клейм тестовых токенов (0.1/день), кулдаун 24 часа
    - Решение капчи через 2Captcha (ключ в `.env`)


## Обновление 16.04.26:

- `TwitterConnect.py` — привязка Twitter + выполнение Twitter-заданий на https://task.simplechain.com
    - Привязывает купленный Twitter к кошельку через OAuth 2.0
    - Выполняет активные задания: Follow on X (+300 pts), X Retweet (+150 pts), Reply to tweet (+100 pts)
    - Данные Twitter аккаунтов берутся из `config/data/twitter_accounts.txt`
    - Формат файла: `profile_number:username:password:auth_token:ct0`
    - Пропускает профили, у которых Twitter уже привязан или задание выполнено


## Обновление 18.04.26:

- `Transfers.py` (API) — отправляет SRW на случайные EVM-адреса для наработки on-chain активности
    - запускается только для аккаунтов, у которых есть хотя бы один успешный фосет
    - за один запуск делает 1–5 трансферов, каждый на 1–5% от баланса
    - фильтр на общее количество трансферов: `TRANSFER_FILTER_LIMIT` вверху скрипта (по умолчанию 20, можно менять)