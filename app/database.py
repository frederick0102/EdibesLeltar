"""
SQLite adatbázis kezelés
"""
import sqlite3
import os
from flask import current_app, g
from datetime import datetime


def get_db_connection():
    """Adatbázis kapcsolat létrehozása"""
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE_PATH'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
        # Foreign key támogatás engedélyezése
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db_connection(e=None):
    """Adatbázis kapcsolat lezárása"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def get_db_session():
    """Visszaadja az aktuális adatbázis kapcsolatot"""
    return get_db_connection()


def init_db():
    """Adatbázis inicializálása - táblák létrehozása"""
    db = get_db_connection()
    
    # Termék kategóriák tábla
    db.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP NULL,
            is_deleted INTEGER DEFAULT 0
        )
    ''')
    
    # Mennyiségi egységek tábla
    db.execute('''
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            abbreviation TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP NULL,
            is_deleted INTEGER DEFAULT 0
        )
    ''')
    
    # Termékek tábla (törzsadatok)
    db.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER,
            unit_id INTEGER,
            barcode TEXT UNIQUE,
            description TEXT,
            package_size TEXT,
            min_stock_level REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP NULL,
            is_deleted INTEGER DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES categories(id),
            FOREIGN KEY (unit_id) REFERENCES units(id)
        )
    ''')
    
    # Migráció: package_size hozzáadása ha még nincs
    try:
        db.execute('ALTER TABLE products ADD COLUMN package_size TEXT')
    except:
        pass
    
    # Készlet tábla (aktuális mennyiségek)
    db.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')
    
    # Készletmozgások tábla (minden változás naplózása)
    db.execute('''
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL,
            quantity_change REAL NOT NULL,
            quantity_before REAL NOT NULL,
            quantity_after REAL NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')
    
    # Audit log tábla (minden változás követése)
    db.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            old_values TEXT,
            new_values TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Alapértelmezett adatok beszúrása (ha még nem léteznek)
    _insert_default_data(db)
    
    db.commit()
    
    # Teardown regisztrálása
    current_app.teardown_appcontext(close_db_connection)


def _insert_default_data(db):
    """Alapértelmezett adatok beszúrása"""
    
    # Alapértelmezett kategóriák
    categories = [
        ('Üdítő', 'Üdítőitalok, vizek'),
        ('Szendvics', 'Szendvicsek, bagettek'),
        ('Csoki', 'Csokoládék, édességek'),
        ('Snack', 'Chipek, sós rágcsálnivalók'),
        ('Kávé', 'Kávéitalok, kávékapszulák'),
        ('Egyéb', 'Egyéb termékek')
    ]
    
    for name, desc in categories:
        try:
            db.execute(
                'INSERT OR IGNORE INTO categories (name, description) VALUES (?, ?)',
                (name, desc)
            )
        except sqlite3.IntegrityError:
            pass
    
    # Alapértelmezett mértékegységek
    units = [
        ('Darab', 'db'),
        ('Liter', 'l'),
        ('Milliliter', 'ml'),
        ('Kilogramm', 'kg'),
        ('Gramm', 'g'),
        ('Csomag', 'csomag'),
        ('Doboz', 'doboz'),
        ('Karton', 'karton')
    ]
    
    for name, abbr in units:
        try:
            db.execute(
                'INSERT OR IGNORE INTO units (name, abbreviation) VALUES (?, ?)',
                (name, abbr)
            )
        except sqlite3.IntegrityError:
            pass


def log_audit(table_name, record_id, action, old_values=None, new_values=None):
    """Audit log bejegyzés létrehozása"""
    db = get_db_connection()
    db.execute('''
        INSERT INTO audit_log (table_name, record_id, action, old_values, new_values)
        VALUES (?, ?, ?, ?, ?)
    ''', (table_name, record_id, action, 
          str(old_values) if old_values else None,
          str(new_values) if new_values else None))
    db.commit()
