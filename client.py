import os
import asyncio
import logging
import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient

# --- Загружаем .env ---
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")
TARGET_CHANNEL = int(os.getenv("TARGET_CHANNEL"))
CHAT_IDS = [int(chat_id) for chat_id in os.getenv("CHAT_IDS").split(",")]
KEYWORDS = [kw.strip().lower() for kw in os.getenv("KEYWORDS").split(",")]
SEARCH_INTERVAL = int(os.getenv("SEARCH_INTERVAL", 10))  # минут

# --- Логирование ---
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("logs/client.log"),
        logging.StreamHandler()
    ]
)

# --- Путь до сессии ---
session_path = os.path.join(os.getcwd(), 'sessions', 'keyword_search_session')

# --- Инициализация клиента ---
client = TelegramClient(session_path, API_ID, API_HASH)

# Жёсткий путь для базы
DB_PATH = Path("/app/data/forwarded.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS forwarded_messages (
    chat_id INTEGER,
    msg_hash TEXT,
    PRIMARY KEY (chat_id, msg_hash)
)
""")
conn.commit()

print(f"DB initialized at {DB_PATH.resolve()}")

def normalize_text(text: str) -> str:
    """Нормализация текста: убираем пробелы, в нижний регистр"""
    return " ".join(text.lower().split())

def get_hash(text: str) -> str:
    """SHA256-хэш нормализованного текста"""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()

def is_forwarded(text: str) -> bool:
    """Проверяем, пересылалось ли сообщение"""
    h = get_hash(text)
    cur.execute("SELECT 1 FROM forwarded_messages WHERE msg_hash=?", (h,))
    return cur.fetchone() is not None

def add_forwarded(chat_id: int, text: str):
    """Добавляем новое сообщение в БД"""
    h = get_hash(text)
    cur.execute("INSERT OR IGNORE INTO forwarded_messages (chat_id, msg_hash) VALUES (?, ?)", (chat_id, h))
    conn.commit()

# --- Авторизация ---
async def start_client():
    if not await client.is_user_authorized():
        logging.info("Авторизация клиента...")
        await client.start(phone=PHONE_NUMBER)
        logging.info("Клиент успешно авторизован!")

# --- Пересылка ---
async def forward_to_channel(client, target_channel, message, offset_date=None):
    try:
        target_channel_entity = await client.get_entity(target_channel)

        if message.grouped_id:
            group_messages = []
            async for msg in client.iter_messages(
                message.peer_id,
                reverse=True,
                offset_date=offset_date
            ):
                if msg.grouped_id == message.grouped_id:
                    group_messages.append(msg)
                if len(group_messages) > 0 and msg.grouped_id != message.grouped_id:
                    break

            await client.forward_messages(
                entity=target_channel_entity,
                messages=[msg.id for msg in reversed(group_messages)],
                from_peer=message.peer_id
            )
        else:
            await client.forward_messages(target_channel_entity, message.id, message.peer_id)

        logging.info(f"Сообщение {message.id} переслано в канал {target_channel}.")
    except Exception as e:
        logging.error(f"Ошибка при пересылке: {e}")

# --- Поиск сообщений ---
async def search_messages():
    while True:
        now = datetime.utcnow()
        ten_minutes_ago = now - timedelta(minutes=10)

        for chat_id in CHAT_IDS:
            logging.info(f"Ищем сообщения в чате {chat_id} за последние 10 минут.")
            async for message in client.iter_messages(chat_id, offset_date=ten_minutes_ago, reverse=True):
                if not message.text:
                    continue

                text = message.text.strip()
                if any(kw in text.lower() for kw in KEYWORDS):
                    if is_forwarded(text):
                        logging.info(f"Сообщение {message.id} уже пересылалось, пропускаем.")
                        continue

                    logging.info(f"Новое сообщение в чате {chat_id}: {text[:50]}...")
                    await forward_to_channel(client, TARGET_CHANNEL, message, offset_date=ten_minutes_ago)
                    add_forwarded(chat_id, text)

        logging.info("Завершили цикл проверки, ждем...")
        await asyncio.sleep(SEARCH_INTERVAL * 60)

# --- Основной запуск ---
async def main():
    logging.info("Клиент запущен. Начинаем авторизацию...")
    await start_client()
    logging.info("Клиент авторизован. Начинаем мониторинг сообщений...")
    await search_messages()

with client:
    client.loop.run_until_complete(main())