FROM python:3.12-slim

# Sistem paketləri
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    wget \
    ca-certificates \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python paketləri
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Mənbə kodunu kopyala
COPY . .

# Non-root user yarat
RUN adduser --disabled-password --gecos "" botuser \
    && chown -R botuser:botuser /app

# botuser kimi Chromium yüklə (path botuser-in home-una düşsün)
USER botuser
ENV PLAYWRIGHT_BROWSERS_PATH=/home/botuser/.cache/ms-playwright
RUN playwright install chromium

EXPOSE 8000

CMD ["python", "-m", "app.main"]
