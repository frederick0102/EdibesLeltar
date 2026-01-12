"""
Termék törzsadatok kezelése
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app.database import get_db_connection, log_audit
from datetime import datetime
import json

products_bp = Blueprint('products', __name__, url_prefix='/products')


@products_bp.route('/')
@login_required
def list_products():
    """Termékek listázása"""
    db = get_db_connection()
    
    # Szűrési paraméterek
    search = request.args.get('search', '')
    category_id = request.args.get('category', '')
    show_deleted = request.args.get('show_deleted', 'false') == 'true'
    
    # Alap lekérdezés
    query = '''
        SELECT 
            p.id, p.name, p.barcode, p.description, p.package_size, p.min_stock_level,
            p.created_at, p.updated_at, p.is_deleted,
            c.name as category_name, c.id as category_id,
            u.name as unit_name, u.abbreviation as unit_abbr, u.id as unit_id,
            COALESCE(i.quantity, 0) as current_quantity
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN units u ON p.unit_id = u.id
        LEFT JOIN inventory i ON p.id = i.product_id
        WHERE 1=1
    '''
    params = []
    
    if not show_deleted:
        query += ' AND p.is_deleted = 0'
    
    if search:
        query += ' AND (p.name LIKE ? OR p.barcode LIKE ? OR p.description LIKE ?)'
        search_pattern = f'%{search}%'
        params.extend([search_pattern, search_pattern, search_pattern])
    
    if category_id:
        query += ' AND p.category_id = ?'
        params.append(category_id)
    
    query += ' ORDER BY p.name'
    
    products = db.execute(query, params).fetchall()
    
    # Kategóriák a szűrőhöz
    categories = db.execute('''
        SELECT id, name FROM categories WHERE is_deleted = 0 ORDER BY name
    ''').fetchall()
    
    # Mértékegységek az űrlaphoz
    units = db.execute('''
        SELECT id, name, abbreviation FROM units WHERE is_deleted = 0 ORDER BY name
    ''').fetchall()
    
    return render_template('products/list.html',
                         products=products,
                         categories=categories,
                         units=units,
                         search=search,
                         selected_category=category_id,
                         show_deleted=show_deleted)


@products_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_product():
    """Új termék hozzáadása"""
    db = get_db_connection()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category_id = request.form.get('category_id') or None
        unit_id = request.form.get('unit_id') or None
        barcode = request.form.get('barcode', '').strip() or None
        description = request.form.get('description', '').strip() or None
        package_size = request.form.get('package_size', '').strip() or None
        min_stock_level = float(request.form.get('min_stock_level', 0) or 0)
        initial_quantity = float(request.form.get('initial_quantity', 0) or 0)
        
        if not name:
            flash('A termék neve kötelező!', 'danger')
            return redirect(url_for('products.add_product'))
        
        # Vonalkód egyediség ellenőrzése
        if barcode:
            existing = db.execute(
                'SELECT id FROM products WHERE barcode = ? AND is_deleted = 0',
                (barcode,)
            ).fetchone()
            if existing:
                flash('Ez a vonalkód már létezik!', 'danger')
                return redirect(url_for('products.add_product'))
        
        try:
            cursor = db.execute('''
                INSERT INTO products (name, category_id, unit_id, barcode, description, package_size, min_stock_level)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, category_id, unit_id, barcode, description, package_size, min_stock_level))
            
            product_id = cursor.lastrowid
            
            # Készlet inicializálása
            db.execute('''
                INSERT INTO inventory (product_id, quantity) VALUES (?, ?)
            ''', (product_id, initial_quantity))
            
            # Kezdőkészlet mozgás rögzítése ha van mennyiség
            if initial_quantity > 0:
                db.execute('''
                    INSERT INTO inventory_movements 
                    (product_id, movement_type, quantity_change, quantity_before, quantity_after, note)
                    VALUES (?, 'INITIAL', ?, 0, ?, 'Kezdőkészlet felvitele')
                ''', (product_id, initial_quantity, initial_quantity))
            
            # Audit log
            log_audit('products', product_id, 'INSERT', None, {
                'name': name, 'category_id': category_id, 'unit_id': unit_id,
                'barcode': barcode, 'package_size': package_size, 'min_stock_level': min_stock_level
            })
            
            db.commit()
            flash(f'Termék sikeresen létrehozva: {name}', 'success')
            return redirect(url_for('products.list_products'))
            
        except Exception as e:
            db.rollback()
            flash(f'Hiba történt: {str(e)}', 'danger')
    
    # Kategóriák és egységek az űrlaphoz
    categories = db.execute('''
        SELECT id, name FROM categories WHERE is_deleted = 0 ORDER BY name
    ''').fetchall()
    
    units = db.execute('''
        SELECT id, name, abbreviation FROM units WHERE is_deleted = 0 ORDER BY name
    ''').fetchall()
    
    return render_template('products/form.html',
                         categories=categories,
                         units=units,
                         product=None,
                         title='Új termék')


@products_bp.route('/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    """Termék szerkesztése"""
    db = get_db_connection()
    
    product = db.execute('''
        SELECT p.*, i.quantity as current_quantity
        FROM products p
        LEFT JOIN inventory i ON p.id = i.product_id
        WHERE p.id = ?
    ''', (product_id,)).fetchone()
    
    if not product:
        flash('Termék nem található!', 'danger')
        return redirect(url_for('products.list_products'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category_id = request.form.get('category_id') or None
        unit_id = request.form.get('unit_id') or None
        barcode = request.form.get('barcode', '').strip() or None
        description = request.form.get('description', '').strip() or None
        package_size = request.form.get('package_size', '').strip() or None
        min_stock_level = float(request.form.get('min_stock_level', 0) or 0)
        
        if not name:
            flash('A termék neve kötelező!', 'danger')
            return redirect(url_for('products.edit_product', product_id=product_id))
        
        # Vonalkód egyediség ellenőrzése (kivéve saját magát)
        if barcode:
            existing = db.execute(
                'SELECT id FROM products WHERE barcode = ? AND id != ? AND is_deleted = 0',
                (barcode, product_id)
            ).fetchone()
            if existing:
                flash('Ez a vonalkód már létezik!', 'danger')
                return redirect(url_for('products.edit_product', product_id=product_id))
        
        old_values = dict(product)
        
        try:
            db.execute('''
                UPDATE products 
                SET name = ?, category_id = ?, unit_id = ?, barcode = ?, 
                    description = ?, package_size = ?, min_stock_level = ?, updated_at = ?
                WHERE id = ?
            ''', (name, category_id, unit_id, barcode, description, 
                  package_size, min_stock_level, datetime.now(), product_id))
            
            # Audit log
            log_audit('products', product_id, 'UPDATE', old_values, {
                'name': name, 'category_id': category_id, 'unit_id': unit_id,
                'barcode': barcode, 'package_size': package_size, 'min_stock_level': min_stock_level
            })
            
            db.commit()
            flash(f'Termék sikeresen módosítva: {name}', 'success')
            return redirect(url_for('products.list_products'))
            
        except Exception as e:
            db.rollback()
            flash(f'Hiba történt: {str(e)}', 'danger')
    
    # Kategóriák és egységek az űrlaphoz
    categories = db.execute('''
        SELECT id, name FROM categories WHERE is_deleted = 0 ORDER BY name
    ''').fetchall()
    
    units = db.execute('''
        SELECT id, name, abbreviation FROM units WHERE is_deleted = 0 ORDER BY name
    ''').fetchall()
    
    return render_template('products/form.html',
                         categories=categories,
                         units=units,
                         product=product,
                         title='Termék szerkesztése')


@products_bp.route('/delete/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    """Termék törlése (soft delete)"""
    db = get_db_connection()
    
    product = db.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    
    if not product:
        flash('Termék nem található!', 'danger')
        return redirect(url_for('products.list_products'))
    
    try:
        db.execute('''
            UPDATE products 
            SET is_deleted = 1, deleted_at = ?, updated_at = ?
            WHERE id = ?
        ''', (datetime.now(), datetime.now(), product_id))
        
        # Audit log
        log_audit('products', product_id, 'SOFT_DELETE', dict(product), None)
        
        db.commit()
        flash(f'Termék törölve: {product["name"]}', 'success')
        
    except Exception as e:
        db.rollback()
        flash(f'Hiba történt: {str(e)}', 'danger')
    
    return redirect(url_for('products.list_products'))


@products_bp.route('/restore/<int:product_id>', methods=['POST'])
@login_required
def restore_product(product_id):
    """Törölt termék visszaállítása"""
    db = get_db_connection()
    
    product = db.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    
    if not product:
        flash('Termék nem található!', 'danger')
        return redirect(url_for('products.list_products'))
    
    try:
        db.execute('''
            UPDATE products 
            SET is_deleted = 0, deleted_at = NULL, updated_at = ?
            WHERE id = ?
        ''', (datetime.now(), product_id))
        
        # Audit log
        log_audit('products', product_id, 'RESTORE', None, dict(product))
        
        db.commit()
        flash(f'Termék visszaállítva: {product["name"]}', 'success')
        
    except Exception as e:
        db.rollback()
        flash(f'Hiba történt: {str(e)}', 'danger')
    
    return redirect(url_for('products.list_products'))


@products_bp.route('/api/barcode/<barcode>')
@login_required
def get_by_barcode(barcode):
    """Termék keresése vonalkód alapján (API)"""
    db = get_db_connection()
    
    product = db.execute('''
        SELECT 
            p.id, p.name, p.barcode, p.description, p.min_stock_level,
            c.name as category_name,
            u.abbreviation as unit_abbr,
            COALESCE(i.quantity, 0) as current_quantity
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN units u ON p.unit_id = u.id
        LEFT JOIN inventory i ON p.id = i.product_id
        WHERE p.barcode = ? AND p.is_deleted = 0
    ''', (barcode,)).fetchone()
    
    if product:
        return jsonify({
            'success': True,
            'product': dict(product)
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Termék nem található'
        }), 404


# ============ Kategóriák kezelése ============

@products_bp.route('/categories')
@login_required
def list_categories():
    """Kategóriák listázása"""
    db = get_db_connection()
    
    show_deleted = request.args.get('show_deleted', 'false') == 'true'
    
    query = 'SELECT * FROM categories'
    if not show_deleted:
        query += ' WHERE is_deleted = 0'
    query += ' ORDER BY name'
    
    categories = db.execute(query).fetchall()
    
    return render_template('products/categories.html',
                         categories=categories,
                         show_deleted=show_deleted)


@products_bp.route('/categories/add', methods=['POST'])
@login_required
def add_category():
    """Új kategória hozzáadása"""
    db = get_db_connection()
    
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip() or None
    
    if not name:
        flash('A kategória neve kötelező!', 'danger')
        return redirect(url_for('products.list_categories'))
    
    try:
        cursor = db.execute('''
            INSERT INTO categories (name, description) VALUES (?, ?)
        ''', (name, description))
        
        log_audit('categories', cursor.lastrowid, 'INSERT', None, {'name': name, 'description': description})
        
        db.commit()
        flash(f'Kategória létrehozva: {name}', 'success')
        
    except Exception as e:
        db.rollback()
        flash(f'Hiba történt: {str(e)}', 'danger')
    
    return redirect(url_for('products.list_categories'))


@products_bp.route('/categories/delete/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    """Kategória törlése (soft delete)"""
    db = get_db_connection()
    
    category = db.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()
    
    if not category:
        flash('Kategória nem található!', 'danger')
        return redirect(url_for('products.list_categories'))
    
    try:
        db.execute('''
            UPDATE categories 
            SET is_deleted = 1, deleted_at = ?, updated_at = ?
            WHERE id = ?
        ''', (datetime.now(), datetime.now(), category_id))
        
        log_audit('categories', category_id, 'SOFT_DELETE', dict(category), None)
        
        db.commit()
        flash(f'Kategória törölve: {category["name"]}', 'success')
        
    except Exception as e:
        db.rollback()
        flash(f'Hiba történt: {str(e)}', 'danger')
    
    return redirect(url_for('products.list_categories'))


# ============ Mértékegységek kezelése ============

@products_bp.route('/units')
@login_required
def list_units():
    """Mértékegységek listázása"""
    db = get_db_connection()
    
    show_deleted = request.args.get('show_deleted', 'false') == 'true'
    
    query = 'SELECT * FROM units'
    if not show_deleted:
        query += ' WHERE is_deleted = 0'
    query += ' ORDER BY name'
    
    units = db.execute(query).fetchall()
    
    return render_template('products/units.html',
                         units=units,
                         show_deleted=show_deleted)


@products_bp.route('/units/add', methods=['POST'])
@login_required
def add_unit():
    """Új mértékegység hozzáadása"""
    db = get_db_connection()
    
    name = request.form.get('name', '').strip()
    abbreviation = request.form.get('abbreviation', '').strip()
    
    if not name or not abbreviation:
        flash('A mértékegység neve és rövidítése kötelező!', 'danger')
        return redirect(url_for('products.list_units'))
    
    try:
        cursor = db.execute('''
            INSERT INTO units (name, abbreviation) VALUES (?, ?)
        ''', (name, abbreviation))
        
        log_audit('units', cursor.lastrowid, 'INSERT', None, {'name': name, 'abbreviation': abbreviation})
        
        db.commit()
        flash(f'Mértékegység létrehozva: {name}', 'success')
        
    except Exception as e:
        db.rollback()
        flash(f'Hiba történt: {str(e)}', 'danger')
    
    return redirect(url_for('products.list_units'))


@products_bp.route('/units/delete/<int:unit_id>', methods=['POST'])
@login_required
def delete_unit(unit_id):
    """Mértékegység törlése (soft delete)"""
    db = get_db_connection()
    
    unit = db.execute('SELECT * FROM units WHERE id = ?', (unit_id,)).fetchone()
    
    if not unit:
        flash('Mértékegység nem található!', 'danger')
        return redirect(url_for('products.list_units'))
    
    try:
        db.execute('''
            UPDATE units 
            SET is_deleted = 1, deleted_at = ?, updated_at = ?
            WHERE id = ?
        ''', (datetime.now(), datetime.now(), unit_id))
        
        log_audit('units', unit_id, 'SOFT_DELETE', dict(unit), None)
        
        db.commit()
        flash(f'Mértékegység törölve: {unit["name"]}', 'success')
        
    except Exception as e:
        db.rollback()
        flash(f'Hiba történt: {str(e)}', 'danger')
    
    return redirect(url_for('products.list_units'))
