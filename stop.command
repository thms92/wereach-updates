#!/bin/bash
# Arret LinkedIn Scraper - macOS (double-clic)
cd "$(dirname "$0")"
echo "Arret de LinkedIn Scraper..."
docker compose down
echo ""
echo "Arrete."
read -p "Appuie sur Entree pour fermer..."
