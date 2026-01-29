"""
Helyszínkezelési route-ok
Raktár, Autó, Automata CRUD és készlet áttekintés
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app.database import get_db_connection, log_audit
from app.models import LocationType
from datetime import datetime

locations_bp = Blueprint('locations', __name__, url_prefix='/locations')


@locations_bp.route('/')
@login_required
def list_locations():
    """Helyszínek listázása"""
    db = get_db_connection()
    
    # Szűrési paraméterek
    location_type = request.args.get('type', '')
    show_deleted = request.args.get('deleted', '') == '1'
    
    query = '''
        SELECT 
            l.*,
            (SELECT COUNT(*) FROM location_inventory li WHERE li.location_id = l.id AND li.quantity > 0) as product_count,
            (SELECT COALESCE(SUM(li.quantity), 0) FROM location_inventory li WHERE li.location_id = l.id) as total_quantity
        FROM locations l
        WHERE 1=1
    '''
    params = []
    
    if not show_deleted:
        query += ' AND l.is_deleted = 0'
    
    if location_type:
        query += ' AND l.location_type = ?'
        params.append(location_type)
    
    query += ' ORDER BY l.location_type, l.name'
    
    locations = db.execute(query, params).fetchall()
    
    return render_template('locations/list.html',
                         locations=locations,
                         location_types=LocationType.choices(),
                         selected_type=location_type,
                         show_deleted=show_deleted,
                         LocationType=LocationType)


@locations_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_location():
    """Új helyszín létrehozása"""
    db = get_db_connection()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        location_type = request.form.get('location_type')
        description = request.form.get('description', '').strip() or None
        address = request.form.get('address', '').strip() or None
        
        if not name or not location_type:
            flash('A név és a típus megadása kötelező!', 'danger')
            return redirect(url_for('locations.create_location'))
        
        if location_type not in ['WAREHOUSE', 'CAR', 'VENDING']:
            flash('Érvénytelen helyszín típus!', 'danger')
            return redirect(url_for('locations.create_location'))
        
        try:
            cursor = db.execute('''
                INSERT INTO locations (name, location_type, description, address)
                VALUES (?, ?, ?, ?)
            ''', (name, location_type, description, address))
            db.commit()
            
            log_audit('locations', cursor.lastrowid, 'CREATE', None, 
                     {'name': name, 'location_type': location_type})
            
            flash(f'Helyszín létrehozva: {name}', 'success')
            return redirect(url_for('locations.list_locations'))
            
        except Exception as e:
            db.rollback()
            flash(f'Hiba történt: {str(e)}', 'danger')
    
    return render_template('locations/form.html',
                         location=None,
                         location_types=LocationType.choices(),
                         LocationType=LocationType)


@locations_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_location(id):
    """Helyszín szerkesztése"""
    db = get_db_connection()
    
    location = db.execute('SELECT * FROM locations WHERE id = ?', (id,)).fetchone()
    if not location:
        flash('Helyszín nem található!', 'danger')
        return redirect(url_for('locations.list_locations'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip() or None
        address = request.form.get('address', '').strip() or None
        is_active = request.form.get('is_active') == '1'
        
        if not name:
            flash('A név megadása kötelező!', 'danger')
            return redirect(url_for('locations.edit_location', id=id))
        
        try:
            old_values = dict(location)
            
            db.execute('''
                UPDATE locations 
                SET name = ?, description = ?, address = ?, is_active = ?, 
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (name, description, address, 1 if is_active else 0, id))
            db.commit()
            
            log_audit('locations', id, 'UPDATE', old_values, 
                     {'name': name, 'is_active': is_active})
            
            flash('Helyszín frissítve!', 'success')
            return redirect(url_for('locations.list_locations'))
            
        except Exception as e:
            db.rollback()
            flash(f'Hiba történt: {str(e)}', 'danger')
    
    return render_template('locations/form.html',
                         location=location,
                         location_types=LocationType.choices(),
                         LocationType=LocationType)


@locations_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete_location(id):
    """Helyszín törlése (soft delete)"""
    db = get_db_connection()
    
    location = db.execute('SELECT * FROM locations WHERE id = ?', (id,)).fetchone()
    if not location:
        flash('Helyszín nem található!', 'danger')
        return redirect(url_for('locations.list_locations'))
    
    # Ellenőrizzük, van-e készlet a helyszínen
    stock = db.execute('''
        SELECT SUM(quantity) as total FROM location_inventory WHERE location_id = ?
    ''', (id,)).fetchone()
    
    if stock and stock['total'] and stock['total'] > 0:
        flash('A helyszín nem törölhető, mert van rajta készlet!', 'danger')
        return redirect(url_for('locations.list_locations'))
    
    try:
        db.execute('''
            UPDATE locations 
            SET is_deleted = 1, deleted_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (id,))
        db.commit()
        
        log_audit('locations', id, 'DELETE', dict(location), None)
        
        flash('Helyszín törölve!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Hiba történt: {str(e)}', 'danger')
    
    return redirect(url_for('locations.list_locations'))


@locations_bp.route('/<int:id>/restore', methods=['POST'])
@login_required
def restore_location(id):
    """Törölt helyszín visszaállítása"""
    db = get_db_connection()
    
    try:
        db.execute('''
            UPDATE locations 
            SET is_deleted = 0, deleted_at = NULL, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (id,))
        db.commit()
        
        flash('Helyszín visszaállítva!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Hiba történt: {str(e)}', 'danger')
    
    return redirect(url_for('locations.list_locations', deleted='1'))


@locations_bp.route('/<int:id>/inventory')
@login_required
def location_inventory(id):
    """Helyszín készletének megtekintése"""
    db = get_db_connection()
    
    location = db.execute('SELECT * FROM locations WHERE id = ?', (id,)).fetchone()
    if not location:
        flash('Helyszín nem található!', 'danger')
        return redirect(url_for('locations.list_locations'))
    
    # Készlet lekérdezése
    inventory = db.execute('''
        SELECT 
            li.*,
            p.name as product_name,
            p.barcode,
            p.package_size,
            c.name as category_name,
            u.abbreviation as unit_abbr
        FROM location_inventory li
        JOIN products p ON li.product_id = p.id
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN units u ON p.unit_id = u.id
        WHERE li.location_id = ? AND p.is_deleted = 0
        ORDER BY c.name, p.name
    ''', (id,)).fetchall()
    
    # Utolsó mozgások
    movements = db.execute('''
        SELECT 
            m.*,
            p.name as product_name,
            sl.name as source_location_name,
            tl.name as target_location_name
        FROM inventory_movements m
        JOIN products p ON m.product_id = p.id
        LEFT JOIN locations sl ON m.source_location_id = sl.id
        LEFT JOIN locations tl ON m.target_location_id = tl.id
        WHERE m.location_id = ? OR m.source_location_id = ? OR m.target_location_id = ?
        ORDER BY m.created_at DESC
        LIMIT 20
    ''', (id, id, id)).fetchall()
    
    return render_template('locations/inventory.html',
                         location=location,
                         inventory=inventory,
                         movements=movements,
                         LocationType=LocationType)


@locations_bp.route('/api/list')
@login_required
def api_list_locations():
    """API: Helyszínek listája (AJAX-hoz)"""
    db = get_db_connection()
    
    location_type = request.args.get('type', '')
    
    query = '''
        SELECT id, name, location_type FROM locations 
        WHERE is_deleted = 0 AND is_active = 1
    '''
    params = []
    
    if location_type:
        query += ' AND location_type = ?'
        params.append(location_type)
    
    query += ' ORDER BY name'
    
    locations = db.execute(query, params).fetchall()
    
    return jsonify({
        'success': True,
        'locations': [dict(loc) for loc in locations]
    })
