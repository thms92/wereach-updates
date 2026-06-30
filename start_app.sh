#!/bin/bash

# Script de lancement simple - LinkedIn Scraper Pro V2
# Sans environnement virtuel

echo "════════════════════════════════════════════════════════════"
echo "🚀 LinkedIn Scraper Pro V2"
echo "════════════════════════════════════════════════════════════"
echo ""

# Aller dans le dossier du script
cd "$(dirname "$0")"

# Ajouter le chemin des binaires locaux
export PATH="/sessions/zen-gracious-mayer/.local/bin:$PATH"

# Créer le dossier config
mkdir -p config

echo "✅ Lancement de l'application Streamlit..."
echo ""
echo "📱 L'interface web va s'ouvrir sur http://localhost:8501"
echo ""
echo "💡 Pour arrêter : Appuyez sur Ctrl+C"
echo ""

# Lancer Streamlit
python3 -m streamlit run app_advanced.py --server.headless=true

echo ""
echo "👋 Application fermée"
