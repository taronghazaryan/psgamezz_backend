FROM python:3.11-slim

# Устанавливаем зависимости для сборки пакетов
RUN apt-get update && apt-get install -y \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Устанавливаем django-celery-results, если его нет в requirements.txt
RUN pip install django-celery-results

# Копируем весь проект
COPY . .

# Переменные окружения
ENV PYTHONUNBUFFERED=1

# Команда запуска Django через gunicorn
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]

