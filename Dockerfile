# Базовый образ Python
FROM python:3.10-slim

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi-dev libssl-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы
COPY requirements.txt requirements.txt
COPY client.py client.py
COPY .env .env

# Создаём папку для базы, чтобы не было проблем с правами
RUN mkdir -p /app/data /app/sessions /app/logs

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Запуск скрипта
CMD ["python", "client.py"]