# Edibles Leltár

Automata feltöltő készletkezelő rendszer - üdítő, szendvics, csoki és egyéb termékeket kiszolgáló automaták leltárkezelésére.

## 🚀 Új: Multi-Location Supply Chain

A rendszer támogatja a több helyszínes készletkezelést a teljes ellátási lánc mentén:

```
[Beszállító] ──BESZERZÉS──► [Raktár] ──FELTÖLTÉS──► [Autó] ──FOGYASZTÁS──► [Automata]
```

### Helyszín típusok
- **🏭 Raktár (Warehouse):** Központi tárhely, ide érkeznek a beszerzések
- **🚚 Autó (Car):** Mobil egység, amely a raktárból viszi a termékeket
- **📦 Automata (Vending):** Végpont, ahová az autóból töltjük fel a készletet

### Atomi tranzakciók
Minden áthelyezés egy tranzakcióban történik - a forrásból csökken, a célba növekszik. Nincs "köztes állapot".

### Kompenzáló tranzakciók
Hibás mozgás esetén nem törlünk, hanem ellentétes mozgást hozunk létre (audit trail megőrzése).

## Funkciók

### 📦 Készletkezelés
- **Multi-location készletnyilvántartás** - termék × helyszín
- Termékek nyilvántartása kategóriákkal és mértékegységekkel
- **Mobil vonalkód olvasó** (html5-qrcode) - kamerával működik
- Készletmozgások rögzítése (bevételezés, kivételezés, áthelyezés, korrekció, selejt)
- Gyors +/- gombok az azonnali készletváltozáshoz
- Minimum készletszint riasztás helyszínenként

### 🔄 Áthelyezések
- Raktár → Autó feltöltés
- Autó → Automata töltés (mobil-optimalizált UI)
- Gyors vonalkódos áthelyezés
- Áthelyezés történet és visszavonás

### 📊 Összegző felület
- Áttekintő dashboard a készletállapotról
- Helyszínenkénti összesítések
- Kategóriánkénti összesítések
- Alacsony készletű termékek kiemelése
- Utolsó mozgások listája

### 📝 Törzsadatok
- Termékek kezelése (CRUD)
- Kategóriák kezelése
- Mértékegységek kezelése
- **Helyszínek kezelése** (raktár, autó, automata)
- Soft delete - törölt elemek visszaállíthatók

### 🔒 Biztonság
- Hash-elt jelszó (PBKDF2-SHA256)
- Session alapú autentikáció
- Helyi hálózaton működik (VPN támogatás)

### 💾 Adatbiztonság
- SQLite adatbázis **WAL móddal** (biztonságos SD kártyán)
- Minden változás naplózása (audit log)
- **Kompenzáló tranzakciók** (soha nem törlünk)
- Manuális és automatikus backup
- Hálózati mentési lehetőség

## Telepítés

### Előfeltételek

- Python 3.9+
- pip

### Telepítési lépések

1. **Klónozza a repót vagy másolja a fájlokat:**
```bash
git clone <repo-url>
cd EdibesLeltar
```

2. **Virtuális környezet létrehozása (ajánlott):**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# vagy Windows-on:
venv\Scripts\activate
```

3. **Függőségek telepítése:**
```bash
pip install -r requirements.txt
```

4. **Környezeti változók beállítása (opcionális):**
```bash
# Linux/Mac
export SECRET_KEY="sajat-titkos-kulcs"
export APP_PASSWORD="sajat-jelszo"
export NETWORK_BACKUP_PATH="/mnt/backup/leltar"

# Windows
set SECRET_KEY=sajat-titkos-kulcs
set APP_PASSWORD=sajat-jelszo
set NETWORK_BACKUP_PATH=\\server\share\backup
```

5. **Alkalmazás indítása (fejlesztési mód):**
```bash
python run.py
```

6. **Böngészőben nyissa meg:**
```
http://localhost:5000
```

### Alapértelmezett bejelentkezési adatok

- **Jelszó:** `leltar2024`

> ⚠️ **Fontos:** Production környezetben változtassa meg a jelszót az `APP_PASSWORD` környezeti változóval!

## Raspberry Pi telepítés

### Raspbian előkészítése

```bash
# Frissítések
sudo apt update && sudo apt upgrade -y

# Python és pip
sudo apt install python3 python3-pip python3-venv -y
```

### Alkalmazás telepítése

```bash
# Alkalmazás mappa
cd /home/pi
mkdir edibles-leltar
cd edibles-leltar

# Fájlok másolása (vagy git clone)
# ...

# Virtuális környezet
python3 -m venv venv
source venv/bin/activate

# Függőségek
pip install -r requirements.txt
```

### Systemd szolgáltatás beállítása

1. **Szolgáltatás fájl létrehozása:**
```bash
sudo nano /etc/systemd/system/edibles-leltar.service
```

2. **Tartalma:**
```ini
[Unit]
Description=Edibles Leltár Alkalmazás
After=network.target

[Service]
User=pi
Group=pi
WorkingDirectory=/home/pi/edibles-leltar
Environment="PATH=/home/pi/edibles-leltar/venv/bin"
Environment="SECRET_KEY=change-this-secret-key"
Environment="APP_PASSWORD=change-this-password"
ExecStart=/home/pi/edibles-leltar/venv/bin/gunicorn --workers 2 --bind 0.0.0.0:5000 wsgi:app

[Install]
WantedBy=multi-user.target
```

3. **Szolgáltatás engedélyezése és indítása:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable edibles-leltar
sudo systemctl start edibles-leltar
```

4. **Státusz ellenőrzése:**
```bash
sudo systemctl status edibles-leltar
```

### Hálózati hozzáférés

Az alkalmazás a `0.0.0.0:5000` címen figyel, így a helyi hálózaton bármely eszközről elérhető:

```
http://<raspberry-pi-ip>:5000
```

A Raspberry Pi IP címét a következő paranccsal tudja lekérdezni:
```bash
hostname -I
```

## 🐳 Docker telepítés (ajánlott Raspberry Pi-re)

A Docker telepítés egyszerűbb és könnyebben karbantartható, mint a manuális telepítés.

### Docker előfeltételek

```bash
# Docker telepítése Raspberry Pi-re
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Docker Compose telepítése (ha nincs)
sudo apt install docker-compose-plugin -y

# Felhasználó hozzáadása a docker csoporthoz (újraindítás szükséges)
sudo usermod -aG docker $USER
```

### Gyors telepítés Dockerrel

```bash
# Repository klónozása
git clone <repo-url>
cd EdibesLeltar

# Titkos kulcs beállítása (opcionális de ajánlott)
cp .env.example .env
nano .env  # SECRET_KEY és APP_PASSWORD módosítása

# Container indítása
docker compose up -d

# Ellenőrzés
docker compose ps
docker compose logs -f
```

### Elérés

```
http://<raspberry-pi-ip>:5000
```

### Docker parancsok

```bash
# Logok megtekintése
docker compose logs -f

# Container újraindítása
docker compose restart

# Container leállítása
docker compose down

# Container frissítése (új verzió telepítése)
./update.sh
```

### Frissítés

A mellékelt `update.sh` script automatikusan frissíti az alkalmazást:

```bash
chmod +x update.sh
./update.sh
```

Ez a script:
1. Letölti a legújabb változásokat Git-ből
2. Újraépíti a Docker containert
3. Törli a régi image-eket (helytakarékosság)

### Docker adatmegőrzés

A következő mappák a host-on maradnak (nem vesznek el container újraépítéskor):
- `./data/` - SQLite adatbázis
- `./backups/` - Backup fájlok

## Backup

### Manuális backup

1. Jelentkezzen be az alkalmazásba
2. Menjen a **Mentések** menüpontra
3. Kattintson a **Mentés készítése** gombra

### Automatikus backup beállítása (cron)

```bash
crontab -e

# Minden nap éjfélkor backup
0 0 * * * /home/pi/edibles-leltar/scripts/backup.sh
```

### Hálózati backup

Állítsa be a `NETWORK_BACKUP_PATH` környezeti változót:
```bash
export NETWORK_BACKUP_PATH="/mnt/nas/backups/leltar"
```

Győződjön meg róla, hogy a hálózati mappa csatlakoztatva van (pl. `/etc/fstab`-ban).

## Projekt struktúra

```
EdibesLeltar/
├── app/
│   ├── __init__.py          # Flask alkalmazás factory
│   ├── config.py             # Konfigurációs beállítások
│   ├── database.py           # SQLite adatbázis kezelés
│   ├── models.py             # Adatmodell osztályok
│   └── routes/
│       ├── auth.py           # Autentikáció
│       ├── products.py       # Termékkezelés
│       ├── inventory.py      # Készletkezelés
│       ├── dashboard.py      # Főoldal
│       └── backup.py         # Backup kezelés
├── templates/                # HTML sablonok
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── products/
│   ├── inventory/
│   └── backup/
├── static/
│   ├── css/style.css
│   └── js/app.js
├── data/                     # SQLite adatbázis (automatikusan létrejön)
├── backups/                  # Backup fájlok
├── run.py                    # Fejlesztési szerver
├── wsgi.py                   # Production szerver
├── requirements.txt          # Python függőségek
└── README.md
```

## API végpontok

### Vonalkód keresés
```
GET /products/api/barcode/<barcode>
```

Válasz:
```json
{
  "success": true,
  "product": {
    "id": 1,
    "name": "Coca Cola 0.5L",
    "barcode": "5449000000996",
    "current_quantity": 50
  }
}
```

## Későbbi fejlesztési lehetőségek

- [ ] Mobilos vonalkód olvasó integráció
- [ ] Remote hozzáférés (VPN/HTTPS)
- [ ] Felhasználókezelés (több felhasználó)
- [ ] Beszállító kezelés
- [ ] Rendelés kezelés
- [ ] Riportok és statisztikák exportálása
- [ ] REST API bővítése

## Hibaelhárítás

### Az alkalmazás nem indul

1. Ellenőrizze a Python verziót: `python3 --version`
2. Ellenőrizze a függőségeket: `pip list`
3. Nézze meg a logokat: `sudo journalctl -u edibles-leltar -f`

### Nem tudok bejelentkezni

1. Ellenőrizze az `APP_PASSWORD` környezeti változót
2. Alapértelmezett jelszó: `leltar2024`

### Backup nem működik

1. Ellenőrizze a `backups/` mappa jogosultságait
2. Hálózati backup esetén ellenőrizze a hálózati mappa csatlakoztatását

## Licenc

MIT License