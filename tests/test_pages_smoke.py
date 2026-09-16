# -*- coding: utf-8 -*-
"""Chaque page du menu doit se charger sans lever d'exception."""

import pytest
from streamlit.testing.v1 import AppTest

from tests.test_navigation import arbre_app, pages_du_menu

PAGES = pages_du_menu(arbre_app())


@pytest.mark.parametrize("page", PAGES)
def test_la_page_se_charge_sans_exception(page):
    at = AppTest.from_file("app_advanced.py", default_timeout=90)
    at.session_state["page"] = page
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["page"] == page
