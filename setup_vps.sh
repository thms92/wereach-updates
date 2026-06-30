#!/bin/bash
# Script de configuration VPS - Ubuntu 22.04
# Exécuter en tant que root : bash setup_vps.sh

set -e

APP_DIR="/opt/linkedin-scraper"
DUCKDNS_DOMAIN="${1:-mon-scraper}"  # ex: bash setup_vps.sh mon-scraper

echo "=== Installation Docker ==="
apt-get update -q
apt-get install -y curl git ca-certificates gnupg

curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu 2>/dev/null || true

echo "=== Copie des fichiers de l'app ==="
mkdir -p "$APP_DIR"
# Les fichiers .py + Dockerfile + docker-compose.yml doivent être dans ce dossier
# (transférés via scp depuis votre Mac)

echo ""
echo "=== ÉTAPES SUIVANTES ==="
echo ""
echo "1. Transférez vos fichiers Python depuis votre Mac :"
echo "   scp -r '/Users/thxms/Desktop/mon dossier de scrapping perso/'*.py root@VPS_IP:$APP_DIR/"
echo "   scp '/Users/thxms/Desktop/mon dossier de scrapping perso/'{Dockerfile,docker-compose.yml,requirements.txt} root@VPS_IP:$APP_DIR/"
echo "   scp -r '/Users/thxms/Desktop/mon dossier de scrapping perso/.streamlit' root@VPS_IP:$APP_DIR/"
echo ""
echo "2. Lancez l'application :"
echo "   cd $APP_DIR && docker compose up -d --build"
echo ""
echo "3. Vérifiez que ça tourne :"
echo "   docker compose logs -f"
echo ""
echo "4. L'app sera accessible sur http://VPS_IP:8501"
echo ""
echo "=== Docker installé avec succès ==="
