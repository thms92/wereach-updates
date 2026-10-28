# -*- coding: utf-8 -*-
"""Pages LinkedIn fictives : liste des invitations envoyées et liste des relations.

Le balisage est celui relevé sur le compte de Thomas le 2026-10-28 (sonde en
lecture seule) : mêmes éléments, mêmes attributs, mêmes classes générées.
Tout ce qui désigne une personne y est inventé — noms, intitulés, adresses
/in/, photos, identifiants internes — et les dessins SVG des avatars sont
vidés. Aucune donnée réelle n'entre dans le dépôt.
"""

ENTETE_ENVOYEES = (
    '<nav class="ajrl5a ajrk1d ajrk1u ajrk2e ajrk2v ajrluf"><ul class="ajrayf ajrij2 ajrjqj a'
    'jrinm ajrluf"><li class="ajrl5b ajrjqo ajrluf"><a class="ajrl5k ajrl5j ajraec ajrjp2 ajr'
    'th ajra2n ajrazb ajrk3v ajrk57 ajrinm ajrjqq ajrk6n ajrkvt ajrkv4 ajrl5l" aria-current="'
    'true" href="https://www.linkedin.com/mynetwork/invitation-manager/sent/CONNECTION/"><spa'
    'n class="ajrayf ajrijm ajrluf"><span class="ajrk8d ajrlcs ajrayf ajrk57 ajrhc3 ajrk8b">P'
    'ersonnes ({total})</span></span></a></li></ul></nav>'
)

OUVERTURE_ENVOYEES = (
    '<div class="ajrlr8 ajrikq ajrayf ajrijm ajra2x ajrima ajrbst ajrjrc ajrluf" data-testid='
    '"lazy-column" data-component-type="LazyColumn">'
)

SEPARATEUR = (
    '<hr role="presentation" class="ajrlq6 ajrlq5 ajrkxn ajrkyj ajrkzf ajrk0b ajrth ajrlra aj'
    'rlq8 ajrtn">'
)

CARTE_ENVOYEE = (
    '<div class="ajrlr8 ajrk1d ajrk1u ajrk2b ajrk2s ajrayf ajrijm ajrjqs ajrjp7 ajrjqi ajrinm'
    ' ajrhz6 ajrluf" role="listitem" componentkey="auto-component-00000000-0000-0000-0000-000'
    '000000000"><div class="ajrayf ajrij2 ajrjqs ajrjp2 ajrjqj ajrinm ajrluf"><a tabindex="0"'
    ' class="ajrjqh ajrl2k ajrl2j ajrkxn ajrkyj ajrkzf ajrk0b ajrth ajrhc3 ajrk8g ajrayf" hre'
    'f="{href}" style="height: 7.2rem; width: 7.2rem;"><div class="ajrikq ajra1r ajrluf"><fig'
    'ure class="ajrlto ajrltr ajrltp ajraee ajra2q ajrhy2 ajrhiq ajrku1 ajrkuw ajrluf" style='
    '"height: 7.2rem; width: 7.2rem;"><svg aria-hidden="true"></svg><img class="ajrltj ajrlti'
    ' ajrhiq ajrhy2 ajrltm" fetchpriority="low" alt="Photo de profil de {nom}" src="{photo}" '
    'data-loaded="true"></figure></div></a><div class="ajrlr8 ajrikq ajrayf ajrijm ajrjqs ajr'
    'jp7 ajrjqi ajrima ajrluf"><div class="ajrlr8 ajrayf ajrijm ajrjqs ajrjp7 ajrjqi ajrima a'
    'jrluf"><p class="ajrk8d ajrk3v ajrk1r ajrk3b ajrk5j ajrk6b ajrk6n ajrk7r ajrgdi ajrk8b a'
    'jrle8">{nom}</p><div class="ajrk3b ajrk5j ajrk5z ajrk6n ajrk7r ajrgeo ajrk8b"><p class="'
    'ajrk8d ajrk3r ajrlfg ajrlfe ajrlfd ajra2q ajrk8c ajrhi2 ajrle8"><span>{titre}</span></p>'
    '</div><div class="ajrk3b ajrk5j ajrk5z ajrk6n ajrk7r ajrgeo ajrk8b"><p class="ajrk8d ajr'
    'k3n ajrlff ajrlfe ajrlfd ajra2q ajrk8c ajrhi2 ajrle8"><span>{quand}</span></p></div></di'
    'v></div><div class="ajrayf ajrij2 ajrjqs ajrjp2 ajrjqi ajrinm ajrluf"><a class="ajrlhg a'
    'jrlhf ajrth ajra2n ajrhc3 ajrk6n ajrk76 ajrlhl ajrlhi ajrlhh ajrazb ajrjp2 ajrjrc" aria-'
    'disabled="false" href="https://www.linkedin.com/mynetwork/invitation-manager/sent/" comp'
    'onentkey="00000000-0000-0000-0000-000000000000" aria-label="Retirer l’invitation envoyée'
    ' à {nom}"><span class="ajrlh3 ajrlhy ajrikq ajrjp2 ajrth ajra2n ajrazb ajrim6 ajrjqq ajr'
    'k6n ajrk76 ajrkvt ajrkv4 ajrlh8 ajrlih ajrlie ajrlh1 ajrhq2 ajrlip"><span class="ajrk8d '
    'ajrlcp ajrlvr ajrk57 ajrhc3 ajrk8b ajrliy">Retirer</span></span></a></div></div></div>'
)

ENTETE_RELATIONS = (
    '<p class="ajrk8d ajrk3z ajrk1d ajrk1u ajrk2d ajrk2u ajrk3b ajrk5j ajrk5z ajrk6n ajrk7r a'
    'jrgdi ajrk8b ajrle8">{total}&nbsp;relations</p>'
)

OUVERTURE_RELATIONS = (
    '<div class="ajrlr8 ajrayf ajrijm ajrima ajrku1 ajrkuw ajrjrc ajrluf" data-testid="lazy-c'
    'olumn" data-component-type="LazyColumn">'
)

CARTE_RELATION = (
    '<div class="ajrax7 ajrluf" data-display-contents="true"><div class="ajrk1c ajrk1t ajrk2e'
    ' ajrk2v ajrayf ajrij2 ajrjqs ajrjp2 ajrjqj ajrin2 ajrluf" componentkey="ConnectionCard_{'
    'rang}-{slug}"><a tabindex="0" class="ajrjqh ajrl2k ajrl2j ajrkxn ajrkyj ajrkzf ajrk0b aj'
    'rth ajrhc3 ajrk8g ajrayf" href="{href}" componentkey="ConnectionCardProfileImage_{rang}-'
    '{slug}" style="height: 7.2rem; width: 7.2rem;"><figure class="ajrlto ajrltr ajrltp ajrae'
    'e ajrikq ajra2q ajrhy2 ajrhiq ajrluf" componentkey="ConnectionCardProfileImage_{rang}-{s'
    'lug}"><svg aria-hidden="true"></svg><img class="ajrltj ajrlti ajrhiq ajrhy2 ajrltm" fetc'
    'hpriority="low" alt="Photo de profil de {nom}" src="{photo}" data-loaded="true"></figure'
    '></a><div class="ajrlr8 ajrikq ajrayf ajrijm ajrjqs ajrjp7 ajrjqi ajrima ajrluf"><div cl'
    'ass="ajrlr8 ajrayf ajrijm ajrjqs ajrjp7 ajrjqi ajrima ajrluf"><a tabindex="0" class="ajr'
    'l2k ajrl2j ajrkxn ajrkyj ajrkzf ajrk0b ajrth ajrhc3 ajrk8g ajrayf" href="{href}" compone'
    'ntkey="00000000-0000-0000-0000-000000000000"><div class="ajrlr8 ajrikq ajrayf ajrijm ajr'
    'jqs ajrjp7 ajrjqi ajrima ajrluf" componentkey="00000000-0000-0000-0000-000000000000"><p '
    'class="ajrk8d ajrk3v ajrkym ajrk3b ajrk5j ajrk6b ajrk6n ajrk7r ajrgdi ajrk8b ajrle7">{no'
    'm}</p><div class="ajrk3b ajrk5j ajrk5z ajrk6n ajrk7r ajrgdi ajrk8b"><p class="ajrk8d ajr'
    'k3r ajrlfg ajrlfe ajrlfd ajra2q ajrk8c ajrhi2 ajrle7"><span>{titre}</span></p></div></di'
    'v></a><p class="ajrk8d ajrk3r ajrk3b ajrk5j ajrk5z ajrk6n ajrk7r ajrgeo ajrk8b ajrle8">{'
    'quand}</p></div></div><div class="ajrayf ajrij2 ajrjqs ajrjp2 ajrjqi ajrinm ajrluf"><div'
    ' class="ajrayf ajrij2 ajrjqs ajrjp7 ajrjqi ajrinu ajrluf"><div class="ajrax7 ajrluf" dat'
    'a-display-contents="true"><a class="ajrlhg ajrlhf ajrth ajra2n ajrhc3 ajrk6n ajrk76 ajrl'
    'hl ajrlhi ajrlhh ajrazb ajrjp2 ajrjrc" aria-disabled="false" href="/messaging/compose/?p'
    'rofileUrn=urn%3Ali%3Afsd_profile%3A{urn}&amp;recipient={urn}&amp;interop=msgOverlay" com'
    'ponentkey="00000000-0000-0000-0000-000000000000" aria-label="Envoyer un message à {nom}"'
    '><span class="ajrlh3 ajrlhy ajrikq ajrjp2 ajrth ajra2n ajrazb ajrim6 ajrjqq ajrk6n ajrk7'
    '6 ajrkvt ajrkv4 ajrlh7 ajrlig ajrlid ajrlh0 ajrhqu ajrlio"><span class="ajrk8d ajrlcn aj'
    'rlvr ajrk57 ajrhc3 ajrk8b ajrliy">Message</span></span></a></div><button class="ajrlhg a'
    'jrlhf ajrth ajra2n ajrhc3 ajrk6n ajrk76 ajrlhj ajrlhi ajrlhh ajrazb ajrjp2 ajrjrc" type='
    '"button" componentkey="00000000-0000-0000-0000-000000000000" aria-label="Plus d’actions '
    'pour {nom}" aria-expanded="false"><span class="ajrlh3 ajrlhy ajrikq ajrjp2 ajrth ajra2n '
    'ajrazb ajrim6 ajrjqq ajrk6n ajrk76 ajrkvt ajrkv4 ajrlh8 ajrlih ajrlif ajrlid ajrlh0 ajrh'
    'qu ajrlip ajrliu"><svg aria-hidden="true"></svg></span></button></div></div></div></div>'
)

PHOTO = "https://media.exemple.test/photo-fictive.jpg"


def personne(rang: int, prefixe: str = "ana") -> dict:
    """Personne inventée n° `rang` : « Ana Test 3 », /in/ana-test-3-1a2b3c/."""
    slug = f"{prefixe}-test-{rang}-1a2b3c"
    return {"slug": slug, "href": f"https://www.linkedin.com/in/{slug}/",
            "nom": f"{prefixe.capitalize()} Test {rang}", "titre": "Product Manager chez Orbique"}


def _document(contenu: str, a_cote: str = "") -> str:
    """Page complète autour de la liste. À côté, une suggestion avec un lien
    /in/ : elle ne doit jamais compter comme une personne de la liste."""
    suggestion = a_cote or (
        '<a href="https://www.linkedin.com/in/zoe-suggestion-9z9z9z/">Zoé Suggestion</a>')
    return ("<!DOCTYPE html><html lang=\"fr\"><head><title>LinkedIn</title>"
            "<style>.x{color:red}</style><script>var t = '/in/script-1/';</script></head><body>"
            "<header><a href=\"https://www.linkedin.com/in/moi-meme-0a0a0a/\">Vous</a></header>"
            '<main><section aria-label="Contenu principal"><section>'
            f"{contenu}</section></section>"
            f'<aside aria-label="De côté">{suggestion}</aside></main></body></html>')


def page_envoyees(personnes, total=None, suivante=None) -> str:
    """Liste « Envoyées » : « Personnes (N) », puis une carte par personne."""
    total = len(personnes) if total is None else total
    cartes = "".join(SEPARATEUR + CARTE_ENVOYEE.format(
        href=p["href"], nom=p["nom"], titre=p["titre"], photo=PHOTO,
        quand="Envoyé il y a 6&nbsp;jours") for p in personnes)
    lien = (f'<a href="{suivante}" aria-label="Suivant">Suivant</a>' if suivante else "")
    return _document("<div>" + ENTETE_ENVOYEES.format(total=total) + OUVERTURE_ENVOYEES
                     + cartes + "</div>" + lien + "</div>")


def page_relations(personnes, total=None, suivante=None) -> str:
    """Liste des relations, ajouts récents d'abord : « N relations », puis
    une carte par personne (lien du profil doublé : photo et nom)."""
    total = len(personnes) if total is None else total
    cartes = "".join(CARTE_RELATION.format(
        rang=i, slug=p["slug"], href=p["href"], nom=p["nom"], titre=p["titre"],
        photo=PHOTO, quand="Connexion le 8 septembre 2026",
        urn=f"ACoAAFICTIF{i:04d}") for i, p in enumerate(personnes))
    lien = (f'<a href="{suivante}" aria-label="Suivant">Suivant</a>' if suivante else "")
    return _document("<div><div>" + ENTETE_RELATIONS.format(total=total) + "</div>"
                     + OUVERTURE_RELATIONS + cartes + "</div>" + lien + "</div>")
