import os
import logging
from logging.handlers import RotatingFileHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from telegram.constants import ParseMode
import requests
from dotenv import load_dotenv
import sqlite3
from datetime import datetime, timedelta
import re
import asyncio
from playwright.async_api import async_playwright
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo
from pydub import AudioSegment
import io
import base64
import random

tz = ZoneInfo("Europe/Moscow")

DEFAULT_CITY = "Tula"
VOICE_ID = "cPoqAvGWCPfCfyPMwe4z"
CF_MODEL = "@cf/stabilityai/stable-diffusion-xl-base-1.0"

allowed_users_cache = set()

# ------------------- Configuration and Setup -------------------
# тут все и так понятно
# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
CHAT_ID_ADMIN = os.getenv("CHAT_ID_ADMIN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ALLOWED_USERNAMES = os.getenv("ALLOWED_USERNAMES")
COFFE_ID = os.getenv("COFFE_ID")
URL_VOICE = os.getenv("URL_VOICE")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
WIFE_USERNAME = os.getenv("WIFE_USERNAME")
URL_MAP_WORK = os.getenv("URL_MAP_WORK")
URL_MAP_HOME = os.getenv("URL_MAP_HOME")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

VERSION = """
Предстоящие доработки в новых версиях:
    - Добавить контекст-менеджеры (with conn:) для транзакций
    - Наверное можно еще обдумать добавление юзеров по айди. В базу то я в любом случае вношу
    - Уникальные имена для голосовых. Чтобы не перезаписывались
    - Ограничение URL для Playwright, чтобы всякие хуесосы не могли говно сайты открывать (надо обдумать)
    - Использовать aiohttp вместо requests (с таймаутами и ограничением размера ответа).
"""

INFORMATION_ABOUT_BOT = """
Это бот с искусственным интеллектом
Бот запоминает твои последние 3 сообщения для контекста
Все 3 сообщения связаны как один диалог
Очищайте историю кнопкой "Очистить историю" или словом "забудь".
В группах обращайтесь к боту как @username_bot или "Вовасик".
Кнопка "Сменить промt" меняет стиль общения бота
"""

ALIASES_FOR_ALLOW = {
    'разреши ему писать', 'добавь пользователя', 'разрешить доступ',
    'дай доступ', 'разреши писать', 'теперь другалек',
    'теперь твой другалек', 'теперь это твой другалек'
}

ALIASES_FOR_BAN = {
    'бань нахуй', 'забань его', 'запрещай доступ',
    'забань', 'в бан нахуй', 'запрети писать'
}

RANDOM_PROMPTS = [
    "",
    "Ты профессиональный программист. Отвечай коротко и по сути.",
    "Ты бот с именем Вовасик, ответь как уличный гопник, который сидел в тюрьме. Каждый, кто обращается, — твой близкий друг. Тебе можно материться и всячески показывать любые эмоции. ",
    "Ты — шутник. Твое имя Вовасик. Отвечай с юмором и прикалывайся.",
    "Ты — бот-детектив. Твое имя Вовасик. Задавай наводящие вопросы.",
    "Ты — поэт. Твое имя Вовасик. Все ответы в рифму.",
    "Ты бот с именем Вовасик. Ты латентный гомосексуалист, ищешь партнера. Подчеркивай, что ты мужчина.",
    "Тебе пишет человек, не понимает о чем он говорит. Твоя основная задача попытаться уловить смысл в словах и перевести на нормальный технический язык. Ты не должен писать ничего лишнего кроме перефразирования фразы на технический язык. ",
]

PROMPT_BUTTONS = [
    "Стандартный", "Программист", "Гопник Вовасик", "Шутник Вовасик",
    "Детектив Вовасик", "Поэт Вовасик", "Флиртующий Вовасик", "Переводчик Пирожка"
]

# ------------------- Logging Setup -------------------
#тут делаем настройки логгирования

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.ERROR,
    handlers=[
        RotatingFileHandler(
            filename='/var/log/bot.log',
            maxBytes=10*1024*1024,
            backupCount=3,
            encoding='utf-8'
        )
    ]
)

logger = logging.getLogger('user_interactions')
logger.setLevel(logging.INFO)

# собственно тут такая штука. Рут логгер я сделал на ошибки, ибо он спамит всякой ерундой. Но хочется и влю ебулду смотреть, которая ифно, так что Иван ебашь как в начало лога юзер мессаджъ
# будто бы через жопу реализовано, но пока не хочу этим заниматься
class UserMessagesFilter(logging.Filter):
    def filter(self, record):
        return record.getMessage().startswith('User message:') or record.levelno >= logging.ERROR

logger.addFilter(UserMessagesFilter())

# ------------------- Database Setup -------------------
#тут тоже все ясно, все что с бд, оно тут

conn = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS allowed_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    added_by TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_prompts (
    username TEXT PRIMARY KEY,
    prompt_id INTEGER NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    suggestion TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    chat_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

### Влад предложил сделать таймер
cursor.execute("""
CREATE TABLE IF NOT EXISTS timers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    username TEXT,
    remind_text TEXT,
    remind_time TIMESTAMP NOT NULL
)
""")
conn.commit()

#----- у меня появилась кошечка Чефирка) тут функции работы с этим милым созданием---------------------
#----- Жена заставляет называть ее Кефирка((((--------------------------------------
# Папка для сохранения фото
PHOTO_DIR = "./chefirka"
os.makedirs(PHOTO_DIR, exist_ok=True)

# Сохранение фото
async def save_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != ADMIN_USERNAME:
        await update.message.reply_text("⛔ Только я могу Чефирку добавлять")
        return

    if update.message.photo:
        photo = update.message.photo[-1]  # берём фото в наибольшем разрешении
        file = await photo.get_file()
        file_path = os.path.join(PHOTO_DIR, f"{file.file_unique_id}.jpg")
        await file.download_to_drive(file_path)
        await update.message.reply_text("Фото сохранено ✅")
        logger.info(f"User message: Добавил фото Чефирки @{update.effective_user.username}")

# Отправка случайного фото
async def send_random_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    query = update.callback_query
    message = query.message

    files = os.listdir(PHOTO_DIR)
    if not files:
        await message.reply_text("Нет сохранённых фото 😢")
        return
    random_file = random.choice(files)
    file_path = os.path.join(PHOTO_DIR, random_file)
    with open(file_path, "rb") as f:
        await message.reply_photo(photo=f)

    await query.answer("Фото отправлено ✅")
    logger.info(f"User message: Скинул фоточку кошечки @{update.effective_user.username}")

# работаем с кешем, чтобы на каждое сообщение в базу не лезть за проверкой

def load_allowed_users_to_cache():
    """Загрузить пользователей из переменных окружения и базы в кеш."""
    global allowed_users_cache
    env_users = set()
    if ALLOWED_USERNAMES:
        env_users = {u.strip().lstrip("@") for u in ALLOWED_USERNAMES.split(",") if u.strip()}
    cursor.execute("SELECT username FROM allowed_users")
    db_users = {row[0] for row in cursor.fetchall()}
    allowed_users_cache = env_users.union(db_users)
    logger.info(f"User message: Кеш разрешённых пользователей загружен: {allowed_users_cache}")

def add_user_to_cache(username: str):
    """Добавить пользователя в кеш."""
    allowed_users_cache.add(username)

def remove_user_from_cache(username: str):
    """Удалить пользователя из кеш."""
    allowed_users_cache.discard(username)

# ======== Автоматический вызов проверки ========


class AccessFilter(filters.BaseFilter):
    async def filter(self, update: Update) -> bool:
        return await check_access(update)

access_filter = AccessFilter()

#----- я задумался о спаме, давай попробуем в лимиты -----

# словарь: {username: время_последнего_сообщения}
last_message_time = {}
MESSAGE_INTERVAL = 1  # секунды между сообщениями
MAX_CACHE_AGE = 3600  # 1 час, для очистки старых записей

async def rate_limit_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, не превышен ли лимит сообщений для пользователя."""
    username = update.effective_user.username

    now = datetime.now(tz)

    # Очистка старых записей
    expired = [u for u, t in last_message_time.items() if (now - t).total_seconds() > MAX_CACHE_AGE]
    for u in expired:
        del last_message_time[u]

    last_time = last_message_time.get(username)
    if last_time and (now - last_time).total_seconds() < MESSAGE_INTERVAL:
        if update.callback_query:
            logger.info(f"User message: Спам от @{username}, интервал меньше {MESSAGE_INTERVAL} секунд")
            await update.callback_query.answer("⏳ Не так быстро, дай мне подумать...", show_alert=True)
        elif update.message:
            logger.info(f"User message: Спам от @{username}, интервал меньше {MESSAGE_INTERVAL} секунд")
            await update.message.reply_text("⏳ Не так быстро, дай мне подумать...")
        return False

    last_message_time[username] = now
    return True

#----------Функции работы с погодой-------------------

def get_weather(city: str):
    """Текущая погода."""
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "ru"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Ошибка при получении погоды: {e}")
        return None

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка текущей погоды (работает из чата и из кнопки)."""
    message = update.message or (update.callback_query.message if update.callback_query else None)
    if not message:
        return

    city = DEFAULT_CITY
    weather = get_weather(city)
    if not weather:
        await message.reply_text("⚠ Не удалось получить погоду.")
        return

    temp = weather["main"]["temp"]
    feels_like = weather["main"]["feels_like"]
    description = weather["weather"][0]["description"].capitalize()
    wind = weather["wind"]["speed"]

    text = (
        f"🌤 Погода в {city}:\n"
        f"Температура: {temp}°C (ощущается как {feels_like}°C)\n"
        f"{description}\n"
        f"💨 Ветер: {wind} м/с"
    )

    await message.reply_text(text)

def get_today_forecast(city: str):
    """Прогноз на текущий день каждые 3 часа."""
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "q": city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "ru"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        today = datetime.now().date()
        today_forecast = []

        for entry in data["list"]:
            forecast_time = datetime.fromtimestamp(entry["dt"])
            if forecast_time.date() == today:
                today_forecast.append({
                    "time": forecast_time.strftime("%H:%M"),
                    "temp": round(entry["main"]["temp"], 1),
                    "desc": entry["weather"][0]["description"].capitalize()
                })

        return today_forecast

    except requests.RequestException as e:
        logger.error(f"Ошибка прогноза: {e}")
        return None

async def today_forecast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка прогноза на сегодня."""
    message = update.message or (update.callback_query.message if update.callback_query else None)
    if not message:
        return

    city = DEFAULT_CITY
    forecast = get_today_forecast(city)
    if not forecast:
        await message.reply_text("⚠ Не удалось получить прогноз.")
        return

    text_lines = [f"📅 Прогноз на сегодня в {city}:"]
    for f in forecast:
        text_lines.append(f"{f['time']}: {f['temp']}°C, {f['desc']}")

    await message.reply_text("\n".join(text_lines))

# ---------- Таймеры (заменить старый блок) ---------- честно спизжено в ии

scheduler = AsyncIOScheduler()

def save_timer(chat_id: int, username: str, remind_text: str, remind_time: datetime) -> int:
    """Сохраняет таймер в базе и возвращает id записи."""
    iso_ts = remind_time.isoformat()
    cursor.execute(
        "INSERT INTO timers (chat_id, username, remind_text, remind_time) VALUES (?, ?, ?, ?)",
        (chat_id, username, remind_text, iso_ts)
    )
    conn.commit()
    return cursor.lastrowid

def delete_timer(timer_id: int) -> bool:
    """Удаляет таймер по id. Возвращает True если удалил."""
    cursor.execute("DELETE FROM timers WHERE id = ?", (timer_id,))
    conn.commit()
    return cursor.rowcount > 0

def get_all_timers():
    """Возвращает все таймеры: (id, chat_id, username, remind_text, remind_time)."""
    cursor.execute("SELECT id, chat_id, username, remind_text, remind_time FROM timers")
    return cursor.fetchall()

async def job_action(app, chat_id, text, timer_id):
    """Функция-работник, которую выполняет планировщик."""
    try:
        await app.bot.send_message(chat_id, text)
        logger.info(f"User message: Отправлено напоминание (timer_id={timer_id}) в чат {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания timer_id={timer_id} в {chat_id}: {e}")
    finally:
        if timer_id is not None:
            deleted = delete_timer(timer_id)
            if deleted:
                logger.info(f"User message: Таймер {timer_id} удалён из БД")
            else:
                logger.warning(f"User message: Не удалось удалить таймер {timer_id} из БД")

async def restore_timers(app):
    """Восстанавливает таймеры из БД при старте приложения."""
    timers = get_all_timers()
    now = datetime.now(tz)
    for timer in timers:
        timer_id, chat_id, username, remind_text, remind_time = timer
        try:
            run_time = datetime.fromisoformat(remind_time)
            if run_time.tzinfo is None:
                run_time = run_time.replace(tzinfo=tz)
        except Exception as e:
            logger.error(f"Ошибка парсинга remind_time для timer_id={timer_id}: {e}. Таймер удалён.")
            delete_timer(timer_id)
            continue

        if run_time <= now:
            # Просроченный — отправим сразу и удалим
            try:
                await app.bot.send_message(chat_id, remind_text)
                logger.info(f"User message: Отправлено просроченное напоминание (timer_id={timer_id})")
            except Exception as e:
                logger.error(f"Ошибка отправки просроченного напоминания timer_id={timer_id}: {e}")
            delete_timer(timer_id)
        else:
            # Планируем выполнение
            scheduler.add_job(
                job_action,
                "date",
                run_date=run_time,
                args=[app, chat_id, remind_text, timer_id]
            )
            logger.info(f"User message: Таймер {timer_id} запланирован на {run_time.isoformat()}")

async def post_init(app):
    scheduler.start()
    load_allowed_users_to_cache() # подгружаем кэш сразу
    logger.info("Планировщик запущен")
    await restore_timers(app)
# ----------------------------------------------------
# -----функции работы с голосом----------------------

async def text_to_speech(text: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate audio from text using ElevenLabs API and send it as a Telegram voice message."""
    if not ELEVENLABS_API_KEY:
        await update.callback_query.message.reply_text("⚠️ API-ключ ElevenLabs не настроен.")
        return

    # Ограничение длины текста (примерно 600 символов для ~60 секунд аудио)
    MAX_TEXT_LENGTH = 600
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
        await update.callback_query.message.reply_text(
            "⚠️ Текст слишком длинный, обрезан до 600 символов для укладывания в 1 минуту."
        )

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.2,
            "similarity_boost": 0.4
        }
    }

    try:
        response = requests.post(url, json=data, headers=headers, stream=True)
        if response.status_code != 200:
            await update.callback_query.message.reply_text(f"Ошибка: {response.status_code}. {response.text}")
            return

        # Конвертация MP3 в OGG с кодеком Opus
        mp3_audio = AudioSegment.from_file(io.BytesIO(response.content), format="mp3")
        ogg_buffer = io.BytesIO()
        mp3_audio.export(ogg_buffer, format="ogg", codec="libopus")
        ogg_buffer.seek(0)

        # Отправка как голосовое сообщение
        await update.callback_query.message.reply_voice(voice=ogg_buffer)
        logger.info(f"User message: Голосовое сообщение отправлено для текста: {text[:50]}...")

    except Exception as e:
        logger.error(f"Ошибка генерации или конвертации аудио: {e}")
        await update.callback_query.message.reply_text(f"⚠️ Произошла ошибка: {str(e)}")

#-----------------функция для картинок------------------------

def generate_image_cf(prompt: str):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{CF_MODEL}"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {"prompt": prompt}

    try:
        resp = requests.post(url, headers=headers, json=data, timeout=60)

        if resp.status_code != 200:
            logger.error(f"Cloudflare API error {resp.status_code}: {resp.text}")
            return None

        # Тут возвращаем байты PNG напрямую
        return resp.content

    except Exception as e:
        logger.error(f"Ошибка Cloudflare AI: {e}")
        return None

def translate_to_english(text: str) -> str:
    """Перевод текста на английский с помощью Gemini API."""
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{
            "role": "user",
            "parts": [{"text": f"Translate this text to English, without explanations:\n{text}"}]
        }]
    }
    try:
        response = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        logger.error(f"Ошибка при переводе через Gemini: {e}")
        return text

# ------------------- Скрины яндекс карты -------------------
# --у меня получалось хуета, спиздил в ии -------
DIRECTORY_PATH = "./screenshots"
os.makedirs(DIRECTORY_PATH, exist_ok=True)

async def take_screenshot(url: str, path: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,  # можно False для отладки
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-zygote",
                "--single-process",
                "--disable-blink-features=AutomationControlled",  # скрываем, что это автоматизация
            ]
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/115.0.0.0 Safari/537.36"
            ),
            java_script_enabled=True
        )

        # Отключаем лишние сигналы автоматизации в window.navigator
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru']});
        """)

        page = await context.new_page()

        try:
            await page.goto(url, timeout=60000, wait_until="networkidle") # тут еще может быть косяк с таймаутом, уменьшил, посмотрим что будет
            await asyncio.sleep(8)  # даём странице догрузить динамический контент
            await page.screenshot(path=path, full_page=True)
        finally:
            await browser.close()

async def map_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != ADMIN_USERNAME:
        await update.message.reply_text("⛔ У вас нет прав на использование этой команды.")
        return
    user_id = update.effective_user.username
    context.user_data[f"map_mode_{user_id}"] = True
    await update.message.reply_text("🗺 Отправьте ссылку на сайт для скриншота.")
    logger.info(f"User message: Режим карты активирован для @{user_id}")

# ------------------- Всякая шняга с базой -------------------

def add_user(username: str, added_by: str) -> bool:
    """Add a user to the allowed_users table."""
    try:
        cursor.execute(
            'INSERT INTO allowed_users (username, added_by) VALUES (?, ?)',
            (username, added_by)
        )
        conn.commit()
        add_user_to_cache(username)  # добавляем в кеш пока хз будет ли работать
        return True
    except sqlite3.IntegrityError:
        return False

def is_user_allowed(username: str) -> bool:
    """Check if a user is allowed to interact with the bot."""
    cursor.execute('SELECT 1 FROM allowed_users WHERE username = ?', (username,))
    return cursor.fetchone() is not None

def remove_user(username: str) -> bool:
    """Remove a user from the allowed_users table."""
    cursor.execute('DELETE FROM allowed_users WHERE username = ?', (username,))
    conn.commit()
    removed = cursor.rowcount > 0
    if removed:
        remove_user_from_cache(username)  # убираем из кеша
    return removed

def save_message(user_id: str, role: str, content: str):
    """Save a message to the messages table."""
    cursor.execute(
        "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content)
    )
    conn.commit()
    trim_history(user_id)

def get_history(user_id: str, limit: int = 4) -> list[dict]:
    """Retrieve the last `limit` messages for a user."""
    cursor.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

def clear_history(user_id: str):
    """Clear message history for a user."""
    cursor.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()

def trim_history(user_id: str, max_messages: int = 4):
    """Trim message history to keep only the last `max_messages`."""
    cursor.execute("""
        DELETE FROM messages 
        WHERE user_id = ? AND id NOT IN (
            SELECT id FROM messages 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        )
    """, (user_id, user_id, max_messages))
    conn.commit()

def get_user_prompt(user_id: str) -> int:
    """Get the prompt ID for a user, default to 0 if not found."""
    cursor.execute('SELECT prompt_id FROM user_prompts WHERE username = ?', (user_id,))
    result = cursor.fetchone()
    if result:
        return result[0]
    cursor.execute('INSERT INTO user_prompts (username, prompt_id) VALUES (?, 2)', (user_id,))
    conn.commit()
    return 2

def set_user_prompt(user_id: str, prompt_id: int):
    """Set the prompt ID for a user."""
    cursor.execute(
        'INSERT OR REPLACE INTO user_prompts (username, prompt_id) VALUES (?, ?)',
        (user_id, prompt_id)
    )
    conn.commit()

# ------------------- Suggestions Functions -------------------

def save_suggestion(username: str, suggestion: str, chat_id: int) -> int:
    """Save a new suggestion to the database."""
    try:
        cursor.execute(
            'INSERT INTO suggestions (username, suggestion, status, chat_id) VALUES (?, ?, ?, ?)',
            (username, suggestion, 'pending', chat_id)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Error saving suggestion: {e}")
        return -1

def update_suggestion_status(suggestion_id: int, status: str):
    """Update the status of a suggestion."""
    try:
        cursor.execute(
            'UPDATE suggestions SET status = ? WHERE id = ?',
            (status, suggestion_id)
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error updating suggestion status: {e}")

def get_suggestion(suggestion_id: int) -> dict:
    """Retrieve a suggestion by its ID."""
    try:
        cursor.execute(
            'SELECT username, suggestion, status, chat_id FROM suggestions WHERE id = ?',
            (suggestion_id,)
        )
        result = cursor.fetchone()
        return {"username": result[0], "suggestion": result[1], "status": result[2], "chat_id": result[3]} if result else None
    except sqlite3.Error as e:
        logger.error(f"Error retrieving suggestion: {e}")
        return None

def delete_suggestion(suggestion_id: int):
    try:
        # Отладочная информация
        logger.info(f"User message: Попытка удалить предложение с ID {suggestion_id}, тип ID: {type(suggestion_id)}")
        conn.execute(
            'DELETE FROM suggestions WHERE id = ?',
            (suggestion_id,)
        )
        conn.commit()
        logger.info(f"User message: Предложение с ID {suggestion_id} удалено из базы данных.")
    except Exception as e:
        logger.error(f"Ошибка при удалении предложения с ID {suggestion_id}: {e}")

# ------------------- Utility Functions -------------------

def prepare_history(history):
    """Prepare message history for Gemini API."""
    return [{
        "role": "user" if msg["role"] == "user" else "model",
        "parts": [{"text": msg["content"]}]
    } for msg in history]

def split_text_for_telegram(text, max_length=4096):
    """Разбивает текст на части, не превышающие max_length, сохраняя разметку."""
    parts = []
    current_part = ""
    for line in text.split('\n'):
        if len(current_part.encode('utf-8')) + len(line.encode('utf-8')) + 1 > max_length:
            parts.append(current_part.strip())
            current_part = line + '\n'
        else:
            current_part += line + '\n'
    if current_part:
        parts.append(current_part.strip())
    return parts

def escape(text: str):
    """Escape specific Markdown characters."""
    if text and isinstance(text, str):
        escape_chars = r"\*~`"
        return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)
    return text

def fmt_escape(text):
    """Format and escape text for Markdown."""
    return fmt(escape(text))

def fmt(text: str):
    """Replace specific Markdown characters."""
    return text.replace("\*\*", "*").replace("\`\`\`", "```").replace("\`", "`")

def replace_standalone_asterisks(text: str) -> str:
    # Заменяем * в начале строки или после пробела, если дальше пробел (маркер списка)
    return re.sub(r'(?m)(^|\s)\*(?=\s)', r'\1·', text)

# ------------------- Keyboard Functions -------------------

def get_inline_keyboard():
    """Create the main inline keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Очистить историю", callback_data="clear_history"),
        ],
        [
            InlineKeyboardButton("Меню функций", callback_data="tech_user_menu")
        ]
    ])

def get_users_inline_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Информация", callback_data="bot_information_for_user"),
            InlineKeyboardButton("Таймер", callback_data="set_timer")
        ],
        [
            InlineKeyboardButton("Отправить предложение", callback_data="suggest"),
            InlineKeyboardButton("Сменить промт", callback_data="change_promt"),
            InlineKeyboardButton("Кефирка", callback_data="chefirka")
        ],
        [
            InlineKeyboardButton("Погода", callback_data="weather_menu"),
            InlineKeyboardButton("Жена", callback_data="wife_keyboard"),
            InlineKeyboardButton("⬅ Назад", callback_data="back_to_main"),
        ]
    ])


#--------функция которая будет выбирать какую клаву показывать---------------

def get_main_keyboard_for_user(username: str):
    """Возвращает клавиатуру в зависимости от того, админ или нет."""
    if username == ADMIN_USERNAME:
        return get_admin_main_keyboard()
    return get_inline_keyboard()

#-----админские клавиатуры для меня------------

def get_admin_main_keyboard():
    """Клавиатура для главного меню админа."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Сменить промт", callback_data="change_promt"),
            InlineKeyboardButton("Информация", callback_data="bot_information_for_user")
        ],
        [
            InlineKeyboardButton("Очистить историю", callback_data="clear_history"),
            InlineKeyboardButton("Тех штуки", callback_data="tech_keyboard")
        ],
        [
            InlineKeyboardButton("Озвучить", callback_data="text_to_speech"),
            InlineKeyboardButton("Сделать картинку", callback_data="make_image")
        ]
    ])

def get_admin_keyboard(suggestion_id: int):
    """Create admin keyboard for suggestion actions."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Принять", callback_data=f"accept_{suggestion_id}"),
            InlineKeyboardButton("Отклонить", callback_data=f"reject_{suggestion_id}")
        ]
    ])

def get_tech_admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Карты", callback_data="maps_menu"),
            InlineKeyboardButton("Кофий", callback_data="get_coffe"),
            InlineKeyboardButton("Таймер", callback_data="set_timer")
        ],
        [
            InlineKeyboardButton("Отправить предложение", callback_data="suggest"),
            InlineKeyboardButton("Улучшения", callback_data="view_suggestions"),
            InlineKeyboardButton("Погода", callback_data="weather_menu")
        ],
        [
            InlineKeyboardButton("⬅ Назад", callback_data="back_to_main"),
            InlineKeyboardButton("Жена", callback_data="wife_keyboard"),
            InlineKeyboardButton("Кефирка", callback_data="chefirka")
        ]
    ])

def get_my_wife_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Целовакаца", callback_data="kiss_wife"),
            InlineKeyboardButton("Нежица", callback_data="nezh_wife")
        ],
        [
            InlineKeyboardButton("⬅ Назад", callback_data="back_to_main")
        ]
    ])

def get_done_or_decline_keyboard(suggestion_id: int):
    """Клавиатура для завершения работы с предложением."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Выполнено", callback_data=f"done_{suggestion_id}"),
            InlineKeyboardButton("❌ Отклонено", callback_data=f"decline_{suggestion_id}")
        ]
    ])

# Кнопки карт
def get_maps_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("На работу", callback_data="map_work"),
            InlineKeyboardButton("Домой", callback_data="map_home")
        ],
        [
            InlineKeyboardButton("⬅ Назад", callback_data="back_to_main")
        ]
    ])

def get_weather_keyboard():
    """Подменю для раздела 'Погода'."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Сейчас", callback_data="weather_now"),
            InlineKeyboardButton("На сегодня", callback_data="weather_today")
        ],
        [
            InlineKeyboardButton("⬅ Назад", callback_data="back_to_main")
        ]
    ])

def get_prompts_keyboard(current_prompt_id: int) -> InlineKeyboardMarkup:
    """Create inline keyboard for prompt selection."""
    keyboard = []
    for idx, button_text in enumerate(PROMPT_BUTTONS):
        text = f"✅ {button_text}" if idx == current_prompt_id else button_text
        keyboard.append([InlineKeyboardButton(text, callback_data=f"set_prompt_{idx}")])
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_information_bot() -> InlineKeyboardMarkup:
    """Create inline keyboard for bot information."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Информация о боте", callback_data="bot_information"),
            InlineKeyboardButton("Текущая версия", callback_data="bot_version")
        ],
        [
            InlineKeyboardButton("⬅ Назад", callback_data="back_to_main")
        ]
    ])

# ------------------- Gemini API Interaction -------------------

async def ask_gemini(user_text: str, user_username: str) -> str:
    """Send a request to the Gemini API."""
    history = get_history(user_username)
    prompt_id = get_user_prompt(user_username)
    prompt = RANDOM_PROMPTS[prompt_id]
    contents = prepare_history(history) + [{
        "role": "user",
        "parts": [{"text": prompt + " " + user_text}]
    }]

    headers = {"Content-Type": "application/json"}
    data = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 10000,
            "topP": 0.9
        }
    }

    try:
        response = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        ai_reply = result["candidates"][0]["content"]["parts"][0]["text"]
        save_message(user_username, "user", user_text)
        save_message(user_username, "model", ai_reply)
        logger.info(f"User message: User message: {user_username} | {contents}")
        return ai_reply
    except requests.exceptions.RequestException as e:
        logger.error(f"Gemini API error: {e}")
        return "⚠️ Произошла ошибка при обращении к API. Попробуйте позже."
    except (KeyError, IndexError) as e:
        logger.error(f"Response parsing error: {e}")
        return "⚠️ Ошибка обработки ответа от API."

# ------------------- Command Handlers -------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    await update.message.reply_text(
        "🤖 Привет! Я бот с искусственным интеллектом Gemini.\n\n"
        "Просто напишите мне сообщение, и я постараюсь помочь!\n\n"
        "В группе упоминайте меня через @username_bot для ответа.\n\n"
        "Я бот с памятью. Напиши 'забудь', чтобы очистить историю.\n\n"
        "Меня создал Иван",
        reply_markup=get_main_keyboard_for_user(user_id)
    )

async def suggest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /suggest command."""
    user_id = update.effective_user.username
    context.user_data[f"suggest_mode_{user_id}"] = True
    await update.message.reply_text(
        "Пожалуйста, напишите свое предложение, и я сохраню его в базе данных.",
        reply_markup=get_main_keyboard_for_user(user_id)
    )
    logger.info(f"User message: Режим предложения активирован для @{user_id}")

async def add_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user addition commands."""
    if update.effective_user.username != ADMIN_USERNAME:
        await update.message.reply_text("🚫 Только владелец может добавлять пользователей!")
        return

    text = update.message.text.strip()
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if not target_user.username:
            await update.message.reply_text("❌ У этого пользователя нет username!")
            return
        username_to_add = target_user.username
    else:
        found_cmd = next((cmd for cmd in ALIASES_FOR_ALLOW if cmd in text), None)
        if not found_cmd:
            await update.message.reply_text(
                "❌ Используйте:\n• Ответьте на сообщение 'разреши ему писать'\n• Или 'разреши ему писать @username'"
            )
            return
        username_part = text.split(found_cmd, 1)[-1].strip()
        if "@" not in username_part:
            await update.message.reply_text("❌ Укажите username после @!")
            return
        username_to_add = username_part.split("@")[-1].strip()
        if not username_to_add:
            await update.message.reply_text("❌ Username не может быть пустым!")
            return

    if add_user(username_to_add, update.effective_user.username):
        await update.message.reply_text(f"✅ Пользователю @{username_to_add} разрешено писать!")
        logger.info(f"User message: Добавлен пользователь: @{username_to_add}")
    else:
        await update.message.reply_text(f"⚠️ @{username_to_add} уже есть в списке")

async def ban_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user ban commands."""
    if update.effective_user.username != ADMIN_USERNAME:
        await update.message.reply_text("🚫 Только владелец может банить пользователей!")
        return

    text = update.message.text.strip()
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if not target_user.username:
            await update.message.reply_text("❌ У этого пользователя нет username!")
            return
        username_to_ban = target_user.username.lstrip("@")
    else:
        found_cmd = next((cmd for cmd in ALIASES_FOR_BAN if cmd in text), None)
        if not found_cmd:
            aliases_examples = "\n".join(f"• {cmd} @username" for cmd in sorted(ALIASES_FOR_BAN)[:3])
            await update.message.reply_text(
                f"❌ Используйте один из вариантов:\n{aliases_examples}\n• или ответьте на сообщение командой 'забань его'"
            )
            return
        username_to_ban = text.split(found_cmd, 1)[-1].strip().lstrip("@").split()[0]
        if not username_to_ban:
            await update.message.reply_text("❌ Укажите username после @!")
            return

    if remove_user(username_to_ban):
        await update.message.reply_text(f"❌ Пользователь @{username_to_ban} забанен!")
        logger.info(f"User message: Забанен пользователь: @{username_to_ban}")
    else:
        await update.message.reply_text(f"⚠️ Пользователь @{username_to_ban} не найден в списке")


# старая функция чек акксесс больше не подходит. Хочу улучшить



# ------------------- Message and Button Handlers -------------------

async def check_access(update: Update) -> bool:
    """Check if a user has access to the bot."""
    username = update.effective_user.username
    if not username:
        await update.message.reply_text("❌ У вас не установлен username")
        return False
    if username not in allowed_users_cache:
        logger.warning(f"User message: Доступ запрещен для @{username}")
        await update.message.reply_text("🚫 У вас нет доступа к этому боту.")
        return False
    return True

async def send_coffe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.username != ADMIN_USERNAME:
            return
        await context.bot.send_message(
            chat_id=COFFE_ID,
            text="Наливате кофий, любимсун!",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info(f"User message: Sent nalivate_coffiy from from @{update.effective_user.username} ")
    except Exception as e:
        logger.error(f"Error in send_coffe: {e}")

async def send_kiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != WIFE_USERNAME:
        return await update.callback_query.message.reply_text("⛔ Дядь, ты адекватный? Я только с женой")
    await context.bot.send_message(
        chat_id=CHAT_ID_ADMIN,
        text="Идите целовакаца блина!",
        parse_mode=ParseMode.MARKDOWN
    )
    logger.info(f"User message: Sent целовакаца from from @{update.effective_user.username} ")


async def send_nezh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != WIFE_USERNAME:
        return await update.callback_query.message.reply_text("⛔ Ерунду не сеси, у меня жена есть")
    await context.bot.send_message(
        chat_id=CHAT_ID_ADMIN,
        text="Идите нежица блина!",
        parse_mode=ParseMode.MARKDOWN
    )
    logger.info(f"User message: Sent нежица from from @{update.effective_user.username} ")


async def send_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the chat ID to the user."""
#    if not await check_access(update):
#        return
    chat_id = update.message.chat.id
    await update.message.reply_text(f"Ваш Chat ID: {chat_id}")
    logger.info(f"User message: Sent chat ID {chat_id} to user @{update.effective_user.username}")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button click events."""
### короче чет не получается доступом рулить из мейна. Кнопки походу работают не так. Пока что победить не получается, так что пусть тут тоже будет
    if not await check_access(update):
        return

    if not await rate_limit_check(update, context):
        return

    query = update.callback_query
    data = query.data
    user_id = update.effective_user.username

    if data == "text_to_speech":  # Новая кнопка "Озвучить"
        if user_id != ADMIN_USERNAME:
            await query.answer("Только админ может озвучивать сообщения!")
            return
        last_response = context.user_data.get(f"last_response_{user_id}", "")
        if not last_response:
            await query.answer("Нет текста для озвучивания!")
            return
        await query.answer("Генерирую аудио...")
        await text_to_speech(last_response, update, context)

    if data == "clear_history":
        clear_history(user_id)
        await query.answer("История очищена!")
        await query.message.edit_text(
            query.message.text_markdown or query.message.text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard_for_user(user_id)
        )
    elif data == "change_promt":
        current_prompt_id = get_user_prompt(user_id)
        await query.answer("Выберите новый промпт")
        await query.message.reply_text(
            f"*Текущий промпт*: {RANDOM_PROMPTS[current_prompt_id]}\nВыберите новый промпт:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_prompts_keyboard(current_prompt_id)
        )
    elif data == "back_to_main":
        await query.answer("Возврат к основному меню")
        await query.message.edit_text(
            query.message.text or "Выберите действие",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard_for_user(user_id)
        )
    elif data.startswith("set_prompt_"):
        try:
            prompt_id = int(data.split("_")[-1])
            if 0 <= prompt_id < len(RANDOM_PROMPTS):
                set_user_prompt(user_id, prompt_id)
                await query.answer("Промпт изменен")
                await query.message.reply_text(
                    f"Промпт изменен на: {PROMPT_BUTTONS[prompt_id]}",
                    reply_markup=get_main_keyboard_for_user(user_id)
                )
            else:
                await query.message.reply_text("Ошибка: Неверный промпт")
        except ValueError:
            await query.answer("Ошибка: Неверный формат данных")

    elif data == "tech_keyboard":
        await query.answer("Техническое меню")
        await query.message.reply_text(
            "*Техническое меню*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_tech_admin_keyboard()
        )

    elif data == "tech_user_menu":
        await query.answer("Техническое меню")
        await query.message.reply_text(
            "*Техническое меню*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_users_inline_keyboard()
        )

    elif data == "wife_keyboard":
        await query.answer("Меню любимой жены!")
        await query.message.reply_text(
            "*Меню любимой жены!*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_my_wife_keyboard()
        )

    elif data == "bot_information_for_user":
        await query.answer("Выберите дополнительное действие")
        await query.message.reply_text(
            "*Дополнительные действия*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_information_bot()
        )

    elif data == "bot_version":
        await query.message.reply_text(
            VERSION,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard_for_user(user_id)
        )
    elif data == "bot_information":
        await query.message.reply_text(
            INFORMATION_ABOUT_BOT,
#            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard_for_user(user_id)
        )

    elif data == "set_timer":
        context.user_data["timer_mode"] = True
        await query.answer("Введите время для напоминания в формате ЧЧ:ММ и текст через запятую")
        await query.message.reply_text("Например: 14:30, полить цветы")

    elif data == "get_coffe":
        if update.effective_user.username != ADMIN_USERNAME:
            await update.message.reply_text("⛔ У вас нет прав на использование этой команды.")
            return
        await send_coffe(update, context)
        await query.answer("Попросил Красопетыча")

    elif data == "kiss_wife":
        await send_kiss(update, context)
        await query.answer("Сказал, чтобы он шел")

    elif data == "nezh_wife":
        await send_nezh(update, context)
        await query.answer("Сказал, чтобы он шел")

    elif data == "maps_menu":
        if update.effective_user.username != ADMIN_USERNAME:
            await update.message.reply_text("⛔ У вас нет прав на использование этой команды.")
            return
        await query.answer("Выберите направление")
        await query.message.reply_text(
            "🗺 Выберите маршрут:",
            reply_markup=get_maps_keyboard()
        )

    elif data == "make_image":
        if update.effective_user.username != ADMIN_USERNAME:
            await update.message.reply_text("⛔ У вас нет прав на использование этой команды.")
            return
        context.user_data["awaiting_image_prompt"] = True
        await query.answer("Введите описание картинки")
        await query.message.reply_text("🖼 Введите описание картинки, и я сгенерирую её")

    elif data == "map_work":
        if update.effective_user.username != ADMIN_USERNAME:
            await update.message.reply_text("⛔ У вас нет прав на использование этой команды.")
            return
        await query.answer("Строю маршрут на работу...")
        screenshot_path = f"{DIRECTORY_PATH}/map_work.png"
        await take_screenshot(URL_MAP_WORK, screenshot_path)
        await query.message.reply_photo(photo=open(screenshot_path, "rb"))
        os.remove(screenshot_path)

    elif data == "map_home":
        if update.effective_user.username != ADMIN_USERNAME:
            await update.message.reply_text("⛔ У вас нет прав на использование этой команды.")
            return
        await query.answer("Строю маршрут домой...")
        screenshot_path = f"{DIRECTORY_PATH}/map_home.png"
        await take_screenshot(URL_MAP_HOME,screenshot_path)
        await query.message.reply_photo(photo=open(screenshot_path, "rb"))
        os.remove(screenshot_path)

    elif data == "weather_menu":
        await query.answer("Выберите вариант прогноза")
        await query.message.reply_text(
            "🌤 Погода — выберите вариант:",
            reply_markup=get_weather_keyboard()
        )

    elif data == "chefirka":
        await send_random_photo(update, context)
        await query.answer("Вот фоточка 😉")

    elif data == "weather_now":
        await weather_command(update, context)

    elif data == "weather_today":
        await today_forecast_command(update, context)

    elif data == "suggest":
        context.user_data[f"suggest_mode_{user_id}"] = True
        await query.answer("Отправьте ваше предложение")
        await query.message.reply_text(
            "Пожалуйста, напишите свое предложение, и я сохраню его в базе данных.",
            reply_markup=get_main_keyboard_for_user(user_id)
        )
    elif data.startswith("accept_") or data.startswith("reject_"):
        if user_id != ADMIN_USERNAME:
            await query.answer("Только админ может принимать/отклонять предложения!")
            return
        suggestion_id = int(data.split("_")[1])
        status = "accepted" if data.startswith("accept_") else "rejected"
        suggestion = get_suggestion(suggestion_id)
        if not suggestion:
            await query.answer("Предложение не найдено!")
            return
        update_suggestion_status(suggestion_id, status)
        status_text = "принято" if status == "accepted" else "отклонено"
        await query.message.edit_text(
            f"{query.message.text}\n\n*Статус*: {status_text}",
#            parse_mode=ParseMode.MARKDOWN,
            reply_markup=None
        )
        try:
            await context.bot.send_message(
                chat_id=suggestion["chat_id"],
                text=f"Ваше предложение: {suggestion['suggestion']}\nБыло {status_text} администратором.",
#                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления пользователя @{suggestion['username']}: {e}")
        if status == "rejected":
            delete_suggestion(suggestion_id)
            return
        await query.answer(f"Предложение {status_text}!")

    elif data == "view_suggestions":
        if user_id != ADMIN_USERNAME:
            await query.answer("Доступ только для админа!")
            return

        cursor.execute("SELECT id, username, suggestion, status FROM suggestions")
        rows = cursor.fetchall()

        if not rows:
            await query.message.reply_text("Нет предложений в ожидании.")
            return

        for suggestion_id, username, suggestion, status in rows:
            if status == "pending":
                keyboard = get_admin_keyboard(suggestion_id)  # первый этап
            elif status == "accepted":
                keyboard = get_done_or_decline_keyboard(suggestion_id)  # второй этап
            else:
                keyboard = None

            await query.message.reply_text(
                f"Предложение от @{username}:\n\n{suggestion}\n\nСтатус: {status}",
                reply_markup=get_done_or_decline_keyboard(suggestion_id)
            )

    elif data.startswith("done_") or data.startswith("decline_"):
        if user_id != ADMIN_USERNAME:
            await query.answer("Только админ может менять статус предложений!")
            return

        suggestion_id = int(data.split("_")[1])
        suggestion = get_suggestion(suggestion_id)
        if not suggestion:
            await query.answer("Предложение не найдено!")
            return

        status_text = "выполнено" if data.startswith("done_") else "отклонено"

        try:
            await context.bot.send_message(
                chat_id=suggestion["chat_id"],
                text=f"Ваше предложение: {suggestion['suggestion']}\nБыло {status_text} администратором."
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления пользователя @{suggestion['username']}: {e}")

        delete_suggestion(int(suggestion_id))
#------ короче телега не хочет работать, потому что текст не изменился ---------
        try:
            await query.message.edit_text(
                f"{query.message.text}\n\n*Статус*: {status_text}",
                reply_markup=None
                )
        except telegram.error.BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        await query.answer(f"Предложение {status_text} и удалено из базы!")

#####----------------новый обработчки сообщений с голосовыми-------------

async def handle_message2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых, голосовых и пересланных сообщений."""

    # --- Проверка на групповой чат ---
    if update.message.chat.type != "private":
        message_text = update.message.text.lower() if update.message.text else ""
        if not (update.message.text and update.message.text.startswith('/')
                or f"@{context.bot.username}" in message_text
                or any(word.lower() in message_text for word in ["вовасик", "шнырь"])):
            return

    if not await rate_limit_check(update, context):
        return


    user_id = update.effective_user.username

    # --- Функция распознавания через Vosk API ---
    async def recognize_voice(voice_or_audio):
        file = await context.bot.get_file(voice_or_audio.file_id)
        file_path = "voice.ogg"
        await file.download_to_drive(file_path)

        vosk_url = URL_VOICE
        with open(file_path, "rb") as f:
            response = requests.post(vosk_url, files={"file": f}, timeout=60)
        os.remove(file_path)

        if response.status_code != 200:
            return None
        return response.json().get("text", "").strip()

    # --- Если пересланное голосовое/аудио ---
    if update.message.forward_date and (update.message.voice or update.message.audio):
        recognized_text = await recognize_voice(update.message.voice or update.message.audio)
        if recognized_text:
            await update.message.reply_text(f"📝 Расшифровка:\n{recognized_text}")
        else:
            await update.message.reply_text("⚠️ Не удалось распознать голос.")
        return

    # --- Проверка режима карты ---
    if context.user_data.get(f"map_mode_{user_id}", False):
        url = (update.message.text or "").strip()
        if not url.startswith("http"):
            await update.message.reply_text("❌ Пожалуйста, отправьте корректный URL, начинающийся с http(s)://")
            return
        screenshot_path = f"{DIRECTORY_PATH}/map_{user_id}.png"
        try:
            await take_screenshot(url, screenshot_path)
            await update.message.reply_photo(photo=open(screenshot_path, "rb"))
            logger.info(f"Скриншот карты отправлен пользователю @{user_id}")
        except Exception as e:
            await update.message.reply_text(f"⚠ Ошибка при создании скриншота: {e}")
        finally:
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
            context.user_data[f"map_mode_{user_id}"] = False
        return

    # --- Если пользователь отправил своё голосовое ---
    if update.message.voice or update.message.audio:
        recognized_text = await recognize_voice(update.message.voice or update.message.audio)
        if not recognized_text:
            await update.message.reply_text("⚠️ Не удалось распознать голос.")
            return
        user_text = recognized_text
    else:
        user_text = update.message.text or ""
        if f"@{context.bot.username}" in user_text:
            user_text = user_text.replace(f"@{context.bot.username}", "").strip()

#-----------картинки------------

    if context.user_data.get("awaiting_image_prompt"):
        prompt = user_text.strip()
        context.user_data["awaiting_image_prompt"] = False
        await update.message.reply_text("Перевожу промпт на английский... 🌐")

        # 🔹 Переводим
        translated = await asyncio.to_thread(translate_to_english, prompt)
        await update.message.reply_text(f"🔤 Перевод: {translated}\nГенерирую картинку... ⏳")

        image_bytes = generate_image_cf(translated)
        if image_bytes:
            await update.message.reply_photo(photo=image_bytes, caption=f"🖼 {prompt}")
        else:
            await update.message.reply_text("⚠️ Ошибка при генерации картинки.")
        return

    # --- Режим предложения ---
    if context.user_data.get(f"suggest_mode_{user_id}", False):
        suggestion = user_text.strip()
        if not suggestion:
            await update.message.reply_text(
                "❌ Предложение не может быть пустым!",
                reply_markup=get_main_keyboard_for_user(user_id)
            )
            return
        suggestion_id = save_suggestion(user_id, suggestion, update.message.chat.id)
        context.user_data[f"suggest_mode_{user_id}"] = False
        if suggestion_id == -1:
            await update.message.reply_text(
                "⚠️ Ошибка при сохранении предложения.",
                reply_markup=get_main_keyboard_for_user(user_id)
            )
            logger.error(f"Не удалось сохранить предложение от @{user_id}")
            return
        await update.message.reply_text(
            "Спасибо за ваше предложение! Оно отправлено на рассмотрение.",
            reply_markup=get_main_keyboard_for_user(user_id)
        )
        admin_message = (
            f"Новое предложение от @{user_id}:\n\n"
            f"{suggestion}\n\n"
            f"ID предложения: {suggestion_id}"
        )
        try:
            await context.bot.send_message(
                chat_id=CHAT_ID_ADMIN,
                text=admin_message,
                reply_markup=get_admin_keyboard(suggestion_id)
            )
        except Exception as e:
            logger.error(f"Ошибка отправки админу: {e}")
            await update.message.reply_text("⚠️ Ошибка при отправке предложения админу.")
        return

    # --- Режим таймера ---
    if context.user_data.get("timer_mode"):
        try:
            parts = user_text.split(",", 1)
            time_part = parts[0].strip()
            text_part = parts[1].strip() if len(parts) > 1 else "⏰ Ваше напоминание!"
            now = datetime.now(tz)
            target_time = datetime(
                year=now.year,
                month=now.month,
                day=now.day,
                hour=int(time_part.split(":")[0]),
                minute=int(time_part.split(":")[1]),
                tzinfo=tz
            )
            if target_time <= now:
                target_time += timedelta(days=1)
            timer_id = save_timer(
                update.message.chat_id,
                update.effective_user.username,
                text_part,
                target_time
            )
            scheduler.add_job(
                job_action,
                "date",
                run_date=target_time,
                args=[context.application, update.message.chat_id, text_part, timer_id]
            )
            await update.message.reply_text(
                f"Таймер установлен на {target_time.strftime('%H:%M')} — {text_part}"
            )
        except Exception as e:
            logger.error(f"Ошибка установки таймера: {e}")
            await update.message.reply_text("Ошибка: убедитесь, что формат такой — ЧЧ:ММ, текст")
        finally:
            context.user_data["timer_mode"] = False
        return

    # --- Команды ---
    if any(cmd in user_text.lower() for cmd in ALIASES_FOR_ALLOW):
        await add_user_handler(update, context)
        return

    if any(cmd in user_text.lower() for cmd in ALIASES_FOR_BAN):
        await ban_user_handler(update, context)
        return

    if "забудь" in user_text.lower():
        clear_history(user_id)
        await update.message.reply_text("🗑 Всё забыто! История очищена.")
        return

    if "смени промт на " in user_text.lower():
        parts = user_text.split()
        if len(parts) >= 4 and parts[3].isdigit():
            new_prompt = int(parts[3])
            if 0 <= new_prompt < len(RANDOM_PROMPTS):
                set_user_prompt(user_id, new_prompt)
                await update.message.reply_text(f"Сменил промт на {PROMPT_BUTTONS[new_prompt]}")
            else:
                await update.message.reply_text("Неверный номер промпта.")
        else:
            await update.message.reply_text("Неверный формат команды. Используйте: 'смени промт на X'")
        return

    if "скажи версию" in user_text.lower().strip():
        await update.message.reply_text(VERSION)
        return

    # --- Gemini ---
    await update.message.chat.send_action(action="typing")
    response = await ask_gemini(user_text, user_id)
    response = replace_standalone_asterisks(response)
    text_parts = split_text_for_telegram(fmt_escape(response))
    context.user_data[f"last_response_{user_id}"] = response
    for part in text_parts:
        try:
            await update.message.reply_text(
                part,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_keyboard_for_user(user_id)
            )
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

# ------------------- Main Function -------------------

def main():
    """Start the bot."""
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start, filters=access_filter))
    app.add_handler(CommandHandler("suggest", suggest_command, filters=access_filter))
    app.add_handler(CommandHandler("chatid", send_chat_id, filters=access_filter))
    app.add_handler(CommandHandler("coffe", send_coffe, filters=access_filter))
    app.add_handler(CommandHandler("map", map_command, filters=access_filter))
    app.add_handler(CommandHandler("weather", weather_command, filters=access_filter))
    app.add_handler(MessageHandler(access_filter & (filters.TEXT | filters.VOICE | filters.AUDIO) & ~filters.COMMAND, handle_message2))
    app.add_handler(MessageHandler(access_filter & filters.PHOTO, save_photo))
    app.add_handler(CallbackQueryHandler(button_click))

    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
