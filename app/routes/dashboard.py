"""
Dashboard (főoldal) route-ok
"""
from flask import Blueprint, render_template, request
from flask_login import login_required
from app.database import get_db_connection
from app.models import LocationType

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    """Főoldal - összegző felület helyszín bontással"""
    db = get_db_connection()
    
    # Összesített statisztikák
    stats = {}
    
    # Összes aktív termék száma
    result = db.execute('''
        SELECT COUNT(*) as count FROM products WHERE is_deleted = 0
    ''').fetchone()
    stats['total_products'] = result['count'] if result else 0
    
    # Összes készleten lévő termék mennyisége (location_inventory-ből)
    result = db.execute('''
        SELECT COALESCE(SUM(li.quantity), 0) as total
        FROM location_inventory li
        JOIN products p ON li.product_id = p.id
        JOIN locations l ON li.location_id = l.id
        WHERE p.is_deleted = 0 AND l.is_deleted = 0
    ''').fetchone()
    stats['total_quantity'] = result['total'] if result and result['total'] else 0
    
    # Alacsony készletű termékek (minimum szint alatt - összkészlet alapján)
    result = db.execute('''
        SELECT COUNT(*) as count
        FROM products p
        WHERE p.is_deleted = 0 
        AND (
            SELECT COALESCE(SUM(li.quantity), 0) 
            FROM location_inventory li 
            JOIN locations l ON li.location_id = l.id
            WHERE li.product_id = p.id AND l.is_deleted = 0
        ) < p.min_stock_level
    ''').fetchone()
    stats['low_stock_count'] = result['count'] if result else 0
    
    # Helyszínek száma
    result = db.execute('''
        SELECT COUNT(*) as count FROM locations WHERE is_deleted = 0 AND is_active = 1
    ''').fetchone()
    stats['location_count'] = result['count'] if result else 0
    
    # === HELYSZÍNENKÉNTI ÖSSZESÍTÉS ===
    location_stats = db.execute('''
        SELECT 
            l.id, l.name, l.location_type,
            COUNT(DISTINCT CASE WHEN li.quantity > 0 THEN li.product_id END) as product_count,
            COALESCE(SUM(li.quantity), 0) as total_quantity
        FROM locations l
        LEFT JOIN location_inventory li ON l.id = li.location_id
        LEFT JOIN products p ON li.product_id = p.id AND p.is_deleted = 0
        WHERE l.is_deleted = 0 AND l.is_active = 1
        GROUP BY l.id, l.name, l.location_type
        ORDER BY 
            CASE l.location_type 
                WHEN 'WAREHOUSE' THEN 1 
                WHEN 'CAR' THEN 2 
                WHEN 'VENDING' THEN 3 
            END, l.name
    ''').fetchall()
    
    # Kategóriánkénti összesítés
    category_stats = db.execute('''
        SELECT 
            c.name as category_name,
            COUNT(DISTINCT p.id) as product_count,
            COALESCE(SUM(li.quantity), 0) as total_quantity
        FROM categories c
        LEFT JOIN products p ON c.id = p.category_id AND p.is_deleted = 0
        LEFT JOIN location_inventory li ON p.id = li.product_id
        LEFT JOIN locations l ON li.location_id = l.id AND l.is_deleted = 0
        WHERE c.is_deleted = 0
        GROUP BY c.id, c.name
        ORDER BY c.name
    ''').fetchall()
    
    # Alacsony készletű termékek listája (összkészlet alapján)
    low_stock_products = db.execute('''
        SELECT 
            p.id, p.name as product_name,
            p.min_stock_level,
            COALESCE(total_qty.quantity, 0) as current_quantity,
            u.abbreviation as unit,
            c.name as category_name
        FROM products p
        LEFT JOIN (
            SELECT product_id, SUM(quantity) as quantity 
            FROM location_inventory li
            JOIN locations l ON li.location_id = l.id
            WHERE l.is_deleted = 0
            GROUP BY product_id
        ) total_qty ON p.id = total_qty.product_id
        LEFT JOIN units u ON p.unit_id = u.id
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_deleted = 0 
        AND COALESCE(total_qty.quantity, 0) < p.min_stock_level
        ORDER BY (COALESCE(total_qty.quantity, 0) / NULLIF(p.min_stock_level, 0)) ASC
        LIMIT 10
    ''').fetchall()
    
    # Utolsó 10 készletmozgás helyszín információval
    recent_movements = db.execute('''
        SELECT 
            im.movement_type,
            im.quantity_change,
            im.created_at,
            im.note,
            p.name as product_name,
            p.package_size,
            u.abbreviation as unit,
            l.name as location_name,
            l.location_type,
            sl.name as source_location_name,
            tl.name as target_location_name
        FROM inventory_movements im
        JOIN products p ON im.product_id = p.id
        LEFT JOIN units u ON p.unit_id = u.id
        LEFT JOIN locations l ON im.location_id = l.id
        LEFT JOIN locations sl ON im.source_location_id = sl.id
        LEFT JOIN locations tl ON im.target_location_id = tl.id
        ORDER BY im.created_at DESC
        LIMIT 10
    ''').fetchall()
    
    return render_template('dashboard.html',
                         stats=stats,
                         location_stats=location_stats,
                         category_stats=category_stats,
                         low_stock_products=low_stock_products,
                         recent_movements=recent_movements,
                         LocationType=LocationType)


@dashboard_bp.route('/audit-log')
@login_required
def audit_log():
    """Audit napló megtekintése"""
    db = get_db_connection()
    
    # Szűrési paraméterek
    action_filter = request.args.get('action', '')
    table_filter = request.args.get('table', '')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Alap lekérdezés
    query = '''
        SELECT * FROM audit_log
        WHERE 1=1
    '''
    params = []
    
    if action_filter:
        query += ' AND action = ?'
        params.append(action_filter)
    
    if table_filter:
        query += ' AND table_name = ?'
        params.append(table_filter)
    
    # Összesítés
    count_query = query.replace('SELECT *', 'SELECT COUNT(*) as cnt')
    total = db.execute(count_query, params).fetchone()['cnt']
    
    # Lapozás
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, (page - 1) * per_page])
    
    logs = db.execute(query, params).fetchall()
    
    # Egyedi akciók és táblák a szűrőhöz
    actions = db.execute('SELECT DISTINCT action FROM audit_log ORDER BY action').fetchall()
    tables = db.execute('SELECT DISTINCT table_name FROM audit_log ORDER BY table_name').fetchall()
    
    return render_template('audit_log.html',
                         logs=logs,
                         actions=actions,
                         tables=tables,
                         action_filter=action_filter,
                         table_filter=table_filter,
                         page=page,
                         per_page=per_page,
                         total=total,
                         total_pages=(total + per_page - 1) // per_page)
