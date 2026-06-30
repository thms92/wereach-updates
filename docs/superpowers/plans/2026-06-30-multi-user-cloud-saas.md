# LinkedIn Scraper – Mise en ligne multi-utilisateurs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre l'outil accessible en ligne à un groupe restreint (≤ 10 personnes en SSO), chaque utilisateur travaillant avec son propre compte LinkedIn (cookie, base, file de jobs et proxy isolés par personne).

**Architecture:** L'app Streamlit + Playmaker reste mono-processus mais devient *multi-locataire*. Cloudflare Access place une couche SSO devant l'app et transmet l'email authentifié dans l'en-tête HTTP `Cf-Access-Authenticated-User-Email`. L'app dérive de cet email un répertoire isolé `data/users/<user_id>/` contenant cookie chiffré, base SQLite, file de jobs, CSV et proxy. Le scraper injecte le proxy de l'utilisateur courant dans le contexte Playwright. Le déploiement se fait sur un petit serveur cloud (VPS) en Docker, avec un volume persistant pour `data/`.

**Tech Stack:** Python 3.11, Streamlit ≥ 1.37 (pour `st.context.headers`), Playwright (Chromium), SQLite, cryptography (Fernet), pytest (tests), Docker, Cloudflare Tunnel + Cloudflare Access.

## Global Constraints

- Python 3.11 (image `python:3.11-slim`, déjà en place dans `Dockerfile`).
- **Rétro-compatibilité obligatoire** : tout changement de constructeur (`CookieManager`, `QueueManager`) doit garder le comportement actuel quand aucun argument n'est passé (chemins `config/...`).
- Streamlit doit être bumpé à `>=1.37.0` dans `requirements.txt` (l'accès `st.context.headers` n'existe pas avant).
- Les identifiants de proxy et le cookie LinkedIn sont **chiffrés au repos** avec la clé Fernet existante (`secret.key`), jamais stockés en clair.
- Aucune donnée d'un utilisateur ne doit être lisible par un autre : tout passe par `data/users/<user_id>/`.
- L'`user_id` est dérivé de l'email par hash SHA-256 tronqué (16 hex) — jamais l'email brut comme nom de dossier.
- En local (hors Cloudflare), l'app retombe sur l'email de `DEV_USER_EMAIL` (env) ou `local@dev` — pour pouvoir développer/tester sans SSO.
- TDD strict : test qui échoue d'abord, puis implémentation minimale. Commits fréquents.

---

## PARTIE A — Isolation multi-utilisateurs (code, TDD)

### Task 1: Mettre en place pytest

**Files:**
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: rien.
- Produces: une suite pytest exécutable depuis la racine du projet avec la racine sur le `pythonpath`.

- [ ] **Step 1: Créer le fichier de dépendances de dev**

`requirements-dev.txt` :
```
pytest>=8.0.0
```

- [ ] **Step 2: Configurer pytest pour importer les modules de la racine**

`pytest.ini` :
```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 3: Créer le package de tests**

`tests/__init__.py` : fichier vide.

- [ ] **Step 4: Écrire un test smoke (qui échoue tant que pytest n'est pas installé)**

`tests/test_smoke.py` :
```python
def test_smoke():
    assert 1 + 1 == 2
```

- [ ] **Step 5: Installer pytest et lancer**

Run :
```bash
pip install -r requirements-dev.txt
pytest tests/test_smoke.py -v
```
Expected : `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt pytest.ini tests/__init__.py tests/test_smoke.py
git commit -m "test: add pytest scaffolding"
```

---

### Task 2: Module `user_context` (identité + chemins par utilisateur)

**Files:**
- Create: `utils/user_context.py`
- Test: `tests/test_user_context.py`

**Interfaces:**
- Consumes: rien (fonctions pures + dataclass).
- Produces :
  - `user_id_from_email(email: str) -> str` — 16 hex stables.
  - `resolve_user_email(headers: dict, dev_fallback: str | None) -> str` — lit `Cf-Access-Authenticated-User-Email` (insensible à la casse), sinon `dev_fallback`, sinon `"local@dev"`.
  - `@dataclass UserPaths` avec attributs `base, config_dir, cookie_file, key_file, db_file, queue_file, profiles_csv, proxy_file` (tous `Path`).
  - `user_paths_for(email: str, root: str = "data/users") -> UserPaths` — crée `base` et `config_dir`, renvoie l'objet.

- [ ] **Step 1: Écrire les tests (qui échouent)**

`tests/test_user_context.py` :
```python
from pathlib import Path
from utils.user_context import (
    user_id_from_email, resolve_user_email, user_paths_for, UserPaths,
)


def test_user_id_is_stable_and_safe():
    a = user_id_from_email("Alice@Example.com")
    b = user_id_from_email("alice@example.com")
    assert a == b                      # insensible à la casse
    assert len(a) == 16
    assert a.isalnum()                 # sûr comme nom de dossier


def test_user_id_differs_per_user():
    assert user_id_from_email("a@x.com") != user_id_from_email("b@x.com")


def test_resolve_email_from_cloudflare_header():
    headers = {"Cf-Access-Authenticated-User-Email": "bob@corp.com"}
    assert resolve_user_email(headers, None) == "bob@corp.com"


def test_resolve_email_header_case_insensitive():
    headers = {"cf-access-authenticated-user-email": "bob@corp.com"}
    assert resolve_user_email(headers, None) == "bob@corp.com"


def test_resolve_email_falls_back_to_dev():
    assert resolve_user_email({}, "dev@me.com") == "dev@me.com"
    assert resolve_user_email({}, None) == "local@dev"


def test_user_paths_isolated_and_created(tmp_path):
    p1 = user_paths_for("a@x.com", root=str(tmp_path))
    p2 = user_paths_for("b@x.com", root=str(tmp_path))
    assert p1.base != p2.base
    assert p1.base.is_dir()
    assert p1.config_dir.is_dir()
    assert p1.cookie_file.parent == p1.config_dir
    assert isinstance(p1, UserPaths)
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run : `pytest tests/test_user_context.py -v`
Expected : FAIL — `ModuleNotFoundError: No module named 'utils.user_context'`.

- [ ] **Step 3: Implémenter le module**

`utils/user_context.py` :
```python
# -*- coding: utf-8 -*-
"""Identité et chemins isolés par utilisateur (multi-locataire)."""
import hashlib
from dataclasses import dataclass
from pathlib import Path

CF_HEADER = "cf-access-authenticated-user-email"
DEFAULT_DEV_EMAIL = "local@dev"


def user_id_from_email(email: str) -> str:
    norm = (email or "").strip().lower().encode("utf-8")
    return hashlib.sha256(norm).hexdigest()[:16]


def resolve_user_email(headers: dict, dev_fallback: str | None) -> str:
    for k, v in (headers or {}).items():
        if k.lower() == CF_HEADER and v:
            return v.strip()
    return (dev_fallback or DEFAULT_DEV_EMAIL).strip()


@dataclass
class UserPaths:
    base: Path
    config_dir: Path
    cookie_file: Path
    key_file: Path
    db_file: Path
    queue_file: Path
    profiles_csv: Path
    proxy_file: Path


def user_paths_for(email: str, root: str = "data/users") -> UserPaths:
    uid = user_id_from_email(email)
    base = Path(root) / uid
    config_dir = base / "config"
    base.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    return UserPaths(
        base=base,
        config_dir=config_dir,
        cookie_file=config_dir / "cookie.txt",
        key_file=config_dir / "secret.key",
        db_file=base / "profiles.db",
        queue_file=config_dir / "queue.json",
        profiles_csv=base / "profils_scrapes.csv",
        proxy_file=config_dir / "proxy.enc",
    )
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run : `pytest tests/test_user_context.py -v`
Expected : `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add utils/user_context.py tests/test_user_context.py
git commit -m "feat: per-user identity and isolated paths"
```

---

### Task 3: `CookieManager` accepte un répertoire par utilisateur

**Files:**
- Modify: `cookie_utils.py:13-16`
- Test: `tests/test_cookie_manager.py`

**Interfaces:**
- Consumes: `UserPaths.config_dir` (str).
- Produces: `CookieManager(config_dir: str = None)` — si `None`, comportement actuel (`config/`). La clé et le cookie vivent sous `config_dir`.

- [ ] **Step 1: Écrire le test (qui échoue)**

`tests/test_cookie_manager.py` :
```python
from cookie_utils import CookieManager


def test_cookies_isolated_per_directory(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    cm_a = CookieManager(config_dir=str(dir_a))
    cm_b = CookieManager(config_dir=str(dir_b))

    cm_a.save_cookie("AQEDcookieA")
    cm_b.save_cookie("AQEDcookieB")

    assert cm_a.load_cookie() == "AQEDcookieA"
    assert cm_b.load_cookie() == "AQEDcookieB"
    assert (dir_a / "cookie.txt").exists()
    assert (dir_b / "cookie.txt").exists()


def test_default_dir_is_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cm = CookieManager()
    cm.save_cookie("AQEDdefault")
    assert (tmp_path / "config" / "cookie.txt").exists()
```

- [ ] **Step 2: Lancer pour vérifier l'échec**

Run : `pytest tests/test_cookie_manager.py -v`
Expected : FAIL — `TypeError: __init__() got an unexpected keyword argument 'config_dir'`.

- [ ] **Step 3: Modifier le constructeur**

Dans `cookie_utils.py`, remplacer la méthode `__init__` actuelle :
```python
    def __init__(self):
        self.key_file = os.path.join(ScraperConfig.CONFIG_DIR, "secret.key")
        self.cookie_file = ScraperConfig.COOKIE_FILE
        self.key = self._get_or_create_key()
```
par :
```python
    def __init__(self, config_dir: str = None):
        cfg_dir = config_dir or ScraperConfig.CONFIG_DIR
        os.makedirs(cfg_dir, exist_ok=True)
        self.key_file = os.path.join(cfg_dir, "secret.key")
        self.cookie_file = os.path.join(cfg_dir, "cookie.txt")
        self.key = self._get_or_create_key()
```

- [ ] **Step 4: Lancer pour vérifier que ça passe**

Run : `pytest tests/test_cookie_manager.py -v`
Expected : `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add cookie_utils.py tests/test_cookie_manager.py
git commit -m "feat: CookieManager supports per-user config_dir"
```

---

### Task 4: `QueueManager` accepte un fichier de file par utilisateur

**Files:**
- Modify: `queue_manager.py:66-72` (constructeur)
- Modify: `queue_manager.py:363-375` (`sauver`/`charger` → utiliser `self.queue_file`)
- Test: `tests/test_queue_manager.py`

**Interfaces:**
- Consumes: `UserPaths.queue_file` (str).
- Produces: `QueueManager(queue_file: str = None)` — si `None`, comportement actuel (`config/queue.json`).

- [ ] **Step 1: Écrire le test (qui échoue)**

`tests/test_queue_manager.py` :
```python
from queue_manager import QueueManager


def test_queue_file_isolated(tmp_path):
    f_a = tmp_path / "a" / "queue.json"
    f_b = tmp_path / "b" / "queue.json"
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    qm_a = QueueManager(queue_file=str(f_a))
    qm_a.ajouter_entreprise("EDF")
    qm_a.sauver()

    qm_b = QueueManager(queue_file=str(f_b))
    qm_b.ajouter_entreprise("Engie")
    qm_b.sauver()

    assert f_a.exists() and f_b.exists()

    reload_a = QueueManager(queue_file=str(f_a))
    reload_a.charger()
    noms = [j.entreprise for j in reload_a.jobs]
    assert noms == ["EDF"]            # n'a PAS chargé la file de b


def test_default_queue_file():
    qm = QueueManager()
    assert qm.queue_file == "config/queue.json"
```

- [ ] **Step 2: Lancer pour vérifier l'échec**

Run : `pytest tests/test_queue_manager.py -v`
Expected : FAIL — `TypeError: __init__() got an unexpected keyword argument 'queue_file'`.

- [ ] **Step 3: Modifier le constructeur**

Dans `queue_manager.py`, remplacer :
```python
    def __init__(self):
        self.config = QueueConfig()
        self.jobs: List[ScrapingJob] = []
        self.is_running = False
        self.current_job_index = -1
        self.all_results: List[pd.DataFrame] = []
```
par :
```python
    def __init__(self, queue_file: str = None):
        self.queue_file = queue_file or self.QUEUE_FILE
        self.config = QueueConfig()
        self.jobs: List[ScrapingJob] = []
        self.is_running = False
        self.current_job_index = -1
        self.all_results: List[pd.DataFrame] = []
```

- [ ] **Step 4: Faire pointer `sauver`/`charger` sur l'instance**

Dans `queue_manager.py`, aux lignes ~363-375, remplacer les `self.QUEUE_FILE` par `self.queue_file` :
```python
        os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
        with open(self.queue_file, "w", encoding="utf-8") as f:
```
et dans `charger` :
```python
        if not os.path.exists(self.queue_file):
            return
        ...
            with open(self.queue_file, "r", encoding="utf-8") as f:
```
(Conserver `QUEUE_FILE = "config/queue.json"` comme valeur par défaut de classe.)

- [ ] **Step 5: Lancer pour vérifier que ça passe**

Run : `pytest tests/test_queue_manager.py -v`
Expected : `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add queue_manager.py tests/test_queue_manager.py
git commit -m "feat: QueueManager supports per-user queue_file"
```

---

### Task 5: Stockage chiffré du proxy par utilisateur

**Files:**
- Create: `utils/proxy_store.py`
- Test: `tests/test_proxy_store.py`

**Interfaces:**
- Consumes: `UserPaths.proxy_file` (Path/str), `UserPaths.key_file` (réutilise la clé Fernet créée par `CookieManager`, ou la crée).
- Produces :
  - `save_proxy(proxy_file, key_file, proxy: dict) -> None` — chiffre et écrit `{server, username, password}`.
  - `load_proxy(proxy_file, key_file) -> dict | None` — déchiffre, ou `None` si absent.
  - Format `proxy` Playwright : `{"server": "http://host:port", "username": "...", "password": "..."}`.

- [ ] **Step 1: Écrire le test (qui échoue)**

`tests/test_proxy_store.py` :
```python
from utils.proxy_store import save_proxy, load_proxy


def test_roundtrip_encrypted(tmp_path):
    pf = tmp_path / "proxy.enc"
    kf = tmp_path / "secret.key"
    proxy = {"server": "http://1.2.3.4:8000", "username": "u", "password": "p"}

    save_proxy(str(pf), str(kf), proxy)

    assert pf.exists()
    raw = pf.read_bytes()
    assert b"1.2.3.4" not in raw           # chiffré, pas en clair
    assert load_proxy(str(pf), str(kf)) == proxy


def test_load_missing_returns_none(tmp_path):
    assert load_proxy(str(tmp_path / "none.enc"), str(tmp_path / "k.key")) is None
```

- [ ] **Step 2: Lancer pour vérifier l'échec**

Run : `pytest tests/test_proxy_store.py -v`
Expected : FAIL — `ModuleNotFoundError: No module named 'utils.proxy_store'`.

- [ ] **Step 3: Implémenter le module**

`utils/proxy_store.py` :
```python
# -*- coding: utf-8 -*-
"""Stockage chiffré (Fernet) des identifiants de proxy par utilisateur."""
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet


def _get_or_create_key(key_file: str) -> bytes:
    if os.path.exists(key_file):
        return Path(key_file).read_bytes()
    key = Fernet.generate_key()
    Path(key_file).parent.mkdir(parents=True, exist_ok=True)
    Path(key_file).write_bytes(key)
    return key


def save_proxy(proxy_file: str, key_file: str, proxy: dict) -> None:
    f = Fernet(_get_or_create_key(key_file))
    token = f.encrypt(json.dumps(proxy).encode("utf-8"))
    Path(proxy_file).parent.mkdir(parents=True, exist_ok=True)
    Path(proxy_file).write_bytes(token)


def load_proxy(proxy_file: str, key_file: str):
    if not os.path.exists(proxy_file):
        return None
    f = Fernet(_get_or_create_key(key_file))
    data = f.decrypt(Path(proxy_file).read_bytes())
    return json.loads(data.decode("utf-8"))
```

- [ ] **Step 4: Lancer pour vérifier que ça passe**

Run : `pytest tests/test_proxy_store.py -v`
Expected : `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add utils/proxy_store.py tests/test_proxy_store.py
git commit -m "feat: encrypted per-user proxy storage"
```

---

### Task 6: Injection du proxy dans le contexte Playwright

**Files:**
- Modify: `scraper_v2.py:39` (constructeur — stocker `self._proxy`)
- Create (méthode): `scraper_v2.py` — `_context_kwargs(self, profile, viewport)` factorisant les arguments de `new_context`
- Modify: `scraper_v2.py:741-746` et `scraper_v2.py:1319-1324` (utiliser `_context_kwargs`)
- Test: `tests/test_context_kwargs.py`

**Interfaces:**
- Consumes: `proxy: dict | None` (format Playwright de Task 5).
- Produces:
  - `LinkedInScraperV2.__init__(self, use_database=True, proxy: dict = None)` — stocke `self._proxy = proxy`.
  - `LinkedInScraperV2._context_kwargs(self, profile, viewport) -> dict` — renvoie les kwargs de `new_context`, incluant `proxy` si présent.

- [ ] **Step 1: Écrire le test (qui échoue)**

`tests/test_context_kwargs.py` :
```python
from types import SimpleNamespace
from scraper_v2 import LinkedInScraperV2


def _fake_profile():
    return SimpleNamespace(
        user_agent="UA", locale="fr-FR", timezone="Europe/Paris",
    )


def test_context_kwargs_without_proxy():
    s = LinkedInScraperV2(use_database=False)
    kw = s._context_kwargs(_fake_profile(), {"width": 1280, "height": 800})
    assert "proxy" not in kw
    assert kw["user_agent"] == "UA"
    assert kw["locale"] == "fr-FR"


def test_context_kwargs_with_proxy():
    proxy = {"server": "http://1.2.3.4:8000", "username": "u", "password": "p"}
    s = LinkedInScraperV2(use_database=False, proxy=proxy)
    kw = s._context_kwargs(_fake_profile(), {"width": 1280, "height": 800})
    assert kw["proxy"] == proxy
```

- [ ] **Step 2: Lancer pour vérifier l'échec**

Run : `pytest tests/test_context_kwargs.py -v`
Expected : FAIL — `TypeError: __init__() got an unexpected keyword argument 'proxy'`.

- [ ] **Step 3: Stocker le proxy dans le constructeur**

Dans `scraper_v2.py`, remplacer la signature (ligne ~39) :
```python
    def __init__(self, use_database: bool = True):
```
par :
```python
    def __init__(self, use_database: bool = True, proxy: dict = None):
        self._proxy = proxy
```
(Garder le reste du corps `__init__` inchangé, juste après cette ligne.)

- [ ] **Step 4: Ajouter la méthode `_context_kwargs`**

Ajouter dans la classe `LinkedInScraperV2` (par ex. juste après `__init__`) :
```python
    def _context_kwargs(self, profile, viewport) -> dict:
        kwargs = {
            "viewport": viewport,
            "user_agent": profile.user_agent,
            "locale": profile.locale,
            "timezone_id": profile.timezone,
        }
        if self._proxy:
            kwargs["proxy"] = self._proxy
        return kwargs
```

- [ ] **Step 5: Lancer pour vérifier que ça passe**

Run : `pytest tests/test_context_kwargs.py -v`
Expected : `2 passed`.

- [ ] **Step 6: Brancher les deux sites `new_context`**

Aux deux endroits (`scraper_v2.py` ~741 et ~1319), remplacer :
```python
                context = await browser.new_context(
                    viewport=viewport,
                    user_agent=profile.user_agent,
                    locale=profile.locale,
                    timezone_id=profile.timezone,
                )
```
par :
```python
                context = await browser.new_context(
                    **self._context_kwargs(profile, viewport)
                )
```

- [ ] **Step 7: Vérifier l'absence de régression**

Run : `pytest -v`
Expected : tous les tests passent. Puis vérifier la syntaxe du scraper :
```bash
python3 -c "import ast; ast.parse(open('scraper_v2.py').read()); print('OK')"
```
Expected : `OK`.

- [ ] **Step 8: Commit**

```bash
git add scraper_v2.py tests/test_context_kwargs.py
git commit -m "feat: inject per-user proxy into Playwright context"
```

---

### Task 7: Câbler l'app sur l'utilisateur courant

**Files:**
- Modify: `app_advanced.py:7-21` (imports)
- Modify: `app_advanced.py:59-75` (initialisation des managers → par utilisateur)
- Modify: `scraper_v2_sync.py:21-45` (passer `proxy` à `run_scraper`)
- Test: `tests/test_app_user_wiring.py`

**Interfaces:**
- Consumes: `resolve_user_email`, `user_paths_for` (Task 2), `CookieManager(config_dir=...)` (Task 3), `QueueManager(queue_file=...)` (Task 4), `DatabaseManager(db_file=...)` (existant), `load_proxy` (Task 5), `LinkedInScraperV2(..., proxy=...)` (Task 6).
- Produces: `app_advanced.current_user_email() -> str` (wrapper Streamlit testable indirectement via `resolve_user_email`).

- [ ] **Step 1: Écrire le test du wrapper d'email (qui échoue)**

`tests/test_app_user_wiring.py` :
```python
from utils.user_context import resolve_user_email, user_paths_for


def test_wiring_uses_resolved_email(tmp_path):
    # Simule l'en-tête Cloudflare → chemins isolés
    email = resolve_user_email(
        {"Cf-Access-Authenticated-User-Email": "carol@corp.com"}, None
    )
    paths = user_paths_for(email, root=str(tmp_path))
    assert "carol" not in str(paths.base)      # dossier = hash, pas l'email
    assert paths.cookie_file.parent.is_dir()
```

- [ ] **Step 2: Lancer pour vérifier qu'il passe déjà (sanity, dépend de Task 2)**

Run : `pytest tests/test_app_user_wiring.py -v`
Expected : `1 passed` (valide que l'API combinée fonctionne ; sert de garde-fou pour le câblage manuel ci-dessous).

- [ ] **Step 3: Ajouter les imports dans l'app**

Dans `app_advanced.py`, après `import os` (ligne ~12), ajouter :
```python
from utils.user_context import resolve_user_email, user_paths_for
from utils.proxy_store import load_proxy
```

- [ ] **Step 4: Ajouter le wrapper d'email Streamlit**

Dans `app_advanced.py`, juste avant le bloc d'initialisation des managers (ligne ~59), ajouter :
```python
def current_user_email() -> str:
    try:
        headers = dict(st.context.headers)
    except Exception:
        headers = {}
    return resolve_user_email(headers, os.getenv("DEV_USER_EMAIL"))
```

- [ ] **Step 5: Initialiser les managers par utilisateur**

Dans `app_advanced.py`, remplacer le bloc d'init (lignes ~59-75) :
```python
if 'db' not in st.session_state:
    st.session_state.db = DatabaseManager()

if 'cookie_manager' not in st.session_state:
    st.session_state.cookie_manager = CookieManager()

if 'export_manager' not in st.session_state:
    st.session_state.export_manager = ExportManager()

if 'queue_manager' not in st.session_state:
    st.session_state.queue_manager = QueueManager()
    st.session_state.queue_manager.charger()

if 'global_cookie' not in st.session_state:
    cookie_saved = st.session_state.cookie_manager.load_cookie()
    st.session_state.global_cookie = cookie_saved or ""
```
par :
```python
_email = current_user_email()
if st.session_state.get('user_email') != _email:
    # Nouvel utilisateur (ou première visite) → (ré)initialiser tout le contexte
    paths = user_paths_for(_email)
    st.session_state.user_email = _email
    st.session_state.user_paths = paths
    st.session_state.db = DatabaseManager(db_file=str(paths.db_file))
    st.session_state.cookie_manager = CookieManager(config_dir=str(paths.config_dir))
    st.session_state.export_manager = ExportManager()
    st.session_state.queue_manager = QueueManager(queue_file=str(paths.queue_file))
    st.session_state.queue_manager.charger()
    cookie_saved = st.session_state.cookie_manager.load_cookie()
    st.session_state.global_cookie = cookie_saved or ""
    st.session_state.user_proxy = load_proxy(
        str(paths.proxy_file), str(paths.key_file)
    )
```

- [ ] **Step 6: Passer le proxy au scraper (wrapper sync)**

Dans `scraper_v2_sync.py`, ajouter un paramètre `proxy` à `run_scraper` (ligne ~25) et le transmettre au scraper. Remplacer la signature :
```python
    def run_scraper(
        self,
        cookie: str,
```
par :
```python
    def run_scraper(
        self,
        cookie: str,
        proxy: dict = None,
```
puis, à l'endroit où `LinkedInScraperV2(...)` est instancié dans ce fichier, ajouter `proxy=proxy`. (Repérer la ligne `LinkedInScraperV2(` et y ajouter l'argument.)

- [ ] **Step 7: Transmettre `user_proxy` lors du lancement d'un scraping**

Dans `app_advanced.py`, à chaque appel qui déclenche un scraping via le scraper sync (chercher `run_scraper(`), ajouter l'argument `proxy=st.session_state.get('user_proxy')`. Exemple :
```python
result = scraper.run_scraper(cookie=..., proxy=st.session_state.get('user_proxy'), ...)
```

- [ ] **Step 8: Vérification manuelle multi-utilisateur (local)**

Run (deux faux utilisateurs, sans Streamlit, pour prouver l'isolation) :
```bash
python3 - <<'PY'
from utils.user_context import user_paths_for
from cookie_utils import CookieManager
a = user_paths_for("a@x.com", root="data/users")
b = user_paths_for("b@x.com", root="data/users")
CookieManager(config_dir=str(a.config_dir)).save_cookie("AQEDaaa")
CookieManager(config_dir=str(b.config_dir)).save_cookie("AQEDbbb")
assert CookieManager(config_dir=str(a.config_dir)).load_cookie() == "AQEDaaa"
assert CookieManager(config_dir=str(b.config_dir)).load_cookie() == "AQEDbbb"
print("✅ Isolation cookie par utilisateur OK")
PY
```
Expected : `✅ Isolation cookie par utilisateur OK`. Puis nettoyer : `rm -rf data/users/`.

- [ ] **Step 9: Vérifier toute la suite**

Run : `pytest -v`
Expected : tous les tests passent.

- [ ] **Step 10: Commit**

```bash
git add app_advanced.py scraper_v2_sync.py tests/test_app_user_wiring.py
git commit -m "feat: wire app to per-user context (cookie/db/queue/proxy)"
```

---

### Task 8: UI de configuration du proxy par utilisateur

**Files:**
- Modify: `app_advanced.py` (ajouter un expander « Mon proxy » dans la barre latérale ou l'onglet config)
- Test: couvert par `tests/test_proxy_store.py` (logique) ; l'UI est vérifiée manuellement.

**Interfaces:**
- Consumes: `save_proxy`, `load_proxy` (Task 5), `st.session_state.user_paths`.
- Produces: rien de nouveau (écrit le `proxy.enc` de l'utilisateur courant).

- [ ] **Step 1: Ajouter l'import**

Dans `app_advanced.py`, compléter l'import proxy_store :
```python
from utils.proxy_store import load_proxy, save_proxy
```

- [ ] **Step 2: Ajouter le formulaire proxy**

Dans `app_advanced.py`, dans la barre latérale (`with st.sidebar:`), ajouter :
```python
with st.sidebar.expander("🌐 Mon proxy (recommandé)"):
    paths = st.session_state.user_paths
    cur = st.session_state.get('user_proxy') or {}
    server = st.text_input("Serveur (http://host:port)", value=cur.get("server", ""))
    p_user = st.text_input("Login proxy", value=cur.get("username", ""))
    p_pass = st.text_input("Mot de passe proxy", type="password",
                           value=cur.get("password", ""))
    if st.button("💾 Enregistrer mon proxy"):
        if server.strip():
            proxy = {"server": server.strip(),
                     "username": p_user.strip(),
                     "password": p_pass}
            save_proxy(str(paths.proxy_file), str(paths.key_file), proxy)
            st.session_state.user_proxy = proxy
            st.success("Proxy enregistré ✅")
        else:
            st.warning("Indique au moins un serveur.")
```

- [ ] **Step 3: Vérification manuelle**

Run :
```bash
streamlit run app_advanced.py
```
Puis dans la barre latérale : saisir un proxy de test, enregistrer, recharger la page → les valeurs persistent et `data/users/<id>/config/proxy.enc` existe (et est chiffré).

- [ ] **Step 4: Commit**

```bash
git add app_advanced.py
git commit -m "feat: per-user proxy configuration UI"
```

---

## PARTIE B — Déploiement cloud + SSO (runbook ops)

> Cette partie n'est pas du code testable unitairement : c'est une procédure d'infrastructure. Chaque étape se vérifie par observation directe (curl, accès navigateur).

### Task 9: Persistance des données par utilisateur dans Docker

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.gitignore` (ignorer `data/`)

- [ ] **Step 1: Monter un volume dédié `data/` (et ne plus monter tout le code en prod)**

Remplacer le `volumes:` actuel de `docker-compose.yml` par un volume nommé persistant :
```yaml
    volumes:
      - scraper_data:/app/data
```
et ajouter en bas du fichier :
```yaml
volumes:
  scraper_data:
```
(Ainsi `data/users/<id>/...` survit aux redéploiements. Le code, lui, vient de l'image construite.)

- [ ] **Step 2: Ignorer les données locales**

Ajouter à `.gitignore` :
```
data/
logs/
```

- [ ] **Step 3: Vérifier le build et le démarrage**

Run :
```bash
docker compose up -d --build
curl -sf http://localhost:8501/_stcore/health && echo " OK"
```
Expected : ` OK`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .gitignore
git commit -m "chore: persistent data volume for per-user storage"
```

### Task 10: Provisionner le serveur cloud (GRATUIT)

> **Plan gratuit :** viser **Oracle Cloud Always Free** (VM Ampere ARM, jusqu'à 4 cœurs / 24 Go RAM, gratuite à vie — largement assez pour Playwright) ou, à défaut, le free tier GCP (`e2-micro`, plus juste en RAM). Pas de coût d'hébergement. (Alternative payante si besoin plus tard : Hetzner CPX21 ~5 €/mo.)

- [ ] **Step 1: Créer une VM Always Free** (Oracle Cloud → Compute → Instance → shape `VM.Standard.A1.Flex`, 2-4 OCPU / 6-12 Go, image Ubuntu 22.04). Noter : la capacité ARM gratuite peut être indisponible par moments — réessayer ou choisir une autre région.
- [ ] **Step 2: Installer Docker + Compose** sur la VM (`curl -fsSL https://get.docker.com | sh`). Le repo contient déjà `setup_vps.sh` — l'adapter/exécuter.
- [ ] **Step 3: Déployer** : cloner le repo sur la VM, `docker compose up -d --build`. Vérifier `curl http://localhost:8501/_stcore/health`.
- [ ] **Step 4: NE PAS ouvrir le port 8501 sur Internet** (le tunnel Cloudflare s'en charge en Task 11). Laisser le pare-feu Oracle fermé sur 8501 ; seul `cloudflared` sort vers Cloudflare.

### Task 11: Cloudflare Tunnel + Cloudflare Access (SSO, groupe restreint)

- [ ] **Step 1: Domaine sur Cloudflare.** Avoir un domaine géré par Cloudflare (ex. `scraper.tondomaine.com`).
- [ ] **Step 2: Installer `cloudflared` sur le VPS** et créer un tunnel :
  ```bash
  cloudflared tunnel login
  cloudflared tunnel create linkedin-scraper
  cloudflared tunnel route dns linkedin-scraper scraper.tondomaine.com
  ```
- [ ] **Step 3: Config du tunnel** (`~/.cloudflared/config.yml`) pointant vers `http://localhost:8501`, puis lancer `cloudflared tunnel run` (en service systemd pour la persistance).
- [ ] **Step 4: Activer Cloudflare Access (Zero Trust).** Dashboard Zero Trust → Access → Applications → Add → Self-hosted → domaine `scraper.tondomaine.com`.
- [ ] **Step 5: Politique d'accès restreint.** Créer une policy « Allow » avec règle **Emails** = la liste exacte des ≤ 10 personnes autorisées (ou « Emails ending in @tondomaine.com »). Méthode de login : One-time PIN (email) ou Google/Microsoft.
- [ ] **Step 6: Vérifier la transmission de l'identité.** Dans Access → Settings, s'assurer que l'en-tête `Cf-Access-Authenticated-User-Email` est transmis (c'est le défaut). L'app le lit déjà (Task 7).
- [ ] **Step 7: Test de bout en bout.** Depuis un navigateur, ouvrir `https://scraper.tondomaine.com` → écran SSO Cloudflare → après login, l'app s'ouvre et `current_user_email()` renvoie l'email réel (vérifiable en affichant temporairement l'email dans la sidebar). Tester avec un email NON autorisé → accès refusé.

### Task 12: Attribution des proxies résidentiels (REPORTÉ — plan gratuit)

> **Reporté pour l'instant** (plan gratuit). Le code des Tasks 5/6/8 est déjà en place : activer un proxy plus tard ne demandera **aucun développement**, juste une saisie dans l'UI « Mon proxy ». En attendant, voir « Mitigations gratuites » ci-dessous.

- [ ] **Step 1: Choisir un fournisseur** de proxies résidentiels statiques/ISP (Webshare, IPRoyal, Smartproxy/Decodo…). Commander **1 IP dédiée par utilisateur**, géo-localisée au pays réel de chaque personne.
- [ ] **Step 2: Distribuer.** Pour chaque utilisateur, communiquer/saisir son `server/login/password` dans l'UI « Mon proxy » (Task 8). Chaque compte LinkedIn sort alors via une IP résidentielle stable et distincte.
- [ ] **Step 3: Valider.** Lancer un petit scraping par utilisateur et vérifier dans `scraper.log` l'absence de blocage/captcha.

**Mitigations gratuites en attendant les proxies :**
- Garder `MAX_INVITATIONS_PER_DAY` bas (ex. 10-15) et `MAX_PROFILES_PER_RUN` modéré dans `config.py`.
- Étaler les usages (éviter que les 10 comptes scrapent en même temps depuis l'IP de la VM).
- Surveiller `scraper.log` : au moindre captcha/restriction, stopper et activer les proxies.

---

## Notes de sécurité & exploitation

- **Risque LinkedIn** : même avec proxies, garder un volume d'invitations bas par compte (`MAX_INVITATIONS_PER_DAY` dans `config.py`). Sans proxy, le risque de restriction des comptes est élevé (plusieurs comptes / une IP).
- **Concurrence** : un seul Chromium tourne à la fois par processus. À ≤ 10 users occasionnels ça passe ; si plusieurs scrapings simultanés deviennent fréquents, prévoir une file globale ou plusieurs workers (hors périmètre de ce plan).
- **Secrets** : la clé Fernet de chaque utilisateur vit dans son `config/secret.key` sous le volume persistant. Sauvegarder le volume `scraper_data`.
- **Conformité** : l'automatisation d'invitations/scraping enfreint les CGU de LinkedIn ; chaque utilisateur agit sous sa propre responsabilité avec son compte.

---

## Self-Review

- **Couverture du spec** : SSO/groupe restreint → Task 11 ; accès en ligne sans install par Mac → Tasks 9-11 ; chacun son compte LinkedIn → Tasks 2-5,7 (isolation cookie/db/queue) ; proxies → Tasks 5,6,8,12. ✅
- **Placeholders** : aucun « TODO/à compléter » dans les étapes de code ; chaque étape de code contient le code réel. Les Tasks 10-12 sont des étapes ops (commandes réelles), volontairement sans test unitaire. ✅
- **Cohérence des types** : `proxy` au format Playwright `{server, username, password}` partout (Tasks 5→6→7→8) ; `config_dir` (Task 3), `queue_file` (Task 4), `db_file` (existant) cohérents avec `UserPaths` (Task 2). ✅
