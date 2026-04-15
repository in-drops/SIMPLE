
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

- `Checkin.py` (API) — Daily Check-in + Visit Official Website на https://task.simplechain.com
    - ВАЖНО!!! Данный скрипт делает Daily Checkin через Апи без подключения Twitter. Хотя, если зайти через браузер, пока Twitter не подключишь, этот Daily Checkin нельзя делать. Поэтому прежде чем запускать скрипт, сначала зарегистрируйтесь по кошельку на сайте по своим рефкам. И потом подвяжите обязательно Twitter.
    - Ежедневный чек-ин и посещение сайта (для аккаунтов с привязанным Twitter+Telegram/Discord)
    - Сброс в 00:00 UTC (03:00 МСК), кулдаун 23 часа
    - Бонусы за стрик: 3/7/14/30/50/60/80 дней
    - Фильтр: `MAX_CHECKINS = 30` — скрипт пропускает аккаунты, достигшие лимита (0 = без лимита)

- `Faucet.py` (API) — Daily Faucet на https://www.simplechain.com/developer/faucet (2captcha)
    - Кран жёстко лагает пока!
    - Ежедневный клейм тестовых токенов (0.1/день), кулдаун 24 часа
    - Решение капчи через 2Captcha (ключ в `.env`)