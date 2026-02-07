"""
SQLite adatbázis kezelés
"""
import sqlite3
import os
from flask import current_app, g
from datetime import datetime
from werkzeug.security import generate_password_hash


def get_db_connection():
    """Adatbázis kapcsolat létrehozása"""
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE_PATH'],
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=30.0  # Hosszabb timeout a konkurens hozzáféréshez
        )
        g.db.row_factory = sqlite3.Row
        
        # === KRITIKUS BEÁLLÍTÁSOK A RASPBERRY PI STABILITÁSÁHOZ ===
        # WAL (Write-Ahead Logging) mód - biztonságosabb SD kártyán
        g.db.execute("PRAGMA journal_mode = WAL")
        # Szinkron mód - FULL a maximális adatbiztonsághoz
        g.db.execute("PRAGMA synchronous = FULL")
        # Foreign key támogatás engedélyezése
        g.db.execute("PRAGMA foreign_keys = ON")
        # Busy timeout - várakozás zárolásra
        g.db.execute("PRAGMA busy_timeout = 30000")
        
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
    
    # === HELYSZÍNEK TÁBLA (ÚJ - Multi-location támogatás) ===
    db.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location_type TEXT NOT NULL CHECK(location_type IN ('WAREHOUSE', 'CAR', 'VENDING')),
            description TEXT,
            address TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP NULL,
            is_deleted INTEGER DEFAULT 0
        )
    ''')
    
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
    
    # Beállítások tábla
    db.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    
    # Készlet tábla (aktuális mennyiségek) - RÉGI, visszafelé kompatibilitás
    db.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')
    
    # === ÚJ: Helyszín-specifikus készlet tábla ===
    # Ez a központi készletnyilvántartás: Product × Location = Quantity
    db.execute('''
        CREATE TABLE IF NOT EXISTS location_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            location_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            min_stock_level REAL DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (location_id) REFERENCES locations(id),
            UNIQUE(product_id, location_id)
        )
    ''')
    
    # Készletmozgások tábla - KIBŐVÍTVE helyszín támogatással
    db.execute('''
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL,
            quantity_change REAL NOT NULL,
            quantity_before REAL NOT NULL,
            quantity_after REAL NOT NULL,
            location_id INTEGER,
            source_location_id INTEGER,
            target_location_id INTEGER,
            reference_movement_id INTEGER,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (location_id) REFERENCES locations(id),
            FOREIGN KEY (source_location_id) REFERENCES locations(id),
            FOREIGN KEY (target_location_id) REFERENCES locations(id),
            FOREIGN KEY (reference_movement_id) REFERENCES inventory_movements(id)
        )
    ''')
    
    # Migráció: helyszín oszlopok hozzáadása a meglévő inventory_movements táblához
    _migrate_inventory_movements(db)
    
    # Audit log tábla (minden változás követése) - BŐVÍTETT
    db.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id INTEGER,
            action TEXT NOT NULL,
            old_values TEXT,
            new_values TEXT,
            user_id TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Migráció: új oszlopok hozzáadása az audit_log táblához
    _migrate_audit_log(db)
    
    # Alapértelmezett adatok beszúrása (ha még nem léteznek)
    _insert_default_data(db)
    
    # Alapértelmezett helyszínek létrehozása
    _insert_default_locations(db)
    
    # Meglévő készlet migrálása az alapértelmezett raktárba
    _migrate_existing_inventory(db)
    
    db.commit()
    
    # Teardown regisztrálása
    current_app.teardown_appcontext(close_db_connection)


def _migrate_inventory_movements(db):
    """Migráció: helyszín oszlopok hozzáadása a meglévő inventory_movements táblához"""
    columns_to_add = [
        ('location_id', 'INTEGER'),
        ('source_location_id', 'INTEGER'),
        ('target_location_id', 'INTEGER'),
        ('reference_movement_id', 'INTEGER')
    ]
    
    for column_name, column_type in columns_to_add:
        try:
            db.execute(f'ALTER TABLE inventory_movements ADD COLUMN {column_name} {column_type}')
        except sqlite3.OperationalError:
            # Oszlop már létezik
            pass


def _migrate_audit_log(db):
    """Migráció: új oszlopok hozzáadása az audit_log táblához"""
    columns_to_add = [
        ('user_id', 'TEXT'),
        ('ip_address', 'TEXT'),
        ('user_agent', 'TEXT')
    ]
    
    for column_name, column_type in columns_to_add:
        try:
            db.execute(f'ALTER TABLE audit_log ADD COLUMN {column_name} {column_type}')
        except sqlite3.OperationalError:
            # Oszlop már létezik
            pass


def _insert_default_locations(db):
    """Alapértelmezett helyszínek létrehozása"""
    
    # Ellenőrizzük, hogy vannak-e már helyszínek
    existing = db.execute('SELECT COUNT(*) as cnt FROM locations').fetchone()
    if existing['cnt'] > 0:
        return
    
    # Alapértelmezett helyszínek
    default_locations = [
        ('Központi Raktár', 'WAREHOUSE', 'Főraktár a termékek tárolására', None),
        ('Autó #1', 'CAR', 'Szállító jármű automata feltöltéshez', None),
    ]
    
    for name, loc_type, description, address in default_locations:
        db.execute('''
            INSERT INTO locations (name, location_type, description, address)
            VALUES (?, ?, ?, ?)
        ''', (name, loc_type, description, address))
    
    db.commit()


def _migrate_existing_inventory(db):
    """Meglévő készlet migrálása az alapértelmezett raktárba"""
    
    # Alapértelmezett raktár ID lekérdezése
    warehouse = db.execute('''
        SELECT id FROM locations WHERE location_type = 'WAREHOUSE' AND is_deleted = 0 LIMIT 1
    ''').fetchone()
    
    if not warehouse:
        return
    
    warehouse_id = warehouse['id']
    
    # Meglévő készlet a régi inventory táblából
    old_inventory = db.execute('SELECT product_id, quantity FROM inventory').fetchall()
    
    for item in old_inventory:
        # Ellenőrizzük, hogy már migrálva van-e
        existing = db.execute('''
            SELECT id FROM location_inventory 
            WHERE product_id = ? AND location_id = ?
        ''', (item['product_id'], warehouse_id)).fetchone()
        
        if not existing:
            db.execute('''
                INSERT INTO location_inventory (product_id, location_id, quantity)
                VALUES (?, ?, ?)
            ''', (item['product_id'], warehouse_id, item['quantity']))
    
    # Régi mozgásokhoz is beállítjuk a helyszínt
    db.execute('''
        UPDATE inventory_movements 
        SET location_id = ? 
        WHERE location_id IS NULL
    ''', (warehouse_id,))
    
    db.commit()


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
    
    # Alapértelmezett jelszó beállítása ha még nincs (hash-elve)
    existing_password = db.execute('SELECT value FROM settings WHERE key = ?', ('app_password',)).fetchone()
    if not existing_password:
        default_password_hash = generate_password_hash('leltar2024')
        db.execute('INSERT INTO settings (key, value) VALUES (?, ?)', ('app_password', default_password_hash))
    
    db.commit()


def log_audit(table_name, record_id, action, old_values=None, new_values=None):
    """
    Audit log bejegyzés létrehozása
    Automatikusan rögzíti a user_id, IP cím és user agent adatokat
    """
    from flask import request, has_request_context
    from flask_login import current_user
    import json
    
    db = get_db_connection()
    
    # Request kontextus adatok
    user_id = None
    ip_address = None
    user_agent = None
    
    if has_request_context():
        # User ID
        try:
            if current_user and current_user.is_authenticated:
                user_id = current_user.id
        except:
            pass
        
        # IP cím (proxy mögött is)
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address and ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()
        
        # User Agent
        user_agent = request.headers.get('User-Agent', '')[:500]  # Max 500 karakter
    
    # Értékek JSON formátumban
    old_json = None
    new_json = None
    
    if old_values:
        if isinstance(old_values, dict):
            old_json = json.dumps(old_values, ensure_ascii=False, default=str)
        else:
            old_json = str(old_values)
    
    if new_values:
        if isinstance(new_values, dict):
            new_json = json.dumps(new_values, ensure_ascii=False, default=str)
        else:
            new_json = str(new_values)
    
    db.execute('''
        INSERT INTO audit_log (table_name, record_id, action, old_values, new_values, user_id, ip_address, user_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (table_name, record_id, action, old_json, new_json, user_id, ip_address, user_agent))
    db.commit()
