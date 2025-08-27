FROM python:3.12-slim

ENV TZ="Europe/Moscow"

WORKDIR /app

# Системные зависимости для Chromium
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    fonts-liberation \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxext6 \
    libx11-6 \
    xvfb \
    build-essential \
    python3-dev
    && rm -rf /var/lib/apt/lists/*

# Копируем только requirements.txt
COPY requirements.txt .

# Ставим зависимости Python (плюс watchdog)
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

# Устанавливаем Chromium после установки Playwright
RUN python -m playwright install --with-deps chromium

# Копируем скрипт запуска с watchdog
COPY dev_runner.py .

# Запускаем через dev_runner
CMD ["python", "dev_runner.py"]
