"""
Készletkezelési route-ok
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app.database import get_db_connection, log_audit
from app.models import MovementType, LocationType
from datetime import datetime, timedelta

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')


@inventory_bp.route('/')
@login_required
def list_inventory():
    """Készlet listázása - helyszínenkénti bontással"""
    db = get_db_connection()
    
    # Szűrési paraméterek
    search = request.args.get('search', '')
    category_id = request.args.get('category', type=int)
    stock_filter = request.args.get('stock', '')  # 'low', 'zero', 'all'
    location_id = request.args.get('location', type=int)  # helyszín szűrő
    
    # Helyszínek lekérdezése
    locations = db.execute('''
        SELECT id, name, location_type FROM locations 
        WHERE is_deleted = 0 AND is_active = 1
        ORDER BY 
            CASE location_type 
                WHEN 'WAREHOUSE' THEN 1 
                WHEN 'CAR' THEN 2 
                WHEN 'VENDING' THEN 3 
            END, name
    ''').fetchall()
    
    # Össz készlet lekérdezése (location_inventory táblából)
    query = '''
        SELECT 
            p.id, p.name, p.barcode, p.package_size, p.min_stock_level,
            c.name as category_name,
            u.abbreviation as unit_abbr,
            COALESCE(SUM(li.quantity), 0) as current_quantity,
            MAX(li.last_updated) as last_updated
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN units u ON p.unit_id = u.id
        LEFT JOIN location_inventory li ON p.id = li.product_id
        LEFT JOIN locations l ON li.location_id = l.id AND l.is_deleted = 0
        WHERE p.is_deleted = 0
    '''
    params = []
    
    if search:
        query += ' AND (p.name LIKE ? OR p.barcode LIKE ?)'
        search_pattern = f'%{search}%'
        params.extend([search_pattern, search_pattern])
    
    if category_id:
        query += ' AND p.category_id = ?'
        params.append(category_id)
    
    # Helyszín szűrő
    if location_id:
        query += ' AND li.location_id = ?'
        params.append(location_id)
    
    query += ' GROUP BY p.id, p.name, p.barcode, p.package_size, p.min_stock_level, c.name, u.abbreviation'
    
    if stock_filter == 'low':
        query += ' HAVING current_quantity < p.min_stock_level AND current_quantity > 0'
    elif stock_filter == 'zero':
        query += ' HAVING current_quantity = 0 OR current_quantity IS NULL'
    
    query += ' ORDER BY p.name'
    
    inventory = db.execute(query, params).fetchall()
    
    # Helyszínenkenti készlet minden termékhez
    location_quantities = {}
    if not location_id:  # Csak ha nincs helyszín szűrő
        location_qty_query = '''
            SELECT 
                li.product_id,
                li.location_id,
                l.name as location_name,
                l.location_type,
                li.quantity
            FROM location_inventory li
            JOIN locations l ON li.location_id = l.id
            WHERE l.is_deleted = 0 AND l.is_active = 1 AND li.quantity > 0
            ORDER BY 
                CASE l.location_type 
                    WHEN 'WAREHOUSE' THEN 1 
                    WHEN 'CAR' THEN 2 
                    WHEN 'VENDING' THEN 3 
                END, l.name
        '''
        location_qty_rows = db.execute(location_qty_query).fetchall()
        
        for row in location_qty_rows:
            product_id = row['product_id']
            if product_id not in location_quantities:
                location_quantities[product_id] = []
            location_quantities[product_id].append({
                'location_id': row['location_id'],
                'location_name': row['location_name'],
                'location_type': row['location_type'],
                'quantity': row['quantity']
            })
    
    # Kategóriák a szűrőhöz
    categories = db.execute('''
        SELECT id, name FROM categories WHERE is_deleted = 0 ORDER BY name
    ''').fetchall()
    
    return render_template('inventory/list.html',
                         inventory=inventory,
                         categories=categories,
                         locations=locations,
                         location_quantities=location_quantities,
                         search=search,
                         selected_category=category_id,
                         selected_location=location_id,
                         stock_filter=stock_filter,
                         LocationType=LocationType)


@inventory_bp.route('/movement', methods=['GET', 'POST'])
@login_required
def add_movement():
    """Készletmozgás rögzítése - helyszín alapú"""
    db = get_db_connection()
    
    # Helyszínek lekérdezése
    locations = db.execute('''
        SELECT id, name, location_type FROM locations 
        WHERE is_deleted = 0 AND is_active = 1
        ORDER BY 
            CASE location_type 
                WHEN 'WAREHOUSE' THEN 1 
                WHEN 'CAR' THEN 2 
                WHEN 'VENDING' THEN 3 
            END, name
    ''').fetchall()
    
    # Alapértelmezett helyszín (raktár)
    default_location = db.execute('''
        SELECT id FROM locations 
        WHERE location_type = 'WAREHOUSE' AND is_deleted = 0 AND is_active = 1 
        LIMIT 1
    ''').fetchone()
    default_location_id = default_location['id'] if default_location else None
    
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        movement_type = request.form.get('movement_type')
        quantity = float(request.form.get('quantity', 0))
        location_id = request.form.get('location_id') or default_location_id
        note = request.form.get('note', '').strip() or None
        
        if not product_id or not movement_type or quantity <= 0:
            flash('Minden mező kitöltése kötelező és a mennyiségnek pozitívnak kell lennie!', 'danger')
            return redirect(url_for('inventory.add_movement'))
        
        if not location_id:
            flash('Helyszín kiválasztása kötelező!', 'danger')
            return redirect(url_for('inventory.add_movement'))
        
        # Aktuális készlet lekérdezése - helyszín alapú
        current = db.execute('''
            SELECT quantity FROM location_inventory 
            WHERE product_id = ? AND location_id = ?
        ''', (product_id, location_id)).fetchone()
        
        current_quantity = current['quantity'] if current else 0
        
        # Mennyiség számítása a mozgás típusa alapján
        if movement_type in ['STOCK_OUT', 'LOSS']:
            quantity_change = -quantity
        else:
            quantity_change = quantity
        
        new_quantity = current_quantity + quantity_change
        
        # Negatív készlet ellenőrzés
        if new_quantity < 0:
            location_name = db.execute('SELECT name FROM locations WHERE id = ?', (location_id,)).fetchone()
            flash(f'Nincs elegendő készlet ezen a helyszínen ({location_name["name"]})! Jelenlegi: {current_quantity}', 'danger')
            return redirect(url_for('inventory.add_movement'))
        
        try:
            # Helyszín-specifikus készlet frissítése
            if current:
                db.execute('''
                    UPDATE location_inventory 
                    SET quantity = ?, last_updated = ? 
                    WHERE product_id = ? AND location_id = ?
                ''', (new_quantity, datetime.now(), product_id, location_id))
            else:
                db.execute('''
                    INSERT INTO location_inventory (product_id, location_id, quantity)
                    VALUES (?, ?, ?)
                ''', (product_id, location_id, new_quantity))
            
            # Összkészlet frissítése az inventory táblában (kompatibilitás)
            total_qty = db.execute('''
                SELECT COALESCE(SUM(quantity), 0) as total 
                FROM location_inventory WHERE product_id = ?
            ''', (product_id,)).fetchone()['total']
            
            existing_inv = db.execute('SELECT id FROM inventory WHERE product_id = ?', (product_id,)).fetchone()
            if existing_inv:
                db.execute('UPDATE inventory SET quantity = ?, last_updated = ? WHERE product_id = ?',
                          (total_qty, datetime.now(), product_id))
            else:
                db.execute('INSERT INTO inventory (product_id, quantity) VALUES (?, ?)', (product_id, total_qty))
            
            # Mozgás rögzítése helyszínnel
            db.execute('''
                INSERT INTO inventory_movements 
                (product_id, movement_type, quantity_change, quantity_before, quantity_after, location_id, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (product_id, movement_type, quantity_change, current_quantity, new_quantity, location_id, note))
            
            db.commit()
            
            # Termék és helyszín neve a visszajelzéshez
            product = db.execute('SELECT name FROM products WHERE id = ?', (product_id,)).fetchone()
            location = db.execute('SELECT name FROM locations WHERE id = ?', (location_id,)).fetchone()
            
            flash(f'Készletmozgás rögzítve: {product["name"]} ({location["name"]}) - {MovementType.get_label(movement_type)}', 'success')
            return redirect(url_for('inventory.list_inventory'))
            
        except Exception as e:
            db.rollback()
            flash(f'Hiba történt: {str(e)}', 'danger')
    
    # Termékek az űrlaphoz - helyszínenkénti készlettel
    products_base = db.execute('''
        SELECT p.id, p.name, p.barcode, p.package_size, u.abbreviation as unit_abbr
        FROM products p
        LEFT JOIN units u ON p.unit_id = u.id
        WHERE p.is_deleted = 0
        ORDER BY p.name
    ''').fetchall()
    
    # Helyszínenkénti készlet minden termékhez
    products = []
    for p in products_base:
        product_data = dict(p)
        
        # Össz készlet
        total_qty = db.execute('''
            SELECT COALESCE(SUM(quantity), 0) as total FROM location_inventory WHERE product_id = ?
        ''', (p['id'],)).fetchone()['total']
        product_data['current_quantity'] = total_qty
        
        # Helyszínenkénti készlet
        location_qtys = db.execute('''
            SELECT l.id, l.name, l.location_type, COALESCE(li.quantity, 0) as quantity
            FROM locations l
            LEFT JOIN location_inventory li ON l.id = li.location_id AND li.product_id = ?
            WHERE l.is_deleted = 0 AND l.is_active = 1
            ORDER BY CASE l.location_type WHEN 'WAREHOUSE' THEN 1 WHEN 'CAR' THEN 2 WHEN 'VENDING' THEN 3 END, l.name
        ''', (p['id'],)).fetchall()
        # Convert Row objects to dicts for JSON serialization
        product_data['location_quantities'] = [dict(row) for row in location_qtys]
        
        products.append(product_data)
    
    movement_types = [
        ('STOCK_IN', 'Bevételezés (+)'),
        ('STOCK_OUT', 'Kivételezés (-)'),
        ('RETURN', 'Visszavétel (+)'),
        ('ADJUSTMENT', 'Korrekció (+/-)'),
        ('LOSS', 'Selejt/Veszteség (-)')
    ]
    
    # Vonalkód paraméter kezelése (vonalkód olvasóhoz)
    barcode = request.args.get('barcode', '')
    selected_product_id = None
    selected_location_id = request.args.get('location', default_location_id)
    
    if barcode:
        product = db.execute('''
            SELECT id FROM products WHERE barcode = ? AND is_deleted = 0
        ''', (barcode,)).fetchone()
        if product:
            selected_product_id = product['id']
    
    return render_template('inventory/movement.html',
                         products=products,
                         locations=locations,
                         movement_types=movement_types,
                         selected_product_id=selected_product_id,
                         selected_location_id=selected_location_id,
                         barcode=barcode,
                         LocationType=LocationType)


@inventory_bp.route('/quick-out/<int:product_id>', methods=['POST'])
@login_required
def quick_stock_out(product_id):
    """Gyors kivételezés (1 darab)"""
    db = get_db_connection()
    
    quantity = float(request.form.get('quantity', 1))
    
    # Aktuális készlet
    current = db.execute('''
        SELECT quantity FROM inventory WHERE product_id = ?
    ''', (product_id,)).fetchone()
    
    current_quantity = current['quantity'] if current else 0
    
    if current_quantity < quantity:
        return jsonify({'success': False, 'message': 'Nincs elegendő készlet!'}), 400
    
    new_quantity = current_quantity - quantity
    
    try:
        db.execute('''
            UPDATE inventory SET quantity = ?, last_updated = ? WHERE product_id = ?
        ''', (new_quantity, datetime.now(), product_id))
        
        db.execute('''
            INSERT INTO inventory_movements 
            (product_id, movement_type, quantity_change, quantity_before, quantity_after, note)
            VALUES (?, 'STOCK_OUT', ?, ?, ?, 'Gyors kivételezés')
        ''', (product_id, -quantity, current_quantity, new_quantity))
        
        db.commit()
        
        return jsonify({
            'success': True,
            'new_quantity': new_quantity,
            'message': 'Kivételezés sikeres!'
        })
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@inventory_bp.route('/quick-in/<int:product_id>', methods=['POST'])
@login_required
def quick_stock_in(product_id):
    """Gyors bevételezés"""
    db = get_db_connection()
    
    quantity = float(request.form.get('quantity', 1))
    
    # Aktuális készlet
    current = db.execute('''
        SELECT quantity FROM inventory WHERE product_id = ?
    ''', (product_id,)).fetchone()
    
    current_quantity = current['quantity'] if current else 0
    new_quantity = current_quantity + quantity
    
    try:
        if current:
            db.execute('''
                UPDATE inventory SET quantity = ?, last_updated = ? WHERE product_id = ?
            ''', (new_quantity, datetime.now(), product_id))
        else:
            db.execute('''
                INSERT INTO inventory (product_id, quantity) VALUES (?, ?)
            ''', (product_id, new_quantity))
        
        db.execute('''
            INSERT INTO inventory_movements 
            (product_id, movement_type, quantity_change, quantity_before, quantity_after, note)
            VALUES (?, 'STOCK_IN', ?, ?, ?, 'Gyors bevételezés')
        ''', (product_id, quantity, current_quantity, new_quantity))
        
        db.commit()
        
        return jsonify({
            'success': True,
            'new_quantity': new_quantity,
            'message': 'Bevételezés sikeres!'
        })
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@inventory_bp.route('/history')
@login_required
def movement_history():
    """Készletmozgások története - helyszín megjelenítéssel"""
    db = get_db_connection()
    
    # Szűrési paraméterek
    product_id = request.args.get('product', type=int)
    movement_type = request.args.get('type', '')
    location_id = request.args.get('location', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = '''
        SELECT 
            im.id, im.movement_type, im.quantity_change, 
            im.quantity_before, im.quantity_after, im.note, im.created_at,
            im.location_id, im.source_location_id, im.target_location_id,
            p.name as product_name, p.id as product_id, p.package_size,
            u.abbreviation as unit_abbr,
            l.name as location_name, l.location_type,
            sl.name as source_location_name, sl.location_type as source_location_type,
            tl.name as target_location_name, tl.location_type as target_location_type
        FROM inventory_movements im
        JOIN products p ON im.product_id = p.id
        LEFT JOIN units u ON p.unit_id = u.id
        LEFT JOIN locations l ON im.location_id = l.id
        LEFT JOIN locations sl ON im.source_location_id = sl.id
        LEFT JOIN locations tl ON im.target_location_id = tl.id
        WHERE 1=1
    '''
    params = []
    
    if product_id:
        query += ' AND im.product_id = ?'
        params.append(product_id)
    
    if movement_type:
        query += ' AND im.movement_type = ?'
        params.append(movement_type)
    
    if location_id:
        query += ' AND (im.location_id = ? OR im.source_location_id = ? OR im.target_location_id = ?)'
        params.extend([location_id, location_id, location_id])
    
    if date_from:
        query += ' AND DATE(im.created_at) >= ?'
        params.append(date_from)
    
    if date_to:
        query += ' AND DATE(im.created_at) <= ?'
        params.append(date_to)
    
    query += ' ORDER BY im.created_at DESC LIMIT 500'
    
    movements = db.execute(query, params).fetchall()
    
    # Termékek a szűrőhöz
    products = db.execute('''
        SELECT id, name FROM products ORDER BY name
    ''').fetchall()
    
    # Helyszínek a szűrőhöz
    locations = db.execute('''
        SELECT id, name, location_type FROM locations 
        WHERE is_deleted = 0
        ORDER BY CASE location_type WHEN 'WAREHOUSE' THEN 1 WHEN 'CAR' THEN 2 WHEN 'VENDING' THEN 3 END, name
    ''').fetchall()
    
    movement_types = [
        ('STOCK_IN', 'Bevételezés'),
        ('STOCK_OUT', 'Kivételezés'),
        ('RETURN', 'Visszavétel'),
        ('ADJUSTMENT', 'Korrekció'),
        ('INITIAL', 'Kezdőkészlet'),
        ('LOSS', 'Selejt/Veszteség'),
        ('TRANSFER', 'Áthelyezés'),
        ('TRANSFER_OUT', 'Kiadás (áthelyezés)'),
        ('TRANSFER_IN', 'Bevétel (áthelyezés)'),
        ('REVERSAL', 'Visszavonás')
    ]
    
    return render_template('inventory/history.html',
                         movements=movements,
                         products=products,
                         locations=locations,
                         movement_types=movement_types,
                         selected_product=product_id,
                         selected_type=movement_type,
                         selected_location=location_id,
                         date_from=date_from,
                         date_to=date_to,
                         MovementType=MovementType,
                         LocationType=LocationType)


@inventory_bp.route('/set-quantity/<int:product_id>', methods=['POST'])
@login_required
def set_quantity(product_id):
    """Készlet beállítása konkrét értékre (leltározás)"""
    db = get_db_connection()
    
    new_quantity = float(request.form.get('quantity', 0))
    note = request.form.get('note', 'Leltározás/korrekció')
    
    if new_quantity < 0:
        flash('A mennyiség nem lehet negatív!', 'danger')
        return redirect(url_for('inventory.list_inventory'))
    
    # Aktuális készlet
    current = db.execute('''
        SELECT quantity FROM inventory WHERE product_id = ?
    ''', (product_id,)).fetchone()
    
    current_quantity = current['quantity'] if current else 0
    quantity_change = new_quantity - current_quantity
    
    try:
        if current:
            db.execute('''
                UPDATE inventory SET quantity = ?, last_updated = ? WHERE product_id = ?
            ''', (new_quantity, datetime.now(), product_id))
        else:
            db.execute('''
                INSERT INTO inventory (product_id, quantity) VALUES (?, ?)
            ''', (product_id, new_quantity))
        
        db.execute('''
            INSERT INTO inventory_movements 
            (product_id, movement_type, quantity_change, quantity_before, quantity_after, note)
            VALUES (?, 'ADJUSTMENT', ?, ?, ?, ?)
        ''', (product_id, quantity_change, current_quantity, new_quantity, note))
        
        db.commit()
        
        product = db.execute('SELECT name FROM products WHERE id = ?', (product_id,)).fetchone()
        flash(f'Készlet beállítva: {product["name"]} - {new_quantity}', 'success')
        
    except Exception as e:
        db.rollback()
        flash(f'Hiba történt: {str(e)}', 'danger')
    
    return redirect(url_for('inventory.list_inventory'))
