#!/bin/bash
# Edibes Leltár frissítő script
# Használat: ./update.sh

set -e

echo "🔄 Edibes Leltár frissítése..."

# Git pull (ha git-tel van telepítve)
if [ -d ".git" ]; then
    echo "📥 Legújabb változások letöltése..."
    git pull origin main
else
    echo "❌ HIBA: Ez nem egy git repository!"
    echo "   Futtasd: git clone <repository-url>"
    echo "   Vagy inicializáld a git-et manuálisan."
    exit 1
fi

# Docker újraépítés és újraindítás
echo "🐳 Docker container újraépítése..."
docker compose down
docker compose up -d --build

# Régi image-ek törlése (helytakarékosság Raspberry Pi-n fontos!)
echo "🧹 Régi image-ek törlése..."
docker image prune -f

echo ""
echo "✅ Frissítés kész!"
echo ""
echo "📊 Állapot:"
docker compose ps
echo ""
echo "📋 Logok megtekintése: docker compose logs -f"
echo "🌐 Elérhetőség: http://$(hostname -I | awk '{print $1}'):5000"
