#!/usr/bin/env bash
# Déploiement WeFiiT Reach sur une VM Ubuntu (Oracle Always Free).
# À exécuter SUR LA VM, dans le dossier du projet (après avoir copié le code).
#   bash deploy_oracle.sh
set -euo pipefail

echo "==> 1/3  Installation de Docker (si absent)"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER" || true
  echo "    Docker installé. (Si 'permission denied' plus bas : déconnecte/reconnecte le SSH puis relance ce script.)"
fi

echo "==> 2/3  Build + lancement du conteneur (Chrome visible sous Xvfb)"
# 'sg docker' permet d'utiliser docker sans re-login juste après l'install.
sg docker -c "docker compose up -d --build" 2>/dev/null || sudo docker compose up -d --build

echo "==> 3/3  Attente du démarrage de l'app…"
for i in $(seq 1 40); do
  if curl -sf http://localhost:8501/_stcore/health >/dev/null 2>&1; then
    echo "    ✅ App en ligne sur http://localhost:8501 (accès local à la VM)"
    exit 0
  fi
  sleep 3
done
echo "    ⚠️ L'app ne répond pas encore. Voir les logs : docker compose logs -f"
exit 1
