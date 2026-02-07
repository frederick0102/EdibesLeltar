"""
Autentikációs route-ok
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import User
from app.database import get_db_connection, log_audit
from app import login_manager

auth_bp = Blueprint('auth', __name__)


def get_app_password_hash():
    """Jelszó hash lekérdezése az adatbázisból"""
    db = get_db_connection()
    result = db.execute('SELECT value FROM settings WHERE key = ?', ('app_password',)).fetchone()
    if result:
        return result['value']
    return None


def verify_password(password):
    """Jelszó ellenőrzése a hash-elt értékkel"""
    password_hash = get_app_password_hash()
    if password_hash:
        return check_password_hash(password_hash, password)
    # Fallback az alap jelszóra (első indításkor)
    return password == current_app.config.get('APP_PASSWORD', 'leltar2024')


@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Bejelentkezési oldal"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        
        if verify_password(password):
            user = User('admin')
            login_user(user, remember=True)
            
            # Sikeres bejelentkezés naplózása
            log_audit('auth', None, 'LOGIN_SUCCESS', None, {'user': 'admin'})
            
            flash('Sikeres bejelentkezés!', 'success')
            
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        else:
            # Sikertelen bejelentkezés naplózása
            log_audit('auth', None, 'LOGIN_FAILED', None, {'reason': 'invalid_password'})
            flash('Hibás jelszó!', 'danger')
    
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Kijelentkezés"""
    # Kijelentkezés naplózása
    log_audit('auth', None, 'LOGOUT', None, {'user': current_user.id if current_user else 'unknown'})
    
    logout_user()
    flash('Sikeres kijelentkezés!', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Beállítások oldal"""
    db = get_db_connection()
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Jelenlegi jelszó ellenőrzése
        if not verify_password(current_password):
            flash('A jelenlegi jelszó hibás!', 'danger')
            return redirect(url_for('auth.settings'))
        
        # Új jelszó validálása
        if not new_password:
            flash('Az új jelszó nem lehet üres!', 'danger')
            return redirect(url_for('auth.settings'))
        
        if len(new_password) < 4:
            flash('Az új jelszónak legalább 4 karakter hosszúnak kell lennie!', 'danger')
            return redirect(url_for('auth.settings'))
        
        if new_password != confirm_password:
            flash('Az új jelszó és a megerősítés nem egyezik!', 'danger')
            return redirect(url_for('auth.settings'))
        
        # Jelszó hash-elése és frissítése
        password_hash = generate_password_hash(new_password)
        
        # Ellenőrizzük, hogy létezik-e már a beállítás
        existing = db.execute('SELECT id FROM settings WHERE key = ?', ('app_password',)).fetchone()
        if existing:
            db.execute('UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?', 
                       (password_hash, 'app_password'))
        else:
            db.execute('INSERT INTO settings (key, value) VALUES (?, ?)', 
                       ('app_password', password_hash))
        db.commit()
        
        # Jelszóváltás naplózása
        log_audit('settings', None, 'PASSWORD_CHANGE', None, {'setting': 'app_password'})
        
        flash('Jelszó sikeresen módosítva!', 'success')
        return redirect(url_for('auth.settings'))
    
    # Adatbázis fájlnév kiszámítása
    import os
    db_name = os.path.basename(current_app.config.get('DATABASE_PATH', 'leltar.db'))
    
    return render_template('settings.html', db_name=db_name)
