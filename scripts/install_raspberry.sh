#!/bin/bash
# Raspberry Pi telepítő script az Edibles Leltár alkalmazáshoz

set -e

# Színek
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  Edibles Leltár - Raspberry Pi Setup ${NC}"
echo -e "${GREEN}======================================${NC}"

# Ellenőrzés: root nem lehet
if [ "$EUID" -eq 0 ]; then 
    echo -e "${RED}Ne futtasd root-ként! Használd a normál felhasználót (pl. pi).${NC}"
    exit 1
fi

# Változók
APP_DIR="$HOME/edibles-leltar"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="edibles-leltar"

# Jelszó bekérése
echo ""
echo -e "${YELLOW}Adja meg az alkalmazás jelszavát (alapértelmezett: leltar2024):${NC}"
read -s APP_PASSWORD
APP_PASSWORD=${APP_PASSWORD:-leltar2024}

echo ""
echo -e "${YELLOW}Adja meg a titkos kulcsot (üresen hagyva automatikusan generálódik):${NC}"
read -s SECRET_KEY
if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
fi

echo ""
echo -e "${GREEN}[1/5] Rendszer frissítése...${NC}"
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv

echo ""
echo -e "${GREEN}[2/5] Alkalmazás mappa előkészítése...${NC}"
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/data"
mkdir -p "$APP_DIR/backups"

echo ""
echo -e "${GREEN}[3/5] Python virtuális környezet létrehozása...${NC}"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo ""
echo -e "${GREEN}[4/5] Python csomagok telepítése...${NC}"
pip install --upgrade pip
pip install Flask Flask-Login gunicorn

echo ""
echo -e "${GREEN}[5/5] Systemd szolgáltatás beállítása...${NC}"

# Szolgáltatás fájl létrehozása
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=Edibles Leltar Alkalmazas
After=network.target

[Service]
User=$USER
Group=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
Environment="SECRET_KEY=$SECRET_KEY"
Environment="APP_PASSWORD=$APP_PASSWORD"
ExecStart=$VENV_DIR/bin/gunicorn --workers 2 --bind 0.0.0.0:5000 wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Szolgáltatás engedélyezése
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}

echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  Telepítés befejezve!${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "Következő lépések:"
echo -e "1. Másolja az alkalmazás fájljait ide: ${YELLOW}$APP_DIR${NC}"
echo -e "2. Indítsa el a szolgáltatást: ${YELLOW}sudo systemctl start ${SERVICE_NAME}${NC}"
echo -e "3. Nyissa meg böngészőben: ${YELLOW}http://$(hostname -I | awk '{print $1}'):5000${NC}"
echo ""
echo -e "Hasznos parancsok:"
echo -e "  Státusz:  ${YELLOW}sudo systemctl status ${SERVICE_NAME}${NC}"
echo -e "  Logok:    ${YELLOW}sudo journalctl -u ${SERVICE_NAME} -f${NC}"
echo -e "  Újraind:  ${YELLOW}sudo systemctl restart ${SERVICE_NAME}${NC}"
echo -e "  Leállít:  ${YELLOW}sudo systemctl stop ${SERVICE_NAME}${NC}"
echo ""
