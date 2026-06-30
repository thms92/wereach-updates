#!/bin/bash

# Diagnostic Cookie LinkedIn — Lanceur macOS
# Double-cliquez pour vérifier si votre cookie LinkedIn est valide.
# Le navigateur s'ouvrira et tentera de charger votre feed LinkedIn.

cd "$(dirname "$0")"

osascript -e 'display notification "Démarrage du diagnostic cookie..." with title "Diagnostic LinkedIn"'

# Vérifier Python
if ! command -v python3 &> /dev/null; then
    osascript -e 'display dialog "Python 3 n'\''est pas installé." buttons {"OK"} with icon stop'
    exit 1
fi

# Vérifier les dépendances minimales
for module in playwright cryptography; do
    if ! python3 -c "import $module" &> /dev/null 2>&1; then
        osascript -e 'display notification "Installation des dépendances..." with title "Diagnostic LinkedIn"'
        python3 -m pip install --break-system-packages playwright cryptography
        python3 -m playwright install chromium
        break
    fi
done

# Lancer le diagnostic (mode visible)
python3 diagnostic_cookie.py

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    osascript -e 'display dialog "Le diagnostic a rencontré une erreur. Voir la sortie dans la fenêtre Terminal." buttons {"OK"} with icon caution'
fi

echo ""
echo "Appuyez sur Entrée pour fermer cette fenêtre..."
read
