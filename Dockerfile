# ── Build stage ───────────────────────────────────────────────
FROM python:3.12-slim AS base

# Sistem paketləri: lxml + Playwright Chromium dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    # Playwright / Chromium dependencies
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

# Playwright Chromium brauzerini yüklə
RUN playwright install chromium --with-deps 2>/dev/null || playwright install chromium

# Mənbə kodunu kopyala
COPY . .

# Non-root istifadəçi
RUN adduser --disabled-password --gecos "" botuser \
    && chown -R botuser:botuser /app
USER botuser

EXPOSE 8000

CMD ["python", "-m", "app.main"]
