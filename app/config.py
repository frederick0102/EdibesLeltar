"""
Konfiguráció a leltárkezelő alkalmazáshoz
"""
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Verzió generálása: yyyymmdd-hhmmss formátumban
def get_version():
    """Visszaadja a verziószámot a build időpontja alapján"""
    # Ha van VERSION fájl, olvassuk ki onnan
    version_file = os.path.join(BASE_DIR, 'VERSION')
    if os.path.exists(version_file):
        with open(version_file, 'r') as f:
            return f.read().strip()
    # Egyébként a jelenlegi időpont
    return datetime.now().strftime('%Y%m%d-%H%M%S')

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
