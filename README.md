# tgvkbot
Общайтесь в VK через Telegram бота.

- Бот от разработчика - [@tgvkbot](https://t.me/tgvkbot)

- Канал - [@tg_vk](https://t.me/tg_vk)

- Чат - https://t.me/joinchat/BZq6jwxeTh04qBzilM5x3g


# Простая Установка (Ubuntu)
```bash
git clone https://github.com/Kylmakalle/tgvkbot
cd tgvkbot
./install.sh

Токен Telegram бота: 123456789:AAABBBCCCDDDEEEFFFGGGHHHIIIJJJKKKLL
VK APP ID (можно оставить пустым):
```

Далее потребуется ввести пароль от `sudo` пользователя и Telegram-token, остальные переменные необязательны.

_Установщик поставит Docker и docker-compose, настроит переменные окружения и запустит контейнер для обновлений, а затем поднимет бота с его базой данных._

### Обновление
Бот автоматически обновляется через образ на [dockerhub](https://hub.docker.com/r/kylmakalle/tgvkbot/tags?page=1&ordering=last_updated), где на всякий случай фиксируются версии каждого коммита. 

Стандартный установщик поднимает [watchtower](https://containrrr.dev/watchtower), который раз в час проверяет обновления.


### Ограничение пользователей
Если по каким-то причинам хочется чтобы ботом пользовались исключительно определенные пользователи, то это можно сделать изменив файл конфигурации.
Потребуется прописать параметр в таком виде, где числа - Telegram ID пользователей через запятую.

`ALLOWED_USER_IDS=12345678,001238091`

ID можно узнать командой `/id` в боте или через других ботов/софт.


### Кастомизация
С недавнего времени бот поднимается с помощью готового docker образа. Если нужно сделать какую-то специфичную правку, то бота можно поднять через отдельный файл командой

`docker-compose -f docker-compose.local.yml up`

Все остальные действия (`restart`, `stop`, ...) привязанные к "локальному боту" нужно выполнять с флагом `-f docker-compose.local.yml`

Не забудьте отключить бота из образа командой `docker-compose down`

# Установка в Dokku

Подробнее о деплое через Dokku можно прочитать [здесь](https://dokku.com/docs/deployment/application-deployment/).

На сервере:

```bash
dokku apps:create tgvkbot
dokku postgres:create tgvkbot_db
dokku postgres:link tgvkbot_db tgvkbot

dokku config:set tgvkbot BOT_TOKEN=<tg_token> [VK_APP_ID=<vk_app_id> ALLOWED_USER_IDS=<tg_user_ids,...> MAX_FILE_SIZE=<num> ...]
```

На локальном компьютере/где угодно в папке с репозиторием:

```bash
git remote add dokku dokku@<dokku_host_url>:tgvkbot
git push dokku
```


# Сервисы музыки (Устаревшие)
Ниже прокси для музыки, которые использовали ранее. Сейчас они нерелевантны, но код открыт и в боте есть поддержка кастомных бэкендов музыки.

API - https://github.com/Kylmakalle/thatmusic-api

Token Refresher - https://github.com/Kylmakalle/vk-audio-token/tree/refresh-api


# Лицензия
MIT
