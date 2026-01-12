"""
Dashboard (főoldal) route-ok
"""
from flask import Blueprint, render_template
from flask_login import login_required
from app.database import get_db_connection

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    """Főoldal - összegző felület"""
    db = get_db_connection()
    
    # Összesített statisztikák
    stats = {}
    
    # Összes aktív termék száma
    result = db.execute('''
        SELECT COUNT(*) as count FROM products WHERE is_deleted = 0
    ''').fetchone()
    stats['total_products'] = result['count'] if result else 0
    
    # Összes készleten lévő termék mennyisége
    result = db.execute('''
        SELECT SUM(i.quantity) as total
        FROM inventory i
        JOIN products p ON i.product_id = p.id
        WHERE p.is_deleted = 0
    ''').fetchone()
    stats['total_quantity'] = result['total'] if result and result['total'] else 0
    
    # Alacsony készletű termékek (minimum szint alatt)
    result = db.execute('''
        SELECT COUNT(*) as count
        FROM inventory i
        JOIN products p ON i.product_id = p.id
        WHERE p.is_deleted = 0 AND i.quantity < p.min_stock_level
    ''').fetchone()
    stats['low_stock_count'] = result['count'] if result else 0
    
    # Kategóriánkénti összesítés
    category_stats = db.execute('''
        SELECT 
            c.name as category_name,
            COUNT(DISTINCT p.id) as product_count,
            COALESCE(SUM(i.quantity), 0) as total_quantity
        FROM categories c
        LEFT JOIN products p ON c.id = p.category_id AND p.is_deleted = 0
        LEFT JOIN inventory i ON p.id = i.product_id
        WHERE c.is_deleted = 0
        GROUP BY c.id, c.name
        ORDER BY c.name
    ''').fetchall()
    
    # Alacsony készletű termékek listája
    low_stock_products = db.execute('''
        SELECT 
            p.name as product_name,
            p.min_stock_level,
            i.quantity as current_quantity,
            u.abbreviation as unit,
            c.name as category_name
        FROM products p
        JOIN inventory i ON p.id = i.product_id
        LEFT JOIN units u ON p.unit_id = u.id
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_deleted = 0 AND i.quantity < p.min_stock_level
        ORDER BY (i.quantity / NULLIF(p.min_stock_level, 0)) ASC
        LIMIT 10
    ''').fetchall()
    
    # Utolsó 10 készletmozgás
    recent_movements = db.execute('''
        SELECT 
            im.movement_type,
            im.quantity_change,
            im.created_at,
            im.note,
            p.name as product_name,
            p.package_size,
            u.abbreviation as unit
        FROM inventory_movements im
        JOIN products p ON im.product_id = p.id
        LEFT JOIN units u ON p.unit_id = u.id
        ORDER BY im.created_at DESC
        LIMIT 10
    ''').fetchall()
    
    return render_template('dashboard.html',
                         stats=stats,
                         category_stats=category_stats,
                         low_stock_products=low_stock_products,
                         recent_movements=recent_movements)
