# -*- coding: utf-8 -*-
"""Script de visite : chargé sans « < » (DOMPurify), étapes intactes."""

import base64
import json
import re

from ui.tutoriel import CLE_FIN, script_visite
from utils.tutoriel import ETAPES, etapes_pour


def _scripts_en_ligne(html):
    return re.findall(r"<script>(.*?)</script>", html, flags=re.S)


def test_un_seul_script_en_ligne_sans_chevron():
    etapes = etapes_pour(False)
    etapes[3]["texte"] = "piège <b>gras</b> et 1<2"
    scripts = _scripts_en_ligne(script_visite(etapes, "abc123"))
    assert len(scripts) == 1
    assert not re.search(r"<[A-Za-z0-9/!]", scripts[0])
    assert "<" not in scripts[0]


def test_la_bibliotheque_est_embarquee_en_base64():
    script = _scripts_en_ligne(script_visite(etapes_pour(False), "abc123"))[0]
    blocs = re.findall(r'atob\("([A-Za-z0-9+/=]+)"\)', script)
    assert len(blocs) == 2
    assert b"driver" in base64.b64decode(blocs[0])


def test_l_identifiant_et_les_etapes_sont_dans_le_script():
    script = _scripts_en_ligne(script_visite(etapes_pour(False), "abc123"))[0]
    assert '"abc123"' in script
    brut = re.search(r"var ETAPES = (\[.*?\]);\n", script, flags=re.S).group(1)
    assert [e["titre"] for e in json.loads(brut)] == [e["titre"] for e in ETAPES]


def test_le_script_ne_clique_que_le_menu_les_onglets_et_la_fin():
    script = _scripts_en_ligne(script_visite(etapes_pour(False), "abc123"))[0]
    script = re.sub(r'atob\("[^"]*"\)', "", script)
    cliques = re.findall(r"(\w+)\.click\(\)", script)
    assert set(cliques) <= {"bouton", "onglet", "fin"}
    assert f".st-key-{CLE_FIN} button" in script


def _pilotage():
    return _scripts_en_ligne(script_visite(etapes_pour(False), "abc123"))[0].split("var ETAPES")[1]


def test_precedent_jamais_grise_par_driver():
    # Une visite d'une bulle par étape : driver.js grise « Précédent » faute
    # d'étape précédente, sauf si la bulle impose disableButtons: [].
    assert "disableButtons: []" in _pilotage()


def test_toute_fermeture_par_la_personne_marque_vu():
    # Échap et clic sur le voile passent par onDestroyStarted, pas onCloseClick.
    assert "onDestroyStarted: finir" in _pilotage()


def test_l_element_montre_n_est_pas_cliquable():
    assert "disableActiveInteraction: true" in _pilotage()


def test_precedent_a_la_premiere_etape_ne_fait_rien():
    assert "if (i === 0) { return; }" in _pilotage()
