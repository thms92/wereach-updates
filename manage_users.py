#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gestion des comptes d'accès à l'app (login email + mot de passe).

Usage :
    python manage_users.py add    alice@exemple.com      # demande le mot de passe
    python manage_users.py list
    python manage_users.py remove alice@exemple.com
"""
import sys
import getpass

from utils.app_auth import add_user, remove_user, list_users


def main(argv):
    if len(argv) < 2 or argv[1] not in {"add", "list", "remove"}:
        print(__doc__)
        return 1

    cmd = argv[1]

    if cmd == "list":
        users = list_users()
        if users:
            print("Utilisateurs autorisés :")
            for u in users:
                print(f"  - {u}")
        else:
            print("Aucun utilisateur. Ajoute-en avec : python manage_users.py add <email>")
        return 0

    if len(argv) < 3:
        print(f"Email manquant. Usage : python manage_users.py {cmd} <email>")
        return 1
    email = argv[2]

    if cmd == "add":
        pw1 = getpass.getpass(f"Mot de passe pour {email} : ")
        if len(pw1) < 6:
            print("❌ Mot de passe trop court (min 6 caractères).")
            return 1
        pw2 = getpass.getpass("Confirme le mot de passe : ")
        if pw1 != pw2:
            print("❌ Les mots de passe ne correspondent pas.")
            return 1
        add_user(email, pw1)
        print(f"✅ Utilisateur '{email.strip().lower()}' ajouté.")
        return 0

    if cmd == "remove":
        if remove_user(email):
            print(f"✅ Utilisateur '{email.strip().lower()}' supprimé.")
            return 0
        print(f"⚠️ Utilisateur '{email}' introuvable.")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
