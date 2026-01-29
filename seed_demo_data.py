#!/usr/bin/env python3
"""
Demo adatok létrehozása az Edibes Leltár alkalmazáshoz.
30 random termék hozzáadása különböző kategóriákban,
készlettel a raktárban és az autóban.
"""

import sqlite3
import random
from datetime import datetime

# Adatbázis elérési út
DB_PATH = 'data/leltar.db'

# Demo termékek listája kategóriánként
DEMO_PRODUCTS = {
    'Üdítő': [
        ('Coca Cola', '0,5 l', '5449000000996'),
        ('Coca Cola Zero', '0,5 l', '5449000131805'),
        ('Fanta Narancs', '0,5 l', '5449000011527'),
        ('Sprite', '0,5 l', '5449000014535'),
        ('Pepsi', '0,5 l', '5998883400018'),
        ('Pepsi Max', '0,5 l', '5998883400025'),
        ('7UP', '0,5 l', '5998883400032'),
        ('Lipton Ice Tea Citrom', '0,5 l', '5449000189653'),
        ('Lipton Ice Tea Barack', '0,5 l', '5449000189660'),
        ('Fuzetea Zöld tea', '0,5 l', '5449000235640'),
    ],
    'Snack': [
        ('Chio Chips Sós', '75 g', '5997312700016'),
        ('Chio Chips Paprikás', '75 g', '5997312700023'),
        ('Pringles Original', '165 g', '5053990101573'),
        ('Pringles Paprika', '165 g', '5053990101580'),
        ('Mogyi Földimogyoró', '170 g', '5997523300017'),
        ('Ropi', '90 g', '5997523300024'),
        ('TUC Kréker', '100 g', '7622210259509'),
        ('Bake Rolls Sajtos', '80 g', '5997312700030'),
    ],
    'Csoki': [
        ('Sport szelet', '30 g', '5998811100015'),
        ('Balaton szelet', '30 g', '5998811100022'),
        ('Túró Rudi', '30 g', '5998811100039'),
        ('Milka Alpesi tej', '100 g', '7622210100016'),
        ('Milka Mogyorós', '100 g', '7622210100023'),
        ('Kinder Bueno', '43 g', '8000500066027'),
        ('Snickers', '50 g', '5000159459228'),
        ('Mars', '51 g', '5000159407236'),
        ('Twix', '50 g', '5000159459242'),
        ('Bounty', '57 g', '5000159484268'),
    ],
    'Kávé': [
        ('Nescafé 3in1', '17,5 g', '7613036549981'),
        ('Nescafé Cappuccino', '13 g', '7613036549998'),
    ],
}

def get_or_create_category(conn, name):
    """Kategória lekérdezése vagy létrehozása"""
    cursor = conn.execute('SELECT id FROM categories WHERE name = ?', (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    
    conn.execute('''
        INSERT INTO categories (name, description, is_deleted, created_at)
        VALUES (?, ?, 0, ?)
    ''', (name, f'{name} kategória', datetime.now()))
    conn.commit()
    return conn.execute('SELECT last_insert_rowid()').fetchone()[0]

def get_or_create_unit(conn, name, abbreviation):
    """Mértékegység lekérdezése vagy létrehozása"""
    cursor = conn.execute('SELECT id FROM units WHERE abbreviation = ?', (abbreviation,))
    row = cursor.fetchone()
    if row:
        return row[0]
    
    conn.execute('''
        INSERT INTO units (name, abbreviation, is_deleted, created_at)
        VALUES (?, ?, 0, ?)
    ''', (name, abbreviation, datetime.now()))
    conn.commit()
    return conn.execute('SELECT last_insert_rowid()').fetchone()[0]

def get_locations(conn):
    """Helyszínek lekérdezése típus szerint"""
    warehouses = conn.execute('''
        SELECT id, name FROM locations 
        WHERE location_type = 'WAREHOUSE' AND is_deleted = 0 AND is_active = 1
    ''').fetchall()
    
    cars = conn.execute('''
        SELECT id, name FROM locations 
        WHERE location_type = 'CAR' AND is_deleted = 0 AND is_active = 1
    ''').fetchall()
    
    return warehouses, cars

def add_product(conn, name, package_size, barcode, category_id, unit_id):
    """Termék hozzáadása (ha még nem létezik)"""
    cursor = conn.execute('SELECT id FROM products WHERE name = ? AND is_deleted = 0', (name,))
    row = cursor.fetchone()
    if row:
        print(f"  Termék már létezik: {name}")
        return row[0]
    
    min_stock = random.randint(5, 20)
    
    conn.execute('''
        INSERT INTO products (name, barcode, package_size, category_id, unit_id, min_stock_level, is_deleted, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?)
    ''', (name, barcode, package_size, category_id, unit_id, min_stock, datetime.now()))
    conn.commit()
    
    product_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    print(f"  + Új termék: {name} (ID: {product_id})")
    return product_id

def add_stock(conn, product_id, location_id, quantity):
    """Készlet hozzáadása helyszínhez"""
    # Ellenőrizzük, van-e már készlet
    cursor = conn.execute('''
        SELECT quantity FROM location_inventory 
        WHERE product_id = ? AND location_id = ?
    ''', (product_id, location_id))
    row = cursor.fetchone()
    
    if row:
        # Frissítés
        new_qty = row[0] + quantity
        conn.execute('''
            UPDATE location_inventory SET quantity = ?, last_updated = ?
            WHERE product_id = ? AND location_id = ?
        ''', (new_qty, datetime.now(), product_id, location_id))
    else:
        # Új rekord
        conn.execute('''
            INSERT INTO location_inventory (product_id, location_id, quantity, last_updated)
            VALUES (?, ?, ?, ?)
        ''', (product_id, location_id, quantity, datetime.now()))
    
    # Inventory tábla frissítése (összesített készlet)
    total = conn.execute('''
        SELECT COALESCE(SUM(quantity), 0) FROM location_inventory WHERE product_id = ?
    ''', (product_id,)).fetchone()[0]
    
    cursor = conn.execute('SELECT id FROM inventory WHERE product_id = ?', (product_id,))
    if cursor.fetchone():
        conn.execute('''
            UPDATE inventory SET quantity = ?, last_updated = ? WHERE product_id = ?
        ''', (total, datetime.now(), product_id))
    else:
        conn.execute('''
            INSERT INTO inventory (product_id, quantity, last_updated)
            VALUES (?, ?, ?)
        ''', (product_id, total, datetime.now()))
    
    conn.commit()

def main():
    print("=" * 50)
    print("Edibes Leltár - Demo adatok létrehozása")
    print("=" * 50)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Mértékegység
    unit_id = get_or_create_unit(conn, 'darab', 'db')
    print(f"Mértékegység ID: {unit_id}")
    
    # Helyszínek lekérdezése
    warehouses, cars = get_locations(conn)
    
    if not warehouses:
        print("HIBA: Nincs raktár helyszín! Hozz létre egyet előbb.")
        return
    
    print(f"\nRaktárak: {[dict(w)['name'] for w in warehouses]}")
    print(f"Autók: {[dict(c)['name'] for c in cars]}")
    
    warehouse_id = warehouses[0]['id']
    car_id = cars[0]['id'] if cars else None
    
    print("\n" + "-" * 50)
    print("Termékek létrehozása és készlet feltöltése...")
    print("-" * 50)
    
    products_created = 0
    
    for category_name, products in DEMO_PRODUCTS.items():
        print(f"\n📦 Kategória: {category_name}")
        category_id = get_or_create_category(conn, category_name)
        
        for name, package_size, barcode in products:
            product_id = add_product(conn, name, package_size, barcode, category_id, unit_id)
            
            # Raktári készlet: 50-200 között
            warehouse_qty = random.randint(50, 200)
            add_stock(conn, product_id, warehouse_id, warehouse_qty)
            print(f"    📍 Raktár: {warehouse_qty} db")
            
            # Autó készlet: 5-30 között (csak ha van autó)
            if car_id:
                car_qty = random.randint(5, 30)
                add_stock(conn, product_id, car_id, car_qty)
                print(f"    🚚 Autó: {car_qty} db")
            
            products_created += 1
    
    conn.close()
    
    print("\n" + "=" * 50)
    print(f"✅ Kész! {products_created} termék hozzáadva/frissítve.")
    print("=" * 50)

if __name__ == '__main__':
    main()
