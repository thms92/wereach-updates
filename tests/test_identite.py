# -*- coding: utf-8 -*-
"""Nom demandé une fois, signal de connexion (nom, version, date)."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from streamlit.testing.v1 import AppTest

import utils.identite as identite
from tests.conftest import APP, EMAIL_DE_TEST


def test_nom_garde_sur_le_poste(tmp_path):
    assert identite.lire_nom(tmp_path) == ""
    identite.enregistrer_nom(tmp_path, "  Personne Exemple ")
    assert identite.lire_nom(tmp_path) == "Personne Exemple"


def test_message_ne_contient_que_nom_version_date():
    m = identite.message_connexion("Personne Exemple", "1.8.3",
                                   datetime(2026, 10, 22, 9, 14, tzinfo=ZoneInfo("Europe/Paris")))
    assert m == {"nom": "Personne Exemple", "version": "1.8.3", "date": "22/10/2026 09:14"}


def test_sans_webhook_ou_sans_nom_rien_ne_part(monkeypatch):
    envois = []
    monkeypatch.setattr(identite, "_envoyer", lambda *a: envois.append(a))
    assert identite.signaler_connexion("", "Personne Exemple", "1.8.3") is False
    assert identite.signaler_connexion("https://exemple.invalid/webhook", "", "1.8.3") is False
    assert envois == []


def test_un_webhook_injoignable_ne_fait_pas_planter():
    identite._envoyer("http://127.0.0.1:9/webhook", {"nom": "x"})


def test_envoi_en_json(monkeypatch):
    recu = {}

    class Reponse:
        def close(self):
            pass

    def faux_urlopen(requete, timeout):
        recu["corps"] = json.loads(requete.data)
        recu["type"] = requete.get_header("Content-type")
        return Reponse()

    monkeypatch.setattr(identite.urllib.request, "urlopen", faux_urlopen)
    identite._envoyer("https://exemple.invalid/webhook", {"nom": "Personne Exemple"})
    assert recu == {"corps": {"nom": "Personne Exemple"}, "type": "application/json"}


def _app_sans_nom(tmp_path, monkeypatch):
    monkeypatch.setattr(identite, "lire_nom", lambda _d: "")
    enregistres = []
    monkeypatch.setattr(identite, "enregistrer_nom", lambda _d, n: enregistres.append(n))
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["auth_email"] = EMAIL_DE_TEST
    at.run()
    return at, enregistres


def test_premier_lancement_demande_le_nom_puis_ouvre_l_outil(tmp_path, monkeypatch):
    at, enregistres = _app_sans_nom(tmp_path, monkeypatch)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert [s.value for s in at.subheader] == ["Bienvenue"]
    at.text_input(key="saisie_nom").set_value("Personne Exemple")
    at.button[0].click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert enregistres == ["Personne Exemple"]
    assert at.session_state["nom_utilisateur"] == "Personne Exemple"


def test_nom_deja_connu_rien_n_est_demande(monkeypatch):
    monkeypatch.setattr(identite, "lire_nom", lambda _d: "Personne Exemple")
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["auth_email"] = EMAIL_DE_TEST
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Bienvenue" not in [s.value for s in at.subheader]
    assert at.session_state["nom_utilisateur"] == "Personne Exemple"


def test_nom_vide_refuse(tmp_path, monkeypatch):
    at, enregistres = _app_sans_nom(tmp_path, monkeypatch)
    at.text_input(key="saisie_nom").set_value("   ")
    at.button[0].click()
    at.run()
    assert enregistres == []
    assert at.error
