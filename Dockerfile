FROM python:3.12-slim

# Sistem paketləri (yalnız lazım olanlar — playwright çıxarıldı)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    ca-certificates \
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

USER botuser

EXPOSE 8000

CMD ["python", "-m", "app.main"]
