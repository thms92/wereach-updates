#!/bin/bash

# LinkedIn Scraper Pro - Lanceur macOS
# Double-cliquez sur ce fichier pour lancer l'application

# Aller dans le dossier du script
cd "$(dirname "$0")"

# Notification de démarrage
osascript -e 'display notification "Démarrage de LinkedIn Scraper Pro..." with title "LinkedIn Scraper Pro"'

# Vérifier que Python est installé
if ! command -v python3 &> /dev/null; then
    osascript -e 'display dialog "Python 3 n'\''est pas installé. Veuillez l'\''installer depuis python.org" buttons {"OK"} with icon stop'
    exit 1
fi

# Ajouter le chemin des binaires Python locaux au PATH
export PATH="$HOME/.local/bin:$PATH"

# Vérifier et installer TOUTES les dépendances manquantes
MISSING_DEPS=false

# Vérifier chaque dépendance
for module in streamlit pandas playwright plotly openpyxl cryptography; do
    if ! python3 -c "import $module" &> /dev/null 2>&1; then
        MISSING_DEPS=true
        break
    fi
done

# Si des dépendances manquent, installer depuis requirements.txt
if [ "$MISSING_DEPS" = true ]; then
    osascript -e 'display notification "Installation des dépendances manquantes..." with title "LinkedIn Scraper Pro"'

    # Installer depuis requirements.txt s'il existe
    if [ -f "requirements.txt" ]; then
        python3 -m pip install --break-system-packages -r requirements.txt
    else
        # Sinon installation manuelle
        python3 -m pip install --break-system-packages streamlit pandas playwright plotly openpyxl xlsxwriter python-dotenv cryptography
    fi

    export PATH="$HOME/.local/bin:$PATH"

    # Installer Playwright Chromium
    python3 -m playwright install chromium

    osascript -e 'display notification "Installation terminée !" with title "LinkedIn Scraper Pro"'
fi

# Créer le dossier config s'il n'existe pas
mkdir -p config

# Notification de lancement
osascript -e 'display notification "Lancement de l'\''interface web..." with title "LinkedIn Scraper Pro"'

# Lancer Streamlit (il ouvrira automatiquement le navigateur)
python3 -m streamlit run app_advanced.py

# Si erreur, afficher un message
if [ $? -ne 0 ]; then
    osascript -e 'display dialog "Erreur lors du lancement de LinkedIn Scraper Pro." buttons {"OK"} with icon stop'
fi
