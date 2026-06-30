#!/bin/bash

echo "🚀 Lancement de LinkedIn Scraper V2..."
echo ""

# Vérifier que Streamlit est installé
if ! command -v streamlit &> /dev/null; then
    echo "❌ Streamlit n'est pas installé"
    echo "→ Lancez d'abord: ./install_mac.sh"
    exit 1
fi

# Lancer l'application
streamlit run app_advanced.py
