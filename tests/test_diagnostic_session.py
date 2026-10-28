# -*- coding: utf-8 -*-
"""« Tester la session » doit tester la session de la personne connectée,
même sans ancien config/cookie.txt (cas d'un nouveau collègue, 2026-10-22)."""

from pathlib import Path

import diagnostic_cookie

RACINE = Path(__file__).resolve().parent.parent


def test_session_transmise_par_l_app(monkeypatch):
    monkeypatch.setenv("WEREACH_COOKIE", "SESSION-DE-TEST")
    assert diagnostic_cookie.load_cookie() == "SESSION-DE-TEST"


def test_l_app_transmet_la_session_au_test():
    source = (RACINE / "ui" / "page_recherche.py").read_text(encoding="utf-8")
    assert '"WEREACH_COOKIE": st.session_state.global_cookie' in source



# --- Playwright simulé : la page du fil est comptée et surveillée ---------

import asyncio
import json

import pytest


class _Reponse:
    def __init__(self, status):
        self.status = status


class _Page:
    def __init__(self, url, status, texte, erreur=None):
        self.url, self._status, self._texte, self._erreur = url, status, texte, erreur
        self.demandes = 0

    def on(self, *a, **k):
        pass

    async def goto(self, *a, **k):
        if self._erreur:
            raise Exception(self._erreur)
        self.demandes += 1
        return _Reponse(self._status)

    async def inner_text(self, *a, **k):
        return self._texte

    async def screenshot(self, **k):
        pass


def _simuler(monkeypatch, page):
    class Contexte:
        async def add_cookies(self, c): pass
        async def new_page(self): return page

    class Navigateur:
        async def new_context(self, **k): return Contexte()
        async def close(self): pass

    class Chromium:
        async def launch(self, **k): return Navigateur()

    class PW:
        chromium = Chromium()

    class Gestionnaire:
        async def __aenter__(self): return PW()
        async def __aexit__(self, *a): pass

    monkeypatch.setattr(diagnostic_cookie, "async_playwright", lambda: Gestionnaire())


def _lancer(capsys):
    asyncio.run(diagnostic_cookie.run_diagnostic("COOKIE", headless=True))
    return capsys.readouterr().out


def _pages(tmp_path):
    f = tmp_path / "daily_limits.json"
    return json.loads(f.read_text()).get("pages_linkedin", 0) if f.exists() else 0


def test_tester_la_session_compte_une_page(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("WEREACH_CONFIG_DIR", str(tmp_path))
    _simuler(monkeypatch, _Page("https://www.linkedin.com/feed/", 200, "Bonjour"))
    sortie = _lancer(capsys)
    assert _pages(tmp_path) == 1
    assert "COOKIE VALIDE" in sortie


def test_sans_dossier_transmis_le_diagnostic_tourne_sans_compter(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("WEREACH_CONFIG_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    _simuler(monkeypatch, _Page("https://www.linkedin.com/feed/", 200, ""))
    assert "COOKIE VALIDE" in _lancer(capsys)
    assert not list(tmp_path.rglob("daily_limits.json"))


def test_page_d_alerte_rendue_comme_session_interrompue(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("WEREACH_CONFIG_DIR", str(tmp_path))
    _simuler(monkeypatch, _Page("https://www.linkedin.com/checkpoint/challenge/x", 200, ""))
    sortie = _lancer(capsys)
    assert "COOKIE EXPIRÉ" in sortie
    assert _pages(tmp_path) == 1


def test_requete_non_partie_ne_compte_pas(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("WEREACH_CONFIG_DIR", str(tmp_path))
    _simuler(monkeypatch, _Page("", 0, "", erreur="net::ERR_INTERNET_DISCONNECTED"))
    _lancer(capsys)
    assert _pages(tmp_path) == 0


def test_l_app_transmet_le_dossier_de_la_personne():
    source = (RACINE / "ui" / "page_recherche.py").read_text(encoding="utf-8")
    assert '"WEREACH_CONFIG_DIR": str(st.session_state.user_paths.config_dir)' in source
