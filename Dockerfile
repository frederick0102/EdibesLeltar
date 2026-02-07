# Edibes Leltár - Docker Image
# Raspberry Pi kompatibilis (ARM64/ARM32)

FROM python:3.11-slim

# Munkadirectory beállítása
WORKDIR /app

# Rendszer függőségek (SQLite, curl a healthcheck-hez)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python függőségek telepítése
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Alkalmazás másolása
COPY . .

# Verzió fájl generálása (yyyymmdd-hhmmss formátum)
RUN date +%Y%m%d-%H%M%S > VERSION

# Data és backup könyvtárak létrehozása
RUN mkdir -p /app/data /app/backups

# Port
EXPOSE 5000

# Nem-root felhasználó (biztonság)
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Gunicorn WSGI szerverrel futtatás (production)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "wsgi:app"]
