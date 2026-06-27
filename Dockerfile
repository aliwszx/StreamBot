FROM python:3.12-slim

# System dependencies for lxml / beautifulsoup
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Non-root user for security
RUN adduser --disabled-password --gecos "" botuser
USER botuser

EXPOSE 8000

CMD ["python", "-m", "app.main"]
