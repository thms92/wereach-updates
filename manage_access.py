#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gestion du mot de passe d'accès partagé à WeFiiT Reach.

Tout le groupe se connecte avec son email @<domaine> + CE mot de passe unique.

Usage :
    python manage_access.py set       # demande le nouveau mot de passe
    python manage_access.py status    # indique s'il est défini
"""
import sys
import getpass

from utils.app_auth import set_access_password, access_configured, ALLOWED_DOMAIN


def main(argv):
    if len(argv) < 2 or argv[1] not in {"set", "status"}:
        print(__doc__)
        return 1

    if argv[1] == "status":
        etat = "défini ✅" if access_configured() else "NON défini ❌"
        print(f"Domaine autorisé : @{ALLOWED_DOMAIN}")
        print(f"Mot de passe d'accès : {etat}")
        return 0

    pw1 = getpass.getpass("Nouveau mot de passe d'accès WeFiiT Reach : ")
    if len(pw1) < 6:
        print("❌ Mot de passe trop court (min 6 caractères).")
        return 1
    pw2 = getpass.getpass("Confirme le mot de passe : ")
    if pw1 != pw2:
        print("❌ Les mots de passe ne correspondent pas.")
        return 1
    set_access_password(pw1)
    print(f"✅ Mot de passe d'accès défini. Domaine autorisé : @{ALLOWED_DOMAIN}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
