<p align="center">
  <h1 align="center">Edibles Inventory</h1>
  <p align="center">
    <strong>Vending Machine Inventory Management System</strong>
  </p>
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
  <a href="#"><img src="https://img.shields.io/badge/flask-2.x-000000?style=flat-square&logo=flask&logoColor=white" alt="Flask"></a>
  <a href="#"><img src="https://img.shields.io/badge/docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-Raspberry%20Pi-C51A4A?style=flat-square&logo=raspberrypi&logoColor=white" alt="Raspberry Pi"></a>
  <a href="#"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
</p>

<p align="center">
  <a href="#installation">Installation</a> |
  <a href="#docker-deployment">Docker</a> |
  <a href="#features">Features</a> |
  <a href="#api">API</a>
</p>

---

## Overview

Inventory management system optimized for vending machines serving beverages, sandwiches, snacks, and other products.

### Multi-Location Supply Chain

The system supports multi-location inventory management across the entire supply chain:

```
Supplier ──PURCHASE──> Warehouse ──LOAD──> Vehicle ──CONSUME──> Vending Machine
```

### Location Types

| Type | Description |
|------|-------------|
| **Warehouse** | Central storage, receives purchases from suppliers |
| **Vehicle** | Mobile unit, transports products from warehouse |
| **Vending** | Endpoint, receives stock from vehicle |

### Transactions

- **Atomic transactions** - Every transfer occurs in a single transaction. Source decreases, destination increases. No intermediate state.
- **Compensating transactions** - Erroneous movements are not deleted; instead, a reverse movement is created (audit trail preservation).

---

## Features

### Inventory Management

- Multi-location inventory tracking (product x location)
- Product catalog with categories and units of measurement
- Mobile barcode scanner (html5-qrcode) - camera-based
- Stock movement recording (receipt, issue, transfer, adjustment, scrap)
- Quick +/- buttons for instant stock changes
- Minimum stock level alerts per location

### Transfers

- Warehouse to Vehicle loading
- Vehicle to Vending machine restocking (mobile-optimized UI)
- Quick barcode-based transfers
- Transfer history and reversal

### Dashboard

- Overview dashboard of inventory status
- Per-location summaries
- Per-category summaries
- Low stock product highlighting
- Recent movements list

### Master Data

- Product management (CRUD)
- Category management
- Unit of measurement management
- Location management (warehouse, vehicle, vending)
- Soft delete - deleted items can be restored

### Security

- Hashed password (PBKDF2-SHA256)
- Session-based authentication
- Operates on local network (VPN support)

### Data Safety

- SQLite database with WAL mode (safe for SD cards)
- All changes logged (audit log)
- Compensating transactions (never delete)
- Manual and automatic backup
- Network backup capability

---

## Installation

### Prerequisites

- Python 3.9+
- pip

### Steps

```bash
# 1. Clone repository
git clone <repo-url>
cd EdibesLeltar

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start application
python run.py
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session encryption key | Auto-generated |
| `APP_PASSWORD` | Login password | `leltar2024` |
| `NETWORK_BACKUP_PATH` | Network backup path | - |

```bash
# Linux/Mac
export SECRET_KEY="your-secret-key"
export APP_PASSWORD="your-password"

# Windows
set SECRET_KEY=your-secret-key
set APP_PASSWORD=your-password
```

> **Important:** Change the default password in production environments!

---

## Docker Deployment

Docker deployment is simpler and easier to maintain.

### Prerequisites

```bash
# Install Docker on Raspberry Pi
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Add user to docker group
sudo usermod -aG docker $USER
# Reboot required
```

### Quick Setup

```bash
# Clone repository
git clone <repo-url>
cd EdibesLeltar

# Create directories
mkdir -p data backups

# Set secret key (recommended)
echo "SECRET_KEY=$(openssl rand -hex 32)" > .env

# Start container
docker compose up -d --build

# Verify
docker compose ps
```

### Access

```
http://<raspberry-pi-ip>:5000
```

### Commands

| Action | Command |
|--------|---------|
| Logs | `docker compose logs -f` |
| Restart | `docker compose restart` |
| Stop | `docker compose down` |
| Update | `./update.sh` |

### Updates

```bash
chmod +x update.sh
./update.sh
```

The script automatically:
1. Pulls latest changes from Git
2. Rebuilds the Docker container
3. Removes old images

### Data Persistence

The following directories persist on the host:

| Directory | Contents |
|-----------|----------|
| `./data/` | SQLite database |
| `./backups/` | Backup files |

---

## Raspberry Pi Installation (Manual)

### System Preparation

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv -y
```

### Systemd Service

```bash
sudo nano /etc/systemd/system/edibles-leltar.service
```

```ini
[Unit]
Description=Edibles Inventory Application
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

```bash
sudo systemctl daemon-reload
sudo systemctl enable edibles-leltar
sudo systemctl start edibles-leltar
sudo systemctl status edibles-leltar
```

---

## Backup

### Manual Backup

1. Log in to the application
2. Navigate to **Backups** menu
3. Click **Create Backup** button

### Automatic Backup (cron)

```bash
crontab -e

# Every day at midnight
0 0 * * * /home/pi/edibles-leltar/scripts/backup.sh
```

### Network Backup

```bash
export NETWORK_BACKUP_PATH="/mnt/nas/backups/inventory"
```

---

## Project Structure

```
EdibesLeltar/
├── app/
│   ├── __init__.py          # Flask application factory
│   ├── config.py            # Configuration settings
│   ├── database.py          # SQLite database handling
│   ├── models.py            # Data model classes
│   └── routes/
│       ├── auth.py          # Authentication
│       ├── products.py      # Product management
│       ├── inventory.py     # Inventory management
│       ├── dashboard.py     # Homepage
│       └── backup.py        # Backup handling
├── templates/               # HTML templates
├── static/                  # CSS, JS
├── data/                    # SQLite database
├── backups/                 # Backup files
├── docker-compose.yml       # Docker configuration
├── Dockerfile               # Docker image
├── requirements.txt         # Python dependencies
└── README.md
```

---

## API

### Barcode Search

```http
GET /products/api/barcode/<barcode>
```

**Response:**

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

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Application won't start | Check `python3 --version`, `pip list` |
| Login failed | Verify `APP_PASSWORD` environment variable |
| Backup not working | Check `backups/` directory permissions |
| Docker error | Run `docker compose logs -f` |

### Viewing Logs

```bash
# Systemd
sudo journalctl -u edibles-leltar -f

# Docker
docker compose logs -f
```

---

## Roadmap

- [ ] Remote access (VPN/HTTPS)
- [ ] User management (multiple users)
- [ ] Supplier management
- [ ] Order management
- [ ] Reports and statistics export
- [ ] REST API expansion

---

## License

MIT License
