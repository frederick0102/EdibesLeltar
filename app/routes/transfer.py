"""
Áthelyezési (Transfer) route-ok
Raktár -> Autó -> Automata közötti készletmozgások kezelése

LOGISZTIKAI SZABÁLYOK:
1. BESZERZÉS: Külső forrás -> Raktár (STOCK_IN)
2. FELTÖLTÉS: Raktár -> Autó (TRANSFER)
3. FOGYASZTÁS: Autó -> Automata (CONSUMPTION/TRANSFER)
4. VISSZAVONÁS: Kompenzáló tranzakció (REVERSAL) - soha nem törlünk!
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app.database import get_db_connection, log_audit
from app.models import MovementType, LocationType
from datetime import datetime

transfer_bp = Blueprint('transfer', __name__, url_prefix='/transfer')


def get_location_stock(db, product_id, location_id):
    """Készlet lekérdezése egy adott helyszínen"""
    result = db.execute('''
        SELECT quantity FROM location_inventory 
        WHERE product_id = ? AND location_id = ?
    ''', (product_id, location_id)).fetchone()
    return result['quantity'] if result else 0


def update_location_stock(db, product_id, location_id, quantity_change):
    """
    Készlet frissítése egy helyszínen
    Visszatér: (quantity_before, quantity_after)
    """
    current = get_location_stock(db, product_id, location_id)
    new_quantity = current + quantity_change
    
    if new_quantity < 0:
        raise ValueError(f'Nincs elegendő készlet! Jelenlegi: {current}, változás: {quantity_change}')
    
    existing = db.execute('''
        SELECT id FROM location_inventory 
        WHERE product_id = ? AND location_id = ?
    ''', (product_id, location_id)).fetchone()
    
    if existing:
        db.execute('''
            UPDATE location_inventory 
            SET quantity = ?, last_updated = CURRENT_TIMESTAMP 
            WHERE product_id = ? AND location_id = ?
        ''', (new_quantity, product_id, location_id))
    else:
        db.execute('''
            INSERT INTO location_inventory (product_id, location_id, quantity)
            VALUES (?, ?, ?)
        ''', (product_id, location_id, new_quantity))
    
    return current, new_quantity


def record_movement(db, product_id, movement_type, quantity_change, 
                   quantity_before, quantity_after, location_id=None,
                   source_location_id=None, target_location_id=None,
                   reference_movement_id=None, note=None):
    """Mozgás rögzítése az audit trail-be"""
    cursor = db.execute('''
        INSERT INTO inventory_movements 
        (product_id, movement_type, quantity_change, quantity_before, quantity_after,
         location_id, source_location_id, target_location_id, reference_movement_id, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (product_id, movement_type, quantity_change, quantity_before, quantity_after,
          location_id, source_location_id, target_location_id, reference_movement_id, note))
    return cursor.lastrowid


def execute_transfer(db, product_id, source_location_id, target_location_id, quantity, note=None):
    """
    ATOMI ÁTHELYEZÉS végrehajtása
    
    Ez a kritikus művelet! Egy tranzakcióban:
    1. Forrásból csökken
    2. Célba növekszik
    3. Mindkét mozgás naplózódik
    
    Visszatér: (source_movement_id, target_movement_id)
    """
    if quantity <= 0:
        raise ValueError('A mennyiségnek pozitívnak kell lennie!')
    
    if source_location_id == target_location_id:
        raise ValueError('A forrás és cél helyszín nem lehet ugyanaz!')
    
    # Ellenőrizzük a forrás készletet
    source_stock = get_location_stock(db, product_id, source_location_id)
    if source_stock < quantity:
        raise ValueError(f'Nincs elegendő készlet a forrás helyszínen! Elérhető: {source_stock}')
    
    # FORRÁS: csökkentés
    source_before, source_after = update_location_stock(db, product_id, source_location_id, -quantity)
    
    # CÉL: növelés
    target_before, target_after = update_location_stock(db, product_id, target_location_id, quantity)
    
    # Mozgások rögzítése
    source_movement_id = record_movement(
        db, product_id, MovementType.TRANSFER_OUT, -quantity,
        source_before, source_after,
        location_id=source_location_id,
        source_location_id=source_location_id,
        target_location_id=target_location_id,
        note=note
    )
    
    target_movement_id = record_movement(
        db, product_id, MovementType.TRANSFER_IN, quantity,
        target_before, target_after,
        location_id=target_location_id,
        source_location_id=source_location_id,
        target_location_id=target_location_id,
        reference_movement_id=source_movement_id,
        note=note
    )
    
    return source_movement_id, target_movement_id


@transfer_bp.route('/')
@login_required
def transfer_home():
    """Áthelyezés főoldal - workflow választó"""
    db = get_db_connection()
    
    # Helyszínek típus szerint
    warehouses = db.execute('''
        SELECT * FROM locations WHERE location_type = 'WAREHOUSE' AND is_deleted = 0 AND is_active = 1
    ''').fetchall()
    
    cars = db.execute('''
        SELECT * FROM locations WHERE location_type = 'CAR' AND is_deleted = 0 AND is_active = 1
    ''').fetchall()
    
    vendings = db.execute('''
        SELECT * FROM locations WHERE location_type = 'VENDING' AND is_deleted = 0 AND is_active = 1
    ''').fetchall()
    
    return render_template('transfer/home.html',
                         warehouses=warehouses,
                         cars=cars,
                         vendings=vendings,
                         LocationType=LocationType)


@transfer_bp.route('/quick')
@login_required
def quick_transfer():
    """
    GYORS ÁTHELYEZÉS - termék alapú
    URL: /transfer/quick?product=123
    Egy adott termék helyszínek közötti mozgatása
    """
    db = get_db_connection()
    
    product_id = request.args.get('product', type=int)
    
    # Termék adatai
    product = None
    if product_id:
        product = db.execute('''
            SELECT p.*, u.abbreviation as unit_abbr, c.name as category_name
            FROM products p
            LEFT JOIN units u ON p.unit_id = u.id
            LEFT JOIN categories c ON p.category_id = c.id
            WHERE p.id = ? AND p.is_deleted = 0
        ''', (product_id,)).fetchone()
    
    # Összes aktív helyszín
    locations = db.execute('''
        SELECT * FROM locations 
        WHERE is_deleted = 0 AND is_active = 1
        ORDER BY 
            CASE location_type 
                WHEN 'WAREHOUSE' THEN 1 
                WHEN 'CAR' THEN 2 
                WHEN 'VENDING' THEN 3 
            END, name
    ''').fetchall()
    
    # Termék készletei helyszínenként
    location_stocks = {}
    if product_id:
        stocks = db.execute('''
            SELECT location_id, quantity 
            FROM location_inventory 
            WHERE product_id = ?
        ''', (product_id,)).fetchall()
        location_stocks = {s['location_id']: s['quantity'] for s in stocks}
    
    # Összes termék a listához
    products = db.execute('''
        SELECT p.id, p.name, p.barcode, p.package_size, u.abbreviation as unit_abbr
        FROM products p
        LEFT JOIN units u ON p.unit_id = u.id
        WHERE p.is_deleted = 0
        ORDER BY p.name
    ''').fetchall()
    
    return render_template('transfer/quick_product.html',
                         product=product,
                         products=products,
                         locations=locations,
                         location_stocks=location_stocks,
                         LocationType=LocationType)


@transfer_bp.route('/quick/execute', methods=['POST'])
@login_required
def execute_quick_transfer():
    """
    GYORS ÁTHELYEZÉS végrehajtása
    POST adatok: product_id, source_location_id, target_location_id, quantity, note
    """
    db = get_db_connection()
    
    product_id = request.form.get('product_id', type=int)
    source_id = request.form.get('source_location_id', type=int)
    target_id = request.form.get('target_location_id', type=int)
    quantity = request.form.get('quantity', type=float)
    note = request.form.get('note', '').strip() or None
    
    if not all([product_id, source_id, target_id, quantity]):
        flash('Minden mező kitöltése kötelező!', 'danger')
        return redirect(url_for('transfer.quick_transfer', product=product_id))
    
    if source_id == target_id:
        flash('A forrás és cél helyszín nem lehet ugyanaz!', 'danger')
        return redirect(url_for('transfer.quick_transfer', product=product_id))
    
    if quantity <= 0:
        flash('A mennyiségnek pozitívnak kell lennie!', 'danger')
        return redirect(url_for('transfer.quick_transfer', product=product_id))
    
    try:
        execute_transfer(db, product_id, source_id, target_id, quantity, note)
        
        # Termék és helyszín nevek a flash üzenethez
        product = db.execute('SELECT name FROM products WHERE id = ?', (product_id,)).fetchone()
        source = db.execute('SELECT name FROM locations WHERE id = ?', (source_id,)).fetchone()
        target = db.execute('SELECT name FROM locations WHERE id = ?', (target_id,)).fetchone()
        
        flash(f'Sikeres áthelyezés! {int(quantity)} db {product["name"]} ({source["name"]} → {target["name"]})', 'success')
        return redirect(url_for('inventory.inventory_list'))
        
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('transfer.quick_transfer', product=product_id))
    except Exception as e:
        db.rollback()
        flash(f'Hiba történt: {str(e)}', 'danger')
        return redirect(url_for('transfer.quick_transfer', product=product_id))


@transfer_bp.route('/warehouse-to-car', methods=['GET', 'POST'])
@login_required
def warehouse_to_car():
    """
    FELTÖLTÉS: Raktár -> Autó
    Ez a fő workflow amikor az autót megrakják a raktárból
    """
    db = get_db_connection()
    
    if request.method == 'POST':
        source_id = request.form.get('source_location_id', type=int)
        target_id = request.form.get('target_location_id', type=int)
        product_id = request.form.get('product_id', type=int)
        quantity = request.form.get('quantity', type=float)
        note = request.form.get('note', '').strip() or None
        
        if not all([source_id, target_id, product_id, quantity]):
            flash('Minden mező kitöltése kötelező!', 'danger')
            return redirect(url_for('transfer.warehouse_to_car'))
        
        try:
            execute_transfer(db, product_id, source_id, target_id, quantity, note)
            db.commit()
            
            # Termék neve a visszajelzéshez
            product = db.execute('SELECT name FROM products WHERE id = ?', (product_id,)).fetchone()
            source = db.execute('SELECT name FROM locations WHERE id = ?', (source_id,)).fetchone()
            target = db.execute('SELECT name FROM locations WHERE id = ?', (target_id,)).fetchone()
            
            flash(f'Áthelyezve: {quantity} db {product["name"]} ({source["name"]} → {target["name"]})', 'success')
            
            # Maradunk az oldalon a folytatáshoz
            return redirect(url_for('transfer.warehouse_to_car', 
                                   source=source_id, target=target_id))
            
        except ValueError as e:
            flash(str(e), 'danger')
        except Exception as e:
            db.rollback()
            flash(f'Hiba történt: {str(e)}', 'danger')
    
    # Előre kiválasztott helyszínek
    selected_source = request.args.get('source', type=int)
    selected_target = request.args.get('target', type=int)
    
    # Raktárak
    warehouses = db.execute('''
        SELECT * FROM locations 
        WHERE location_type = 'WAREHOUSE' AND is_deleted = 0 AND is_active = 1
        ORDER BY name
    ''').fetchall()
    
    # Autók
    cars = db.execute('''
        SELECT * FROM locations 
        WHERE location_type = 'CAR' AND is_deleted = 0 AND is_active = 1
        ORDER BY name
    ''').fetchall()
    
    # Alapértelmezett raktár ha nincs kiválasztva
    if not selected_source and warehouses:
        selected_source = warehouses[0]['id']
    
    # Termékek a kiválasztott raktárból (készlettel)
    products = []
    if selected_source:
        products = db.execute('''
            SELECT 
                p.id, p.name, p.barcode, p.package_size,
                u.abbreviation as unit_abbr,
                COALESCE(li.quantity, 0) as available_quantity
            FROM products p
            LEFT JOIN units u ON p.unit_id = u.id
            LEFT JOIN location_inventory li ON p.id = li.product_id AND li.location_id = ?
            WHERE p.is_deleted = 0
            ORDER BY p.name
        ''', (selected_source,)).fetchall()
    
    return render_template('transfer/warehouse_to_car.html',
                         warehouses=warehouses,
                         cars=cars,
                         products=products,
                         selected_source=selected_source,
                         selected_target=selected_target)


@transfer_bp.route('/car-to-vending', methods=['GET', 'POST'])
@login_required
def car_to_vending():
    """
    AUTOMATA FELTÖLTÉS: Autó -> Automata
    Ezt használják terepen amikor az automatát töltik
    MOBIL-BARÁT felület!
    """
    db = get_db_connection()
    
    if request.method == 'POST':
        source_id = request.form.get('source_location_id', type=int)
        target_id = request.form.get('target_location_id', type=int)
        product_id = request.form.get('product_id', type=int)
        quantity = request.form.get('quantity', type=float)
        note = request.form.get('note', '').strip() or 'Automata feltöltés'
        
        if not all([source_id, target_id, product_id, quantity]):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': 'Minden mező kitöltése kötelező!'})
            flash('Minden mező kitöltése kötelező!', 'danger')
            return redirect(url_for('transfer.car_to_vending'))
        
        try:
            execute_transfer(db, product_id, source_id, target_id, quantity, note)
            db.commit()
            
            product = db.execute('SELECT name FROM products WHERE id = ?', (product_id,)).fetchone()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True, 
                    'message': f'{quantity} db {product["name"]} áthelyezve'
                })
            
            flash(f'{quantity} db {product["name"]} áthelyezve!', 'success')
            return redirect(url_for('transfer.car_to_vending', 
                                   source=source_id, target=target_id))
            
        except ValueError as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': str(e)})
            flash(str(e), 'danger')
        except Exception as e:
            db.rollback()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': str(e)})
            flash(f'Hiba történt: {str(e)}', 'danger')
    
    selected_source = request.args.get('source', type=int)
    selected_target = request.args.get('target', type=int)
    
    cars = db.execute('''
        SELECT * FROM locations 
        WHERE location_type = 'CAR' AND is_deleted = 0 AND is_active = 1
        ORDER BY name
    ''').fetchall()
    
    vendings = db.execute('''
        SELECT * FROM locations 
        WHERE location_type = 'VENDING' AND is_deleted = 0 AND is_active = 1
        ORDER BY name
    ''').fetchall()
    
    if not selected_source and cars:
        selected_source = cars[0]['id']
    
    products = []
    if selected_source:
        products = db.execute('''
            SELECT 
                p.id, p.name, p.barcode, p.package_size,
                u.abbreviation as unit_abbr,
                COALESCE(li.quantity, 0) as available_quantity
            FROM products p
            LEFT JOIN units u ON p.unit_id = u.id
            LEFT JOIN location_inventory li ON p.id = li.product_id AND li.location_id = ?
            WHERE p.is_deleted = 0 AND COALESCE(li.quantity, 0) > 0
            ORDER BY p.name
        ''', (selected_source,)).fetchall()
    
    return render_template('transfer/car_to_vending.html',
                         cars=cars,
                         vendings=vendings,
                         products=products,
                         selected_source=selected_source,
                         selected_target=selected_target)


@transfer_bp.route('/quick/<int:source_id>/<int:target_id>')
@login_required
def quick_transfer_page(source_id, target_id):
    """
    GYORS ÁTHELYEZÉS oldal - vonalkód olvasóval
    Mobil-optimalizált, nagy gombok
    """
    db = get_db_connection()
    
    source = db.execute('SELECT * FROM locations WHERE id = ?', (source_id,)).fetchone()
    target = db.execute('SELECT * FROM locations WHERE id = ?', (target_id,)).fetchone()
    
    if not source or not target:
        flash('Helyszín nem található!', 'danger')
        return redirect(url_for('transfer.transfer_home'))
    
    # Készlet a forráson
    products = db.execute('''
        SELECT 
            p.id, p.name, p.barcode, p.package_size,
            u.abbreviation as unit_abbr,
            COALESCE(li.quantity, 0) as available_quantity
        FROM products p
        LEFT JOIN units u ON p.unit_id = u.id
        LEFT JOIN location_inventory li ON p.id = li.product_id AND li.location_id = ?
        WHERE p.is_deleted = 0 AND COALESCE(li.quantity, 0) > 0
        ORDER BY p.name
    ''', (source_id,)).fetchall()
    
    return render_template('transfer/quick.html',
                         source=source,
                         target=target,
                         products=products,
                         LocationType=LocationType)


@transfer_bp.route('/api/execute', methods=['POST'])
@login_required
def api_execute_transfer():
    """API: Áthelyezés végrehajtása (AJAX)"""
    db = get_db_connection()
    
    data = request.get_json()
    source_id = data.get('source_location_id')
    target_id = data.get('target_location_id')
    product_id = data.get('product_id')
    quantity = data.get('quantity')
    note = data.get('note', '')
    
    if not all([source_id, target_id, product_id, quantity]):
        return jsonify({'success': False, 'error': 'Hiányzó paraméterek!'})
    
    try:
        execute_transfer(db, product_id, source_id, target_id, float(quantity), note or None)
        db.commit()
        
        product = db.execute('SELECT name FROM products WHERE id = ?', (product_id,)).fetchone()
        new_stock = get_location_stock(db, product_id, source_id)
        
        return jsonify({
            'success': True,
            'message': f'{quantity} db {product["name"]} áthelyezve',
            'new_source_stock': new_stock
        })
        
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})


@transfer_bp.route('/api/product-by-barcode/<barcode>')
@login_required
def api_product_by_barcode(barcode):
    """API: Termék keresése vonalkód alapján"""
    db = get_db_connection()
    
    location_id = request.args.get('location_id', type=int)
    
    product = db.execute('''
        SELECT 
            p.id, p.name, p.barcode, p.package_size,
            u.abbreviation as unit_abbr
        FROM products p
        LEFT JOIN units u ON p.unit_id = u.id
        WHERE p.barcode = ? AND p.is_deleted = 0
    ''', (barcode,)).fetchone()
    
    if not product:
        return jsonify({'success': False, 'error': 'Termék nem található!'})
    
    result = dict(product)
    
    if location_id:
        stock = get_location_stock(db, product['id'], location_id)
        result['available_quantity'] = stock
    
    return jsonify({'success': True, 'product': result})


@transfer_bp.route('/history')
@login_required
def transfer_history():
    """Áthelyezések története"""
    db = get_db_connection()
    
    location_id = request.args.get('location', type=int)
    
    query = '''
        SELECT 
            m.*,
            p.name as product_name,
            l.name as location_name,
            sl.name as source_location_name,
            tl.name as target_location_name
        FROM inventory_movements m
        JOIN products p ON m.product_id = p.id
        LEFT JOIN locations l ON m.location_id = l.id
        LEFT JOIN locations sl ON m.source_location_id = sl.id
        LEFT JOIN locations tl ON m.target_location_id = tl.id
        WHERE m.movement_type IN ('TRANSFER', 'TRANSFER_IN', 'TRANSFER_OUT')
    '''
    params = []
    
    if location_id:
        query += ' AND (m.source_location_id = ? OR m.target_location_id = ?)'
        params.extend([location_id, location_id])
    
    query += ' ORDER BY m.created_at DESC LIMIT 100'
    
    movements = db.execute(query, params).fetchall()
    
    locations = db.execute('''
        SELECT id, name, location_type FROM locations WHERE is_deleted = 0 ORDER BY name
    ''').fetchall()
    
    return render_template('transfer/history.html',
                         movements=movements,
                         locations=locations,
                         selected_location=location_id,
                         MovementType=MovementType)


@transfer_bp.route('/reversal/<int:movement_id>', methods=['POST'])
@login_required
def create_reversal(movement_id):
    """
    KOMPENZÁLÓ TRANZAKCIÓ létrehozása
    Nem töröljük az eredeti mozgást, hanem egy ellentétes mozgást hozunk létre!
    """
    db = get_db_connection()
    
    # Eredeti mozgás lekérdezése
    original = db.execute('''
        SELECT * FROM inventory_movements WHERE id = ?
    ''', (movement_id,)).fetchone()
    
    if not original:
        flash('Mozgás nem található!', 'danger')
        return redirect(url_for('transfer.transfer_history'))
    
    # Ellenőrizzük, hogy már volt-e visszavonás
    existing_reversal = db.execute('''
        SELECT id FROM inventory_movements 
        WHERE reference_movement_id = ? AND movement_type = 'REVERSAL'
    ''', (movement_id,)).fetchone()
    
    if existing_reversal:
        flash('Ez a mozgás már vissza lett vonva!', 'warning')
        return redirect(url_for('transfer.transfer_history'))
    
    try:
        # Kompenzáló mozgás: ellentétes irányba, ellentétes mennyiséggel
        if original['movement_type'] in ['TRANSFER_OUT', 'TRANSFER_IN']:
            # Áthelyezés visszavonása: vissza kell helyezni
            source_id = original['target_location_id']  # Eredeti cél = új forrás
            target_id = original['source_location_id']  # Eredeti forrás = új cél
            quantity = abs(original['quantity_change'])
            
            execute_transfer(db, original['product_id'], source_id, target_id, quantity,
                           f'Visszavonás: #{movement_id}')
        else:
            # Egyéb mozgás visszavonása
            location_id = original['location_id']
            quantity_change = -original['quantity_change']
            
            before, after = update_location_stock(db, original['product_id'], 
                                                  location_id, quantity_change)
            
            record_movement(db, original['product_id'], MovementType.REVERSAL,
                          quantity_change, before, after, location_id,
                          reference_movement_id=movement_id,
                          note=f'Visszavonás: #{movement_id}')
        
        db.commit()
        flash('Mozgás sikeresen visszavonva!', 'success')
        
    except ValueError as e:
        flash(f'Visszavonás sikertelen: {str(e)}', 'danger')
    except Exception as e:
        db.rollback()
        flash(f'Hiba történt: {str(e)}', 'danger')
    
    return redirect(url_for('transfer.transfer_history'))


@transfer_bp.route('/car-consumption', methods=['GET', 'POST'])
@login_required
def car_consumption():
    """
    AUTÓ KIADÁS: Termék kikerül az autóból (fogyasztás)
    NEM kell cél automata - a termék egyszerűen "elfogyott" / kiadásra került
    Ez a legegyszerűbb workflow terepen!
    """
    db = get_db_connection()
    
    if request.method == 'POST':
        source_id = request.form.get('source_location_id', type=int)
        product_id = request.form.get('product_id', type=int)
        quantity = request.form.get('quantity', type=float)
        note = request.form.get('note', '').strip() or 'Autó kiadás'
        
        if not all([source_id, product_id, quantity]):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': 'Minden mező kitöltése kötelező!'})
            flash('Minden mező kitöltése kötelező!', 'danger')
            return redirect(url_for('transfer.car_consumption'))
        
        if quantity <= 0:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': 'A mennyiségnek pozitívnak kell lennie!'})
            flash('A mennyiségnek pozitívnak kell lennie!', 'danger')
            return redirect(url_for('transfer.car_consumption'))
        
        try:
            # Készlet csökkentése az autóból - ez CONSUMPTION típusú mozgás
            before, after = update_location_stock(db, product_id, source_id, -quantity)
            
            # Mozgás rögzítése
            record_movement(
                db, product_id, MovementType.CONSUMPTION, -quantity,
                before, after,
                location_id=source_id,
                note=note
            )
            
            # Összkészlet frissítése az inventory táblában (kompatibilitás)
            total_qty = db.execute('''
                SELECT COALESCE(SUM(li.quantity), 0) as total 
                FROM location_inventory li
                JOIN locations l ON li.location_id = l.id
                WHERE li.product_id = ? AND l.is_deleted = 0
            ''', (product_id,)).fetchone()['total']
            
            existing_inv = db.execute('SELECT id FROM inventory WHERE product_id = ?', (product_id,)).fetchone()
            if existing_inv:
                db.execute('UPDATE inventory SET quantity = ?, last_updated = CURRENT_TIMESTAMP WHERE product_id = ?',
                          (total_qty, product_id))
            else:
                db.execute('INSERT INTO inventory (product_id, quantity) VALUES (?, ?)', (product_id, total_qty))
            
            db.commit()
            
            product = db.execute('SELECT name FROM products WHERE id = ?', (product_id,)).fetchone()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True, 
                    'message': f'{int(quantity)} db {product["name"]} kiadva',
                    'new_quantity': after
                })
            
            flash(f'{int(quantity)} db {product["name"]} kiadva az autóból!', 'success')
            return redirect(url_for('transfer.car_consumption', source=source_id))
            
        except ValueError as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': str(e)})
            flash(str(e), 'danger')
        except Exception as e:
            db.rollback()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': str(e)})
            flash(f'Hiba történt: {str(e)}', 'danger')
    
    selected_source = request.args.get('source', type=int)
    
    # Autók lekérdezése
    cars = db.execute('''
        SELECT * FROM locations 
        WHERE location_type = 'CAR' AND is_deleted = 0 AND is_active = 1
        ORDER BY name
    ''').fetchall()
    
    if not selected_source and cars:
        selected_source = cars[0]['id']
    
    # Termékek az autóból (csak ahol van készlet)
    products = []
    if selected_source:
        products = db.execute('''
            SELECT 
                p.id, p.name, p.barcode, p.package_size,
                u.abbreviation as unit_abbr,
                COALESCE(li.quantity, 0) as available_quantity
            FROM products p
            LEFT JOIN units u ON p.unit_id = u.id
            LEFT JOIN location_inventory li ON p.id = li.product_id AND li.location_id = ?
            WHERE p.is_deleted = 0 AND COALESCE(li.quantity, 0) > 0
            ORDER BY p.name
        ''', (selected_source,)).fetchall()
    
    return render_template('transfer/car_consumption.html',
                         cars=cars,
                         products=products,
                         selected_source=selected_source)
