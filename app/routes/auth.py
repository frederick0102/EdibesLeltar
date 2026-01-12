"""
Autentikációs route-ok
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app import login_manager

auth_bp = Blueprint('auth', __name__)


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
        
        if password == current_app.config['APP_PASSWORD']:
            user = User('admin')
            login_user(user, remember=True)
            flash('Sikeres bejelentkezés!', 'success')
            
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        else:
            flash('Hibás jelszó!', 'danger')
    
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Kijelentkezés"""
    logout_user()
    flash('Sikeres kijelentkezés!', 'info')
    return redirect(url_for('auth.login'))
