FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2, lxml, and Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc build-essential python3-dev \
    # Playwright/Chromium runtime dependencies
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
    fonts-liberation wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright's Chromium browser (only Chromium to keep image small)
RUN playwright install chromium

# Copy application source
COPY . .

# Expose the port (Railway injects $PORT; default 8000 for local)
EXPOSE 8000

# Start server — must bind 0.0.0.0 to be reachable outside the container
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
