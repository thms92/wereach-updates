# -*- coding: utf-8 -*-
"""Composants visuels de la refonte (ui/composants.py) : HTML pur, testé
sans Streamlit."""
import re

import pytest

from ui.composants import (ICONES, TONS, bandeau_contexte, carte_action,
                           entonnoir, etat_vide, jauge_budget, pluriel,
                           point_direct, puce, taux_passage, ton_budget)

NBSP_FINE = " "


def _texte(html: str) -> str:
    """Texte visible approximatif : balises retirées, espaces resserrés."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _attr(html: str, nom: str) -> str:
    m = re.search(rf'{nom}="([^"]*)"', html)
    assert m, f"attribut {nom} absent"
    return m.group(1)


# ---------------------------------------------------------------- pluriel

@pytest.mark.parametrize("n, attendu", [
    (0, "0 entreprise"), (1, "1 entreprise"), (2, "2 entreprises"),
    (3, "3 entreprises"), (-1, "-1 entreprise"),
])
def test_pluriel_francais_zero_et_un_au_singulier(n, attendu):
    assert pluriel(n, "entreprise") == attendu


def test_pluriel_irregulier_et_milliers():
    assert pluriel(2, "travail", "travaux") == "2 travaux"
    assert pluriel(1, "travail", "travaux") == "1 travail"
    assert pluriel(1200, "profil") == f"1{NBSP_FINE}200 profils"


# ------------------------------------------------------------- échappement

def test_tout_texte_recu_est_echappe():
    piege = '<script>alert("x")</script>'
    for html in (
        puce(piege, "ok"),
        bandeau_contexte(piege, [(piege, "neutre")]),
        carte_action(piege, piege),
        etat_vide(piege, piege),
        entonnoir([(piege, 3), ("b", 1), ("c", 0)]),
        point_direct(piege),
    ):
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


def test_html_sur_une_ligne_pour_st_markdown():
    # Une ligne vide ou une indentation casserait le bloc HTML du Markdown.
    for html in (jauge_budget(4, 20), entonnoir([("a", 3), ("b", 1), ("c", 0)]),
                 carte_action("a", "b", "ok"), etat_vide("a", "b"),
                 bandeau_contexte("a", [("b", "ok", True)])):
        assert "\n" not in html


def test_aucun_emoji_dans_les_icones():
    for svg in ICONES.values():
        assert svg.startswith("<svg") and 'aria-hidden="true"' in svg
        assert all(ord(c) < 0x2000 for c in svg)


# ------------------------------------------------------------------- puces

@pytest.mark.parametrize("ton", TONS)
def test_puce_porte_son_ton(ton):
    assert f"wf-puce--{ton}" in puce("Prêt", ton)


def test_ton_inconnu_refuse():
    with pytest.raises(ValueError):
        puce("x", "rouge")
    with pytest.raises(ValueError):
        carte_action("x", "y", "rouge")
    with pytest.raises(ValueError):
        carte_action("x", "y", "ok", icone="licorne")


def test_puce_en_direct_pulse():
    assert "wf-direct" in puce("Session active", "ok", en_direct=True)
    assert "wf-direct" not in puce("Session active", "ok")
    assert 'aria-hidden="true"' in point_direct()


def test_bandeau_contexte_sous_titre_et_puces():
    html = bandeau_contexte("Ce qui vous attend aujourd'hui.",
                            [("Session active", "ok", True), ("File vide", "neutre")])
    assert "<h1" not in html  # le titre reste un st.title
    assert "Ce qui vous attend aujourd&#x27;hui." in html
    assert html.count('class="wf-puce ') == 2


# -------------------------------------------------------- jauge du budget

@pytest.mark.parametrize("utilisees, ton", [
    (0, "ok"), (15, "ok"), (16, "attention"), (19, "attention"), (20, "attention"), (21, "danger"), (25, "danger"),
])
def test_seuils_du_budget(utilisees, ton):
    assert ton_budget(utilisees, 20) == ton
    assert f"wf-jauge--{ton}" in jauge_budget(utilisees, 20)


def test_jauge_restantes_au_singulier_et_au_pluriel():
    assert "16 restantes" in _texte(jauge_budget(4, 20))
    assert "1 restante" in _texte(jauge_budget(19, 20))
    assert "0 restante" in _texte(jauge_budget(20, 20))
    assert "Invitations du jour" in _texte(jauge_budget(4, 20))
    assert "sur 20 conseillées" in _texte(jauge_budget(4, 20))


def test_jauge_limite_atteinte_puis_depassee_sans_blocage():
    assert "vous pouvez continuer" in jauge_budget(20, 20)
    assert "continuer" not in jauge_budget(19, 20)
    depasse = _texte(jauge_budget(23, 20))
    assert "+3" in depasse and "au-delà" in depasse and "Rien n" in depasse
    assert "épuisé" not in jauge_budget(20, 20) + jauge_budget(23, 20)


def test_jauge_dessine_un_cran_par_invitation():
    html = jauge_budget(7, 20)
    assert html.count('class="wf-cran') == 20
    assert html.count("wf-cran--utilise") == 7


def test_jauge_accessible_comme_meter():
    html = jauge_budget(7, 20)
    assert _attr(html, "role") == "meter"
    assert _attr(html, "aria-valuemin") == "0"
    assert _attr(html, "aria-valuemax") == "20"
    assert _attr(html, "aria-valuenow") == "13"
    assert _attr(html, "aria-label")
    assert "13 invitations restantes sur 20 conseillées" == _attr(html, "aria-valuetext")


def test_jauge_bornee_et_plafond_nul():
    assert _attr(jauge_budget(30, 20), "aria-valuenow") == "0"
    assert _attr(jauge_budget(-3, 20), "aria-valuenow") == "20"
    html = jauge_budget(0, 0)
    assert "wf-jauge--danger" in html


def test_jauge_sur_fond_sombre():
    assert "wf-jauge--sombre" in jauge_budget(3, 20, sur_fond_sombre=True)
    assert "wf-jauge--sombre" not in jauge_budget(3, 20)


# ---------------------------------------------------------------- entonnoir

def test_taux_de_passage():
    assert taux_passage(200, 50) == f"25{NBSP_FINE}%"
    assert taux_passage(3, 1) == f"33{NBSP_FINE}%"
    assert taux_passage(0, 0) == "—"
    assert taux_passage(0, 5) == "—"


def test_entonnoir_gere_les_zeros():
    html = entonnoir([("Trouvés", 0), ("Invités", 0), ("Acceptés", 0)])
    assert html.count("<li") == 3
    assert html.count("—") == 2
    assert "width:0%" in html
    assert "ZeroDivision" not in html


def test_entonnoir_proportions_et_taux():
    html = entonnoir([("Trouvés", 200), ("Invités", 50), ("Acceptés", 10), ("Message envoyé", 0)])
    assert "width:100%" in html and "width:25%" in html and "width:5%" in html
    assert f"25{NBSP_FINE}%" in html and f"20{NBSP_FINE}%" in html and f"0{NBSP_FINE}%" in html
    assert "--wf-etapes:4" in html
    assert html.startswith("<ol") and 'aria-label="Parcours des prospects"' in html


def test_entonnoir_vide():
    assert entonnoir([]) == ""


# ------------------------------------------------- carte et état vide

def test_carte_action_icone_par_defaut_selon_le_ton():
    assert ICONES["alerte"] in carte_action("Budget épuisé", "Demain.", "danger")
    assert ICONES["relance"] in carte_action("Relancer", "3 personnes", "attention", "relance")
    assert "wf-action__detail" not in carte_action("Rien d'urgent", "")


def test_etat_vide_explique():
    html = etat_vide("Aucun profil", "Lancez une recherche.")
    assert "wf-vide" in html and "Aucun profil" in html and "Lancez une recherche." in html
