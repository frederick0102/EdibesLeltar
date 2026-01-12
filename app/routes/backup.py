"""
Backup kezelési route-ok
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required
from app.database import get_db_connection
from datetime import datetime
import os
import shutil
import glob

backup_bp = Blueprint('backup', __name__, url_prefix='/backup')


def create_backup(backup_dir=None, network_backup=False):
    """Backup létrehozása"""
    if backup_dir is None:
        backup_dir = current_app.config['BACKUP_DIR']
    
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f'leltar_backup_{timestamp}.db'
    backup_path = os.path.join(backup_dir, backup_filename)
    
    # Adatbázis másolása
    source_db = current_app.config['DATABASE_PATH']
    
    if os.path.exists(source_db):
        shutil.copy2(source_db, backup_path)
        
        # Hálózati mentés ha engedélyezett
        if network_backup and current_app.config.get('NETWORK_BACKUP_PATH'):
            network_path = current_app.config['NETWORK_BACKUP_PATH']
            try:
                os.makedirs(network_path, exist_ok=True)
                network_backup_path = os.path.join(network_path, backup_filename)
                shutil.copy2(source_db, network_backup_path)
            except Exception as e:
                print(f"Hálózati mentés sikertelen: {e}")
        
        return backup_path
    
    return None


def cleanup_old_backups(backup_dir=None, retention_days=None):
    """Régi backup-ok törlése"""
    if backup_dir is None:
        backup_dir = current_app.config['BACKUP_DIR']
    if retention_days is None:
        retention_days = current_app.config['BACKUP_RETENTION_DAYS']
    
    now = datetime.now()
    
    for backup_file in glob.glob(os.path.join(backup_dir, 'leltar_backup_*.db')):
        try:
            file_time = datetime.fromtimestamp(os.path.getmtime(backup_file))
            if (now - file_time).days > retention_days:
                os.remove(backup_file)
        except Exception as e:
            print(f"Backup törlési hiba: {e}")


@backup_bp.route('/')
@login_required
def backup_page():
    """Backup kezelő oldal"""
    backup_dir = current_app.config['BACKUP_DIR']
    network_backup_path = current_app.config.get('NETWORK_BACKUP_PATH')
    
    # Helyi backup-ok listázása
    local_backups = []
    if os.path.exists(backup_dir):
        for backup_file in sorted(glob.glob(os.path.join(backup_dir, 'leltar_backup_*.db')), reverse=True):
            file_stat = os.stat(backup_file)
            local_backups.append({
                'filename': os.path.basename(backup_file),
                'path': backup_file,
                'size': file_stat.st_size,
                'created': datetime.fromtimestamp(file_stat.st_mtime)
            })
    
    # Hálózati backup-ok listázása
    network_backups = []
    network_available = False
    if network_backup_path:
        try:
            if os.path.exists(network_backup_path):
                network_available = True
                for backup_file in sorted(glob.glob(os.path.join(network_backup_path, 'leltar_backup_*.db')), reverse=True):
                    file_stat = os.stat(backup_file)
                    network_backups.append({
                        'filename': os.path.basename(backup_file),
                        'path': backup_file,
                        'size': file_stat.st_size,
                        'created': datetime.fromtimestamp(file_stat.st_mtime)
                    })
        except Exception as e:
            pass
    
    # Adatbázis méret
    db_path = current_app.config['DATABASE_PATH']
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    
    return render_template('backup/index.html',
                         local_backups=local_backups,
                         network_backups=network_backups,
                         network_backup_path=network_backup_path,
                         network_available=network_available,
                         db_size=db_size,
                         retention_days=current_app.config['BACKUP_RETENTION_DAYS'])


@backup_bp.route('/create', methods=['POST'])
@login_required
def create_backup_now():
    """Backup létrehozása most"""
    network_backup = request.form.get('network_backup', 'false') == 'true'
    
    try:
        backup_path = create_backup(network_backup=network_backup)
        if backup_path:
            flash(f'Backup sikeresen létrehozva: {os.path.basename(backup_path)}', 'success')
        else:
            flash('Backup létrehozása sikertelen - adatbázis nem található!', 'danger')
    except Exception as e:
        flash(f'Hiba történt: {str(e)}', 'danger')
    
    return redirect(url_for('backup.backup_page'))


@backup_bp.route('/download/<path:filename>')
@login_required
def download_backup(filename):
    """Backup letöltése"""
    backup_dir = current_app.config['BACKUP_DIR']
    backup_path = os.path.join(backup_dir, filename)
    
    if os.path.exists(backup_path) and filename.startswith('leltar_backup_'):
        return send_file(backup_path, as_attachment=True)
    
    flash('Backup fájl nem található!', 'danger')
    return redirect(url_for('backup.backup_page'))


@backup_bp.route('/delete/<path:filename>', methods=['POST'])
@login_required
def delete_backup(filename):
    """Backup törlése"""
    backup_dir = current_app.config['BACKUP_DIR']
    backup_path = os.path.join(backup_dir, filename)
    
    if os.path.exists(backup_path) and filename.startswith('leltar_backup_'):
        try:
            os.remove(backup_path)
            flash(f'Backup törölve: {filename}', 'success')
        except Exception as e:
            flash(f'Hiba történt: {str(e)}', 'danger')
    else:
        flash('Backup fájl nem található!', 'danger')
    
    return redirect(url_for('backup.backup_page'))


@backup_bp.route('/restore/<path:filename>', methods=['POST'])
@login_required
def restore_backup(filename):
    """Backup visszaállítása"""
    backup_dir = current_app.config['BACKUP_DIR']
    backup_path = os.path.join(backup_dir, filename)
    db_path = current_app.config['DATABASE_PATH']
    
    if os.path.exists(backup_path) and filename.startswith('leltar_backup_'):
        try:
            # Jelenlegi adatbázisról backup készítése először
            pre_restore_backup = create_backup()
            
            # Visszaállítás
            shutil.copy2(backup_path, db_path)
            
            flash(f'Backup visszaállítva: {filename}. Előző állapot mentve: {os.path.basename(pre_restore_backup)}', 'success')
        except Exception as e:
            flash(f'Hiba történt: {str(e)}', 'danger')
    else:
        flash('Backup fájl nem található!', 'danger')
    
    return redirect(url_for('backup.backup_page'))


@backup_bp.route('/cleanup', methods=['POST'])
@login_required
def cleanup_backups():
    """Régi backup-ok törlése"""
    try:
        cleanup_old_backups()
        flash('Régi backup-ok törölve!', 'success')
    except Exception as e:
        flash(f'Hiba történt: {str(e)}', 'danger')
    
    return redirect(url_for('backup.backup_page'))
