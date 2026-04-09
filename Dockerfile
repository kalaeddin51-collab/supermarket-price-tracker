FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 and lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc build-essential python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose the port (Koyeb / Railway inject $PORT; default 8000 for local)
EXPOSE 8000

# Start server — must bind 0.0.0.0 to be reachable outside the container
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
