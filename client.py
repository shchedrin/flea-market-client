from telethon import TelegramClient
import os
import asyncio
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta
from telethon.tl.types import Message

# Загрузка переменных из .env файла
load_dotenv()

# Переменные из .env
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")  # Номер телефона для авторизации
TARGET_CHANNEL = int(os.getenv("TARGET_CHANNEL"))
CHAT_IDS = [int(chat_id) for chat_id in os.getenv("CHAT_IDS").split(",")]
KEYWORDS = [keyword.strip() for keyword in os.getenv("KEYWORDS").split(",")]
SEARCH_INTERVAL = int(os.getenv("SEARCH_INTERVAL", 10))

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("logs/client.log"),
        logging.StreamHandler()
    ]
)

# Путь до сессии
session_path = os.path.join(os.getcwd(), 'sessions', 'keyword_search_session')

# Создаем Telegram клиент с указанным путем сессии
client = TelegramClient(session_path, API_ID, API_HASH)

# Функция для авторизации
async def start_client():
    if not await client.is_user_authorized():
        logging.info("Авторизация клиента...")
        await client.start(phone=PHONE_NUMBER)
        logging.info("Клиент успешно авторизован!")

# Функция пересылки сообщений
async def forward_to_channel(client, target_channel, message, offset_date=None):
    try:
        # Получаем сущность канала по ID
        target_channel_entity = await client.get_entity(target_channel)

        if message.grouped_id:  # Если сообщение принадлежит медиа-группе
            # Собираем все сообщения из группы
            group_messages = []

            async for msg in client.iter_messages(
                message.peer_id,
                reverse=True,
                offset_date=offset_date
            ):
                if msg.grouped_id == message.grouped_id:
                    group_messages.append(msg)
                # Останавливаем, если нашли все сообщения группы
                if len(group_messages) > 0 and msg.grouped_id != message.grouped_id:
                    break
            
            # Пересылаем все сообщения из группы
            await client.forward_messages(
                entity=target_channel_entity,
                messages=[msg.id for msg in reversed(group_messages)],
                from_peer=message.peer_id
            )

        else:
            # Пересылаем одиночное сообщение
            await client.forward_messages(target_channel_entity, message.id, message.peer_id)
        
        logging.info(f"Сообщение переслано в канал {target_channel}.")
    except ValueError as e:
        logging.error(f"Ошибка пересылки сообщения в канал {target_channel}: {e}")
    except Exception as e:
        logging.error(f"Неизвестная ошибка при пересылке сообщения в канал {target_channel}: {e}")

# Функция поиска сообщений
async def search_messages():
    while True:
        now = datetime.utcnow()  # Текущее время в UTC
        ten_minutes_ago = now - timedelta(minutes=10)  # Время 10 минут назад

        for chat_id in CHAT_IDS:
            logging.info(f"Ищем сообщения в чате {chat_id} за последние 10 минут.")
            async for message in client.iter_messages(chat_id, offset_date=ten_minutes_ago, reverse=True):
                if message.text and any(keyword.lower() in message.text.lower() for keyword in KEYWORDS):
                    logging.info(f"Найдено сообщение в чате {chat_id}: {message.text}")
                    await forward_to_channel(client, TARGET_CHANNEL, message, offset_date=ten_minutes_ago)

        logging.info("Завершили цикл проверки, ждем...")
        await asyncio.sleep(SEARCH_INTERVAL * 60)

# Основной запуск
async def main():
    logging.info("Клиент запущен. Начинаем авторизацию...")
    await start_client()
    logging.info("Клиент авторизован. Начинаем мониторинг сообщений...")
    await search_messages()

with client:
    client.loop.run_until_complete(main())