"""
Készletkezelési route-ok
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app.database import get_db_connection, log_audit
from app.models import MovementType
from datetime import datetime, timedelta

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')


@inventory_bp.route('/')
@login_required
def list_inventory():
    """Készlet listázása"""
    db = get_db_connection()
    
    # Szűrési paraméterek
    search = request.args.get('search', '')
    category_id = request.args.get('category', '')
    stock_filter = request.args.get('stock', '')  # 'low', 'zero', 'all'
    
    query = '''
        SELECT 
            p.id, p.name, p.barcode, p.package_size, p.min_stock_level,
            c.name as category_name,
            u.abbreviation as unit_abbr,
            COALESCE(i.quantity, 0) as current_quantity,
            i.last_updated
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN units u ON p.unit_id = u.id
        LEFT JOIN inventory i ON p.id = i.product_id
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
    
    if stock_filter == 'low':
        query += ' AND i.quantity < p.min_stock_level AND i.quantity > 0'
    elif stock_filter == 'zero':
        query += ' AND (i.quantity = 0 OR i.quantity IS NULL)'
    
    query += ' ORDER BY p.name'
    
    inventory = db.execute(query, params).fetchall()
    
    # Kategóriák a szűrőhöz
    categories = db.execute('''
        SELECT id, name FROM categories WHERE is_deleted = 0 ORDER BY name
    ''').fetchall()
    
    return render_template('inventory/list.html',
                         inventory=inventory,
                         categories=categories,
                         search=search,
                         selected_category=category_id,
                         stock_filter=stock_filter)


@inventory_bp.route('/movement', methods=['GET', 'POST'])
@login_required
def add_movement():
    """Készletmozgás rögzítése"""
    db = get_db_connection()
    
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        movement_type = request.form.get('movement_type')
        quantity = float(request.form.get('quantity', 0))
        note = request.form.get('note', '').strip() or None
        
        if not product_id or not movement_type or quantity <= 0:
            flash('Minden mező kitöltése kötelező és a mennyiségnek pozitívnak kell lennie!', 'danger')
            return redirect(url_for('inventory.add_movement'))
        
        # Aktuális készlet lekérdezése
        current = db.execute('''
            SELECT quantity FROM inventory WHERE product_id = ?
        ''', (product_id,)).fetchone()
        
        current_quantity = current['quantity'] if current else 0
        
        # Mennyiség számítása a mozgás típusa alapján
        if movement_type in ['STOCK_OUT', 'LOSS']:
            quantity_change = -quantity
        else:
            quantity_change = quantity
        
        new_quantity = current_quantity + quantity_change
        
        # Negatív készlet ellenőrzés
        if new_quantity < 0:
            flash(f'Nincs elegendő készlet! Jelenlegi: {current_quantity}', 'danger')
            return redirect(url_for('inventory.add_movement'))
        
        try:
            # Készlet frissítése
            if current:
                db.execute('''
                    UPDATE inventory SET quantity = ?, last_updated = ? WHERE product_id = ?
                ''', (new_quantity, datetime.now(), product_id))
            else:
                db.execute('''
                    INSERT INTO inventory (product_id, quantity) VALUES (?, ?)
                ''', (product_id, new_quantity))
            
            # Mozgás rögzítése
            db.execute('''
                INSERT INTO inventory_movements 
                (product_id, movement_type, quantity_change, quantity_before, quantity_after, note)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (product_id, movement_type, quantity_change, current_quantity, new_quantity, note))
            
            db.commit()
            
            # Termék neve a visszajelzéshez
            product = db.execute('SELECT name FROM products WHERE id = ?', (product_id,)).fetchone()
            
            flash(f'Készletmozgás rögzítve: {product["name"]} - {MovementType.get_label(movement_type)}', 'success')
            return redirect(url_for('inventory.list_inventory'))
            
        except Exception as e:
            db.rollback()
            flash(f'Hiba történt: {str(e)}', 'danger')
    
    # Termékek az űrlaphoz
    products = db.execute('''
        SELECT p.id, p.name, p.barcode, p.package_size, u.abbreviation as unit_abbr,
               COALESCE(i.quantity, 0) as current_quantity
        FROM products p
        LEFT JOIN units u ON p.unit_id = u.id
        LEFT JOIN inventory i ON p.id = i.product_id
        WHERE p.is_deleted = 0
        ORDER BY p.name
    ''').fetchall()
    
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
    
    if barcode:
        product = db.execute('''
            SELECT id FROM products WHERE barcode = ? AND is_deleted = 0
        ''', (barcode,)).fetchone()
        if product:
            selected_product_id = product['id']
    
    return render_template('inventory/movement.html',
                         products=products,
                         movement_types=movement_types,
                         selected_product_id=selected_product_id,
                         barcode=barcode)


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
    """Készletmozgások története"""
    db = get_db_connection()
    
    # Szűrési paraméterek
    product_id = request.args.get('product', '')
    movement_type = request.args.get('type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = '''
        SELECT 
            im.id, im.movement_type, im.quantity_change, 
            im.quantity_before, im.quantity_after, im.note, im.created_at,
            p.name as product_name, p.id as product_id, p.package_size,
            u.abbreviation as unit_abbr
        FROM inventory_movements im
        JOIN products p ON im.product_id = p.id
        LEFT JOIN units u ON p.unit_id = u.id
        WHERE 1=1
    '''
    params = []
    
    if product_id:
        query += ' AND im.product_id = ?'
        params.append(product_id)
    
    if movement_type:
        query += ' AND im.movement_type = ?'
        params.append(movement_type)
    
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
    
    movement_types = [
        ('STOCK_IN', 'Bevételezés'),
        ('STOCK_OUT', 'Kivételezés'),
        ('RETURN', 'Visszavétel'),
        ('ADJUSTMENT', 'Korrekció'),
        ('INITIAL', 'Kezdőkészlet'),
        ('LOSS', 'Selejt/Veszteség')
    ]
    
    return render_template('inventory/history.html',
                         movements=movements,
                         products=products,
                         movement_types=movement_types,
                         selected_product=product_id,
                         selected_type=movement_type,
                         date_from=date_from,
                         date_to=date_to,
                         MovementType=MovementType)


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
