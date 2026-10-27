"""Rythme humain : constantes et compteur de pages LinkedIn par jour."""
import json
from datetime import date, timedelta

from config import ScraperConfig
from utils.human_behavior import DailyLimitsTracker


def test_compteur_de_pages_par_jour(tmp_path):
    t = DailyLimitsTracker(max_pages=3, limits_file=str(tmp_path / "l.json"))
    assert t.can_navigate() and t.remaining_pages() == 3
    t.increment_pages()
    t.increment_pages(2)
    assert t.pages_today == 3 and t.remaining_pages() == 0 and not t.can_navigate()


def test_compteur_de_pages_relu_et_remis_a_zero_le_lendemain(tmp_path):
    f = tmp_path / "l.json"
    t = DailyLimitsTracker(limits_file=str(f))
    t.increment_pages(4)
    assert DailyLimitsTracker(limits_file=str(f)).pages_today == 4
    hier = (date.today() - timedelta(days=1)).isoformat()
    f.write_text(json.dumps({"date": hier, "pages_linkedin": 50}))
    assert DailyLimitsTracker(limits_file=str(f)).pages_today == 0


def test_constantes_du_rythme():
    assert (ScraperConfig.MAX_PAGES_PER_DAY, ScraperConfig.MAX_PROFILES_PER_RUN,
            ScraperConfig.MAX_PAGES_PER_SEANCE, ScraperConfig.PAUSE_ENTRE_SEANCES_MIN) == (60, 25, 25, 20)
    assert ScraperConfig.PAUSE_LECTURE_PROBA == 1 / 6
    assert ScraperConfig.MAX_INVITATIONS_PER_DAY == 20


# ---------------------------------------------------------------------------
# Une seule porte de navigation : comptée, rythmée, arrêtée sur alerte.
# Aucun navigateur : page, réseau et pause sont factices.
# ---------------------------------------------------------------------------

import asyncio
import random

import pytest

from scraper_v2 import SESSION_EXPIREE, ArretLinkedIn, LinkedInScraperV2
from utils.network_manager import NetworkManager

PROFIL_A = "https://www.linkedin.com/in/alice/"
PROFIL_B = "https://www.linkedin.com/in/bob/"
PROFIL_C = "https://www.linkedin.com/in/chloe/"
CHECKPOINT = "https://www.linkedin.com/checkpoint/challenge/AgEx123?ut=1"


class _FauxCorps:
    def __init__(self, page):
        self.page = page

    async def inner_text(self, timeout=None):
        return self.page.texte


class _FaussePage:
    def __init__(self, texte=""):
        self.url = "about:blank"
        self.texte = texte

    def locator(self, selecteur):
        return _FauxCorps(self)


class _FauxNavigateur:
    def __init__(self):
        self.fermetures = 0

    async def close(self):
        self.fermetures += 1


class _FauxPlaywright:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


async def _rien(*a, **k):
    return None


def _scraper(tmp_path, monkeypatch, redirections=None, statuts=None):
    """Scraper dont le réseau note les chargements ; `redirections` : URL
    demandée → URL où LinkedIn renvoie ; `statuts` : URL → statut HTTP."""
    s = LinkedInScraperV2(use_database=False, config_dir=str(tmp_path))
    s.profil_file = str(tmp_path / "profils.csv")
    s.chargements = []

    async def aller(page, url, *a, **k):
        s.chargements.append(url)
        page.url = (redirections or {}).get(url, url)
        s.network_manager.last_status = (statuts or {}).get(url, 200)
        return True

    monkeypatch.setattr(s.network_manager, "safe_page_goto", aller)
    monkeypatch.setattr(s.human, "pause_entre_pages", _rien)
    return s


def _naviguer(s, page, *urls):
    async def tout():
        return [await s._naviguer(page, u) for u in urls]
    return asyncio.run(tout())


def test_chaque_navigation_compte_une_page(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)
    assert _naviguer(s, _FaussePage(), PROFIL_A, PROFIL_B, PROFIL_C) == [True] * 3
    assert s.human.daily_limits.pages_today == 3
    assert s.pages_cette_seance == 3


def test_chaque_navigation_attend_une_pause_humaine(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)
    pauses = []

    async def pause():
        pauses.append(1)

    monkeypatch.setattr(s.human, "pause_entre_pages", pause)
    _naviguer(s, _FaussePage(), PROFIL_A, PROFIL_B)
    assert len(pauses) == 2


def test_budget_jour_refuse_avant_de_charger(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)
    s.human.daily_limits.increment_pages(60)
    with pytest.raises(ArretLinkedIn) as arret:
        _naviguer(s, _FaussePage(), PROFIL_A)
    assert arret.value.motif == "budget_jour"
    assert s.chargements == []
    assert s.human.daily_limits.pages_today == 60


def test_budget_seance(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)
    s.limite_pages_seance = 2
    page = _FaussePage()
    _naviguer(s, page, PROFIL_A, PROFIL_B)
    with pytest.raises(ArretLinkedIn) as arret:
        _naviguer(s, page, PROFIL_C)
    assert arret.value.motif == "budget_seance"
    assert s.chargements == [PROFIL_A, PROFIL_B]


def test_page_alerte_leve_alerte(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch, redirections={PROFIL_A: CHECKPOINT})
    with pytest.raises(ArretLinkedIn) as arret:
        _naviguer(s, _FaussePage(), PROFIL_A)
    assert arret.value.motif == "alerte"
    # La requête est partie : la page compte.
    assert s.human.daily_limits.pages_today == 1


def test_statut_429_leve_alerte(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch, statuts={PROFIL_A: 429})
    with pytest.raises(ArretLinkedIn) as arret:
        _naviguer(s, _FaussePage(), PROFIL_A)
    assert arret.value.motif == "alerte"


def test_texte_d_alerte_hors_page_de_travail(tmp_path, monkeypatch):
    autre = "https://www.linkedin.com/feed/"
    s = _scraper(tmp_path, monkeypatch,
                 redirections={autre: "https://www.linkedin.com/securite/"})
    page = _FaussePage(texte="Nous avons remarqué une activité inhabituelle")
    with pytest.raises(ArretLinkedIn) as arret:
        _naviguer(s, page, autre)
    assert arret.value.motif == "alerte"


def test_redirection_vers_la_connexion_leve_session(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch,
                 redirections={PROFIL_A: "https://www.linkedin.com/login?x=1"})
    with pytest.raises(ArretLinkedIn) as arret:
        _naviguer(s, _FaussePage(), PROFIL_A)
    assert arret.value.motif == "session"


def test_meme_profil_pas_rouvert_dans_le_passage(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)
    page = _FaussePage()
    assert _naviguer(s, page, PROFIL_A, PROFIL_A.rstrip("/") + "?trk=x") == [True, True]
    assert s.chargements == [PROFIL_A]
    assert s.human.daily_limits.pages_today == 1


def test_retour_sur_un_profil_deja_ouvert_recharge_et_compte(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)
    _naviguer(s, _FaussePage(), PROFIL_A, PROFIL_B, PROFIL_A)
    assert s.chargements == [PROFIL_A, PROFIL_B, PROFIL_A]
    assert s.human.daily_limits.pages_today == 3


def test_un_chargement_rate_compte_quand_meme(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)

    async def echec(page, url, *a, **k):
        s.chargements.append(url)
        return False

    monkeypatch.setattr(s.network_manager, "safe_page_goto", echec)
    assert _naviguer(s, _FaussePage(), PROFIL_A) == [False]
    assert s.human.daily_limits.pages_today == 1


def _lancer_par_urls(s, monkeypatch, urls, inviter=False):
    navigateur = _FauxNavigateur()
    page = _FaussePage()

    async def ouvrir(p, cookie, status_callback=None):
        return navigateur, page

    async def profil(pg):
        return {"nom": pg.url.split("/in/")[-1].strip("/"), "poste": "PM", "entreprise": "X"}

    async def inviter_ok(pg, url, nom, message=""):
        return True

    monkeypatch.setattr("scraper_v2.async_playwright", lambda: _FauxPlaywright())
    monkeypatch.setattr(s, "_open_linkedin_page", ouvrir)
    monkeypatch.setattr(s, "extraire_profil_depuis_page", profil)
    monkeypatch.setattr(s, "envoyer_invitation", inviter_ok)
    monkeypatch.setattr(s.human, "browse_page_naturally", _rien)
    monkeypatch.setattr(s.human, "human_delay", _rien)
    monkeypatch.setattr(s.human, "random_long_pause", _rien)
    df = asyncio.run(s.run_url_scraper_async("COOKIE-DE-TEST", urls, inviter=inviter))
    return df, navigateur


def test_page_alerte_arrete_la_boucle_sans_compter_l_action(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch, redirections={PROFIL_B: CHECKPOINT})
    df, navigateur = _lancer_par_urls(s, monkeypatch, [PROFIL_A, PROFIL_B, PROFIL_C],
                                      inviter=True)
    assert len(df) == 1
    assert s.errors == [SESSION_EXPIREE]
    assert s.human.daily_limits.invitations_today == 1
    assert navigateur.fermetures >= 1
    assert PROFIL_C not in s.chargements


def test_budget_pages_atteint_en_cours_garde_le_travail_fait(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)
    s.human.daily_limits.increment_pages(58)
    df, navigateur = _lancer_par_urls(s, monkeypatch, [PROFIL_A, PROFIL_B, PROFIL_C])
    assert len(df) == 2
    assert any("Limite du jour atteinte : 60 pages" in e for e in s.errors)
    assert navigateur.fermetures >= 1
    assert s.chargements == [PROFIL_A, PROFIL_B]


def test_budget_seance_atteint_le_dit(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)
    s.limite_pages_seance = 1
    df, _ = _lancer_par_urls(s, monkeypatch, [PROFIL_A, PROFIL_B])
    assert len(df) == 1
    assert s.errors == ["Séance terminée : 1 pages consultées. "
                        "Prochaine séance possible dans 20 minutes."]


def test_pause_entre_pages_respecte_les_bornes(monkeypatch):
    from utils.human_behavior import HumanBehavior
    attentes = []

    async def noter(secondes):
        attentes.append(secondes)

    monkeypatch.setattr("utils.human_behavior.asyncio.sleep", noter)
    random.seed(7)
    h = HumanBehavior()
    for _ in range(300):
        attentes.clear()
        asyncio.run(h.pause_entre_pages())
        total = sum(attentes)
        assert 8 <= total <= 20 or 38 <= total <= 110, total
        h.longues = getattr(h, "longues", 0) + (total > 20)
    # Une pause « lecture » environ une fois sur six, pas jamais ni toujours.
    assert 20 <= h.longues <= 90


def test_warmup_passe_par_la_porte(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)
    monkeypatch.setattr(s.human, "browse_page_naturally", _rien)
    monkeypatch.setattr("utils.human_behavior.asyncio.sleep", _rien)
    page = _FaussePage()
    assert asyncio.run(s.human.warmup_session(page, naviguer=s._naviguer)) is True
    assert s.chargements == ["https://www.linkedin.com/feed/"]
    assert s.human.daily_limits.pages_today == 1


def test_warmup_sur_page_d_alerte_s_arrete(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch,
                 redirections={"https://www.linkedin.com/feed/": CHECKPOINT})
    monkeypatch.setattr("utils.human_behavior.asyncio.sleep", _rien)
    with pytest.raises(ArretLinkedIn):
        asyncio.run(s.human.warmup_session(_FaussePage(), naviguer=s._naviguer))


def test_safe_page_goto_garde_le_statut_de_la_reponse():
    class Reponse:
        status = 429

    class Page:
        async def goto(self, url, **k):
            return Reponse()

    nm = NetworkManager()
    assert asyncio.run(nm.safe_page_goto(Page(), PROFIL_A)) is True
    assert nm.last_status == 429


def test_plafonds_par_passage():
    import inspect
    from config import ScraperConfig as C
    sig = inspect.signature
    assert sig(LinkedInScraperV2.verifier_acceptations_async).parameters["max_check"].default \
        == C.MAX_VERIFICATIONS_PAR_PASSAGE == 10
    assert sig(LinkedInScraperV2.envoyer_messages_async).parameters["max_msg"].default \
        == C.MAX_MESSAGES_PAR_SEANCE == 10
    import ui.page_messages as pm
    assert pm.MAX_ENVOIS == C.MAX_MESSAGES_PAR_SEANCE


# --- Recherche : une seule pause entre deux pas, jamais deux d'affilée ------

def test_recherche_une_seule_pause_entre_deux_pas(tmp_path, monkeypatch):
    """Pause avant chaque invitation sauf la première d'une page fraîchement
    chargée : la porte attend déjà avant la page suivante, et rien après la
    dernière invitation avant de fermer Chrome."""
    from utils.human_behavior import HumanBehavior
    s = _scraper(tmp_path, monkeypatch)
    journal = []

    async def aller(page, url, *a, **k):
        journal.append("page " + url.rsplit("page=", 1)[-1])
        page.url = url
        return True

    async def pause(self):
        journal.append("pause")

    async def vrai(*a, **k):
        return True

    def personne(n):
        return {"nom": n, "url": f"https://www.linkedin.com/in/{n}/",
                "poste": "PM", "entreprise": "X"}

    async def profils(page):
        return [personne("a"), personne("b")] if page.url.endswith("page=1") \
            else [personne("c"), personne("d")]

    async def inviter(page, url, nom, message=""):
        journal.append("invite " + nom)
        return True

    async def ouvrir(p, cookie, status_callback=None):
        return _FauxNavigateur(), _FaussePage()

    monkeypatch.setattr(s.network_manager, "safe_page_goto", aller)
    monkeypatch.setattr(HumanBehavior, "pause_entre_pages", pause)
    for nom in ("page_entry_behavior", "browse_page_naturally", "simulate_distraction"):
        monkeypatch.setattr(HumanBehavior, nom, _rien)
    monkeypatch.setattr(HumanBehavior, "check_safety", vrai)
    monkeypatch.setattr("scraper_v2.async_playwright", lambda: _FauxPlaywright())
    monkeypatch.setattr(s, "_open_linkedin_page", ouvrir)
    monkeypatch.setattr(s, "extraire_profils_page", profils)
    monkeypatch.setattr(s, "envoyer_invitation", inviter)
    monkeypatch.setattr(s, "_charger_urls_scrappees", lambda: set())

    df = asyncio.run(s.run_scraper_async("C", "pm", None, 3, [], inviter=True))

    assert len(df) == 3
    assert journal == ["pause", "page 1", "invite a", "pause", "invite b",
                       "pause", "page 2", "invite c"]


# --- Panneau « profils similaires » : une page, comptée et contrôlée --------

class _FauxLien:
    def __init__(self, page):
        self.page = page

    async def scroll_into_view_if_needed(self):
        pass

    async def bounding_box(self):
        return None

    async def click(self):
        self.page.clics += 1
        self.page.url = self.page.url_apres_clic


class _PageAvecPanneau(_FaussePage):
    def __init__(self, url_apres_clic):
        super().__init__()
        self.url = PROFIL_A
        self.url_apres_clic = url_apres_clic
        self.clics = 0

    async def wait_for_selector(self, selecteur, **k):
        return _FauxLien(self)

    async def wait_for_function(self, js, **k):
        return True


def _ouvrir_panneau(s, url_apres_clic=PROFIL_A + "overlay/browsemap-recommendations/"):
    page = _PageAvecPanneau(url_apres_clic)
    return page, asyncio.run(s._ouvrir_panneau(page))


def test_ouvrir_le_panneau_compte_une_page(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)
    monkeypatch.setattr(s.human, "human_delay", _rien)
    page, echec = _ouvrir_panneau(s)
    assert echec is None and page.clics == 1
    assert s.human.daily_limits.pages_today == 1 and s.pages_cette_seance == 1


def test_panneau_refuse_avant_le_clic_si_budget_epuise(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)
    monkeypatch.setattr(s.human, "human_delay", _rien)
    s.limite_pages_seance = 0
    page = _PageAvecPanneau(PROFIL_A)
    with pytest.raises(ArretLinkedIn) as arret:
        asyncio.run(s._ouvrir_panneau(page))
    assert arret.value.motif == "budget_seance" and page.clics == 0
    s.limite_pages_seance = None
    s.human.daily_limits.increment_pages(60)
    with pytest.raises(ArretLinkedIn) as arret:
        asyncio.run(s._ouvrir_panneau(page))
    assert arret.value.motif == "budget_jour" and page.clics == 0


def test_panneau_qui_mene_a_une_alerte_leve_alerte(tmp_path, monkeypatch):
    s = _scraper(tmp_path, monkeypatch)
    monkeypatch.setattr(s.human, "human_delay", _rien)
    with pytest.raises(ArretLinkedIn) as arret:
        _ouvrir_panneau(s, url_apres_clic=CHECKPOINT)
    assert arret.value.motif == "alerte"
    assert s.human.daily_limits.pages_today == 1


def test_deux_pages_de_resultats_ne_sont_pas_le_meme_profil(tmp_path, monkeypatch):
    # « &page=2 » ne diffère de « &page=1 » que par la requête : la règle
    # « profil déjà ouvert » ne doit pas empêcher de charger la suivante.
    s = _scraper(tmp_path, monkeypatch)
    base = "https://www.linkedin.com/search/results/people/?keywords=pm"
    _naviguer(s, _FaussePage(), base + "&page=1", base + "&page=2")
    assert s.chargements == [base + "&page=1", base + "&page=2"]
