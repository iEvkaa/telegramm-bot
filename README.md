# Бот Вовасик 🤖

**Вовасик** — это мой личный Telegram-бот с искусственным интеллектом, созданный для общения в группах, полезных задач и немного юмора. Бот работает на бесплатных тарифах API, поэтому иногда генерирует картинки с семью пальцами или странно распознает голос, но это делает его только интереснее! 😄 Бот не публичный — доступ только по разрешению админа. Назови его «Вовасик» в чате, и он откликнется!

---

## Основная идея

Я хотел сделать бота, который можно добавить в Telegram-группы для общения, шуток и полезных функций, используя только бесплатные API. Это эксперимент, поэтому некоторые функции (например, генерация голоса) ограничены токенами и доступны только админу. Бот — мой личный проект, так что тут есть немного души: фотки моей кошки Чефирки (жена зовет её Кефирка 😾) и режимы вроде «Гопник Вовасик».

---

## Функционал

- **Чат с AI**: Общайтесь с ботом через Gemini API. Он помнит последние 3 сообщения для контекста (сброс — по слову «забудь» или кнопке).
- **Погода**: Текущая погода и прогноз на день (по умолчанию — Тула).
- **Таймеры**: Устанавливайте напоминания (например, «14:30, налить кофе»).
- **Голос**: Распознавание голосовых сообщений через Vosk и генерация аудио через ElevenLabs (ограничено 400 символами, только для админа).
- **Генерация картинок**: Создание изображений через Cloudflare AI (иногда пальцы получаются... необычными 😅).
- **Скриншоты сайтов**: Делайте скриншоты любых сайтов или Яндекс.Карт (экспериментальная фича, только для админа).
- **Личные фичи**: Команды вроде «наливате кофий» или «целовакаца» для админа и его жены.
- **Стили общения**: Меняйте промпты — от «Программиста» до «Гопника Вовасика» или «Поэта».
- **Доступ**: Только разрешенные пользователи (@username) могут писать. Админ управляет доступом командами вроде «дай доступ @username» или «забань @username».

> **Примечание**: Генерация голоса и некоторые функции ограничены из-за бесплатных тарифов API. Картинки работают лучше, но все еще в бете.

---

## Требования

- Python 3.12+
- Telegram Bot Token [](https://t.me/BotFather)
- API-ключи:
  - [Gemini API](https://ai.google.dev/) — чат и перевод
  - [OpenWeather API](https://openweathermap.org/) — погода
  - [ElevenLabs API](https://elevenlabs.io/) — голос (платный, ограничено)
  - [Cloudflare AI](https://developers.cloudflare.com/) — картинки
  - Vosk API (или локальный сервер) — распознавание голоса
- Docker (опционально)

---

## Установка

1. **Клонируйте репо**:
   ```bash
   git clone https://github.com/iEvkaa/telegramm-bot.git
   cd telegramm-bot
    ```
2. **Установка зависимостей**:
    ```
    python -m venv venv
    source venv/bin/activate  # На Windows: venv\Scripts\activate
    pip install -r requirements.txt
    python -m playwright install --with-deps chromium
    ```
3. **Настройте .env: Создайте файл .env в корне проекта:**
    ```
    TELEGRAM_BOT_TOKEN=your_telegram_bot_token
    GEMINI_API_KEY=your_gemini_api_key
    OPENWEATHER_API_KEY=your_openweather_api_key
    ELEVENLABS_API_KEY=your_elevenlabs_api_key
    CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id
    CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
    URL_VOICE=your_vosk_api_url
    CHAT_ID_ADMIN=your_admin_chat_id
    ADMIN_USERNAME=@your_admin_username
    ALLOWED_USERNAMES=@user1,@user2
    COFFE_ID=your_coffe_chat_id
    WIFE_USERNAME=@your_wife_username
    URL_MAP_WORK=your_yandex_map_work_url
    URL_MAP_HOME=your_yandex_map_home_url
    ```
5. **Запустите бота**
    python gemini_bot.py



