#!/bin/bash
# Automatikus backup script

APP_DIR="$HOME/edibles-leltar"
BACKUP_DIR="$APP_DIR/backups"
DB_FILE="$APP_DIR/data/leltar.db"
NETWORK_BACKUP_PATH="${NETWORK_BACKUP_PATH:-}"
RETENTION_DAYS=30

# Időbélyeg
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="leltar_backup_${TIMESTAMP}.db"

# Ellenőrzés
if [ ! -f "$DB_FILE" ]; then
    echo "Adatbázis nem található: $DB_FILE"
    exit 1
fi

# Helyi backup
mkdir -p "$BACKUP_DIR"
cp "$DB_FILE" "$BACKUP_DIR/$BACKUP_FILE"
echo "Helyi backup létrehozva: $BACKUP_DIR/$BACKUP_FILE"

# Hálózati backup (ha be van állítva)
if [ -n "$NETWORK_BACKUP_PATH" ] && [ -d "$NETWORK_BACKUP_PATH" ]; then
    cp "$DB_FILE" "$NETWORK_BACKUP_PATH/$BACKUP_FILE"
    echo "Hálózati backup létrehozva: $NETWORK_BACKUP_PATH/$BACKUP_FILE"
fi

# Régi backup-ok törlése
find "$BACKUP_DIR" -name "leltar_backup_*.db" -mtime +$RETENTION_DAYS -delete
echo "Régi backup-ok törölve (${RETENTION_DAYS} napnál régebbiek)"

if [ -n "$NETWORK_BACKUP_PATH" ] && [ -d "$NETWORK_BACKUP_PATH" ]; then
    find "$NETWORK_BACKUP_PATH" -name "leltar_backup_*.db" -mtime +$RETENTION_DAYS -delete
fi

echo "Backup kész!"
