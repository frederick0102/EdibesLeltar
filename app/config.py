"""
Konfiguráció a leltárkezelő alkalmazáshoz
"""
import os
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Budapest időzóna (UTC+1, nyári időszámítás: UTC+2)
BUDAPEST_TZ = timezone(timedelta(hours=1))  # CET (téli)

def get_budapest_time():
    """Visszaadja a jelenlegi budapesti időt"""
    utc_now = datetime.now(timezone.utc)
    # Egyszerű DST logika: március utolsó vasárnap - október utolsó vasárnap
    month = utc_now.month
    if 3 < month < 10:
        # Nyári időszámítás (CEST = UTC+2)
        return utc_now + timedelta(hours=2)
    elif month == 3:
        # Március: utolsó vasárnap után CEST
        last_sunday = 31 - ((5 + 31) % 7)  # Utolsó vasárnap napja
        if utc_now.day >= last_sunday:
            return utc_now + timedelta(hours=2)
        return utc_now + timedelta(hours=1)
    elif month == 10:
        # Október: utolsó vasárnap előtt CEST
        last_sunday = 31 - ((5 + 31 + (utc_now.year % 400)) % 7)
        if utc_now.day < last_sunday:
            return utc_now + timedelta(hours=2)
        return utc_now + timedelta(hours=1)
    else:
        # Téli időszámítás (CET = UTC+1)
        return utc_now + timedelta(hours=1)

# Verzió generálása: yyyymmdd-hhmmss formátumban
def get_version():
    """Visszaadja a verziószámot a build időpontja alapján (budapesti idő)"""
    # Ha van VERSION fájl, olvassuk ki onnan
    version_file = os.path.join(BASE_DIR, 'VERSION')
    if os.path.exists(version_file):
        with open(version_file, 'r') as f:
            return f.read().strip()
    # Egyébként a jelenlegi budapesti időpont
    return get_budapest_time().strftime('%Y%m%d-%H%M%S')

class Config:
    # Alap beállítások
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'edibles-leltar-secret-key-change-in-production'
    
    # Adatbázis
    DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'leltar.db')
    
    # Backup beállítások
    BACKUP_DIR = os.path.join(BASE_DIR, 'backups')
    NETWORK_BACKUP_PATH = os.environ.get('NETWORK_BACKUP_PATH') or None
    BACKUP_INTERVAL_MINUTES = 30  # Automatikus backup időköz
    BACKUP_RETENTION_DAYS = 30    # Backup megőrzési idő
    
    # Session beállítások
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Alkalmazás beállítások
    APP_NAME = 'Edibes Leltár'
    APP_VERSION = get_version()
    
    # Egyszerű jelszó (production-ben változtasd meg!)
    APP_PASSWORD = os.environ.get('APP_PASSWORD') or 'leltar2024'


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
