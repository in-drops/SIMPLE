
# SimpleChain

- Web https://www.simplechain.com/home
- Twitter https://x.com/SimpleChain_RWA
- Telegram `@SimpleChain_Official`
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
