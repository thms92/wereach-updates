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

