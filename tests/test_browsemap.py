# -*- coding: utf-8 -*-
"""Adressage du panneau « Plus de profils pour vous » et filtrage de son contenu.

Tout ce qui est testé ici décide sans navigateur : c'est la couche où les
erreurs se paient en doublons dans le fichier et en profils écartés à tort.
"""

from utils.browsemap import (
    CHEMIN_PANNEAU,
    normaliser_url,
    url_panneau,
    vanity_depuis_url,
)

URL_SIMPLE = "https://www.linkedin.com/in/jean-dupont-12345/"


def test_le_vanity_est_extrait_d_une_url_simple():
    assert vanity_depuis_url(URL_SIMPLE) == "jean-dupont-12345"


def test_les_parametres_de_suivi_sont_ignores():
    # LinkedIn sert ses liens ainsi depuis le panneau : sans ça, la même
    # personne entre deux fois au fichier.
    url = URL_SIMPLE + "?miniProfileUrn=urn%3Ali%3Afsd_profile%3AACoAAA"
    assert vanity_depuis_url(url) == "jean-dupont-12345"


def test_un_sous_chemin_de_profil_est_ignore():
    url = "https://www.linkedin.com/in/jean-dupont-12345/details/experience/"
    assert vanity_depuis_url(url) == "jean-dupont-12345"


def test_la_casse_du_vanity_est_normalisee():
    assert vanity_depuis_url("https://www.linkedin.com/in/Jean-Dupont/") == "jean-dupont"


def test_un_vanity_encode_et_son_ecriture_decodee_sont_la_meme_cle():
    # Le panneau sert « c%C3%A9line-exemple » là où la personne colle
    # « céline-exemple » : sans décodage, la même personne serait deux clés.
    encode = "https://www.linkedin.com/in/c%C3%A9line-exemple/"
    decode = "https://www.linkedin.com/in/céline-exemple/"
    assert vanity_depuis_url(encode) == vanity_depuis_url(decode) == "céline-exemple"


def test_la_casse_d_un_vanity_encode_est_normalisee_apres_decodage():
    # %C3%89 est « É » : minuscule seulement une fois décodé, sinon « É »
    # et « é » resteraient deux personnes.
    assert vanity_depuis_url("https://www.linkedin.com/in/%C3%89lise-exemple/") == "élise-exemple"


def test_l_url_canonique_d_un_vanity_accentue_est_la_meme_pour_les_deux_ecritures():
    # Forme ré-encodée, en ASCII : celle que LinkedIn sert lui-même dans ses
    # liens, qui passe telle quelle dans un CSV, un Excel ou la base.
    attendu = "https://www.linkedin.com/in/c%C3%A9line-exemple/"
    assert normaliser_url("https://www.linkedin.com/in/céline-exemple") == attendu
    assert normaliser_url("https://www.linkedin.com/in/C%C3%A9line-Exemple/?trk=x") == attendu
    # Hex en minuscules dans la source : même clé quand même.
    assert normaliser_url("https://www.linkedin.com/in/c%c3%a9line-exemple/") == attendu


def test_l_url_du_panneau_d_un_vanity_accentue_reste_en_ascii():
    assert url_panneau("https://www.linkedin.com/in/céline-exemple/") == (
        "https://www.linkedin.com/in/c%C3%A9line-exemple/" + CHEMIN_PANNEAU
    )


def test_une_page_entreprise_n_est_pas_un_profil():
    assert vanity_depuis_url("https://www.linkedin.com/company/thiga/") is None


def test_une_saisie_vide_n_est_pas_un_profil():
    assert vanity_depuis_url("") is None
    assert vanity_depuis_url(None) is None


def test_deux_liens_vers_la_meme_personne_donnent_la_meme_url():
    autre = "http://linkedin.com/in/JEAN-DUPONT-12345?trk=public_profile"
    assert normaliser_url(autre) == normaliser_url(URL_SIMPLE) == URL_SIMPLE


def test_l_url_du_panneau_se_construit_depuis_celle_du_profil():
    assert url_panneau(URL_SIMPLE) == URL_SIMPLE + CHEMIN_PANNEAU


def test_l_url_du_panneau_est_nulle_si_ce_n_est_pas_un_profil():
    assert url_panneau("https://www.linkedin.com/company/thiga/") is None


# --- Filtrage des suggestions --------------------------------------------

from utils.browsemap import filtrer_suggestions


def suggestion(**champs):
    """Une entrée de panneau, par défaut retenable, surchargeable au besoin."""
    base = {
        "nom": "Jean Dupont",
        "url": URL_SIMPLE,
        "degre": "2e",
        "intitule": "Product Manager, Thiga",
        "invitable": True,
    }
    base.update(champs)
    return base


def motifs(ecartees):
    return [e["motif"] for e in ecartees]


def test_une_suggestion_ordinaire_est_retenue():
    retenues, ecartees = filtrer_suggestions([suggestion()])
    assert [r["nom"] for r in retenues] == ["Jean Dupont"]
    assert ecartees == []


def test_l_url_retenue_est_canonique():
    # Ce qui sort d'ici part dans run_url_scraper : les paramètres de suivi
    # n'ont rien à y faire.
    brute = URL_SIMPLE + "?miniProfileUrn=urn%3Ali%3Afsd_profile%3AACoAAA"
    retenues, _ = filtrer_suggestions([suggestion(url=brute)])
    assert retenues[0]["url"] == URL_SIMPLE


def test_le_premier_degre_est_ecarte():
    _, ecartees = filtrer_suggestions([suggestion(degre="1er")])
    assert "réseau" in motifs(ecartees)[0]


def test_les_autres_degres_sont_retenus():
    retenues, _ = filtrer_suggestions(
        [suggestion(degre="2e"), suggestion(url="https://www.linkedin.com/in/marie/", degre="3e")]
    )
    assert len(retenues) == 2


def test_un_profil_deja_au_fichier_est_ecarte():
    _, ecartees = filtrer_suggestions([suggestion()], urls_en_base=[URL_SIMPLE])
    assert "fichier" in motifs(ecartees)[0]


def test_le_fichier_est_compare_sous_forme_canonique():
    # La base peut contenir le lien tel qu'il avait été copié jadis.
    stockee = "http://www.linkedin.com/in/JEAN-DUPONT-12345?trk=x"
    _, ecartees = filtrer_suggestions([suggestion()], urls_en_base=[stockee])
    assert len(ecartees) == 1


def test_l_entreprise_de_reference_est_ecartee():
    # « Le même profil ailleurs » : celui qui y est encore n'est pas la cible.
    _, ecartees = filtrer_suggestions([suggestion()], entreprise_reference="Thiga")
    assert "Thiga" in motifs(ecartees)[0]


def test_l_entreprise_de_reference_se_compare_sans_tenir_compte_de_la_casse():
    _, ecartees = filtrer_suggestions([suggestion()], entreprise_reference="thiga")
    assert len(ecartees) == 1


def test_une_entreprise_de_reference_inconnue_n_ecarte_personne():
    # La page n'a pas permis de la lire : on ne doit ni planter ni tout vider.
    retenues, ecartees = filtrer_suggestions([suggestion()], entreprise_reference=None)
    assert len(retenues) == 1 and ecartees == []


def test_une_entreprise_de_reference_vide_n_ecarte_personne():
    retenues, _ = filtrer_suggestions([suggestion()], entreprise_reference="   ")
    assert len(retenues) == 1


def test_les_non_invitables_sont_ecartes_sur_demande():
    _, ecartees = filtrer_suggestions(
        [suggestion(invitable=False)], invitables_seulement=True
    )
    assert "invitable" in motifs(ecartees)[0]


def test_les_non_invitables_sont_gardes_par_defaut():
    retenues, _ = filtrer_suggestions([suggestion(invitable=False)])
    assert len(retenues) == 1


def test_le_mot_attendu_filtre_sur_l_intitule():
    _, ecartees = filtrer_suggestions([suggestion()], mot_intitule="Data")
    assert "Data" in motifs(ecartees)[0]


def test_le_mot_attendu_ignore_la_casse_et_les_espaces_de_bord():
    # Une saisie « product » ne doit pas vider la liste sans raison visible.
    retenues, _ = filtrer_suggestions([suggestion()], mot_intitule="  product  ")
    assert len(retenues) == 1


def test_un_mot_attendu_vide_ne_filtre_rien():
    retenues, _ = filtrer_suggestions([suggestion()], mot_intitule="")
    assert len(retenues) == 1


def test_un_lien_illisible_est_ecarte_avec_son_motif():
    _, ecartees = filtrer_suggestions([suggestion(url="https://example.com/x")])
    assert "illisible" in motifs(ecartees)[0]


def test_le_motif_affiche_est_le_plus_sur_des_motifs_applicables():
    # 1er degré ET déjà au fichier : le degré est une certitude, l'autre aussi,
    # mais l'ordre doit être stable pour que l'écran soit compréhensible.
    _, ecartees = filtrer_suggestions(
        [suggestion(degre="1er")], urls_en_base=[URL_SIMPLE]
    )
    assert "réseau" in motifs(ecartees)[0]


def test_une_liste_entierement_ecartee_rend_tous_les_motifs():
    # L'écran s'en sert : une liste vide sans explication passerait pour un
    # profil sans voisins.
    entrees = [suggestion(degre="1er"), suggestion(url="https://www.linkedin.com/in/marie/", degre="1er")]
    retenues, ecartees = filtrer_suggestions(entrees)
    assert retenues == [] and len(ecartees) == 2


def test_un_panneau_vide_ne_rend_rien_sans_echouer():
    assert filtrer_suggestions([]) == ([], [])
