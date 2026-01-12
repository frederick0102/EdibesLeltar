"""
Konfiguráció a leltárkezelő alkalmazáshoz
"""
import os
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
    APP_VERSION = '1.0.0'
    
    # Egyszerű jelszó (production-ben változtasd meg!)
    APP_PASSWORD = os.environ.get('APP_PASSWORD') or 'leltar2024'


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
