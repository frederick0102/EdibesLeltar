"""
Edibes Leltár - Automata feltöltő leltárkezelő rendszer
"""
from flask import Flask
from flask_login import LoginManager
from app.database import init_db, get_db_session
from app.config import Config
import os

login_manager = LoginManager()

def create_app(config_class=Config):
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    app.config.from_object(config_class)
    
    # Biztosítjuk, hogy a szükséges mappák léteznek
    os.makedirs(app.config['BACKUP_DIR'], exist_ok=True)
    os.makedirs(os.path.dirname(app.config['DATABASE_PATH']), exist_ok=True)
    
    # Login manager inicializálás
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Kérjük, jelentkezzen be!'
    login_manager.login_message_category = 'warning'
    
    # Adatbázis inicializálás
    with app.app_context():
        init_db()
    
    # Blueprint-ek regisztrálása
    from app.routes.auth import auth_bp
    from app.routes.products import products_bp
    from app.routes.inventory import inventory_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.backup import backup_bp
    from app.routes.locations import locations_bp
    from app.routes.transfer import transfer_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(locations_bp)
    app.register_blueprint(transfer_bp)
    
    return app
