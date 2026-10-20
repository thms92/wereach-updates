# -*- coding: utf-8 -*-
"""Visite guidée en bulles (driver.js), injectée dans la page par st.html.

Deux contraintes de Streamlit 1.58 dictent la forme :
- `st.html` passe par DOMPurify, qui supprime SANS ERREUR tout script dont
  le texte contient « < » suivi d'une lettre ou d'un chiffre. driver.js
  minifié en contient : il est donc embarqué en base64 et décodé dans la
  page. Le pilotage ci-dessous est écrit sans un seul « < ».
- Le service de fichiers statiques renvoie le JavaScript en text/plain,
  que le navigateur refuse d'exécuter : pas de `<script src>`.

Chaque clic de navigation relance le script Python et donc ce script :
`window.__wrTour` garde l'identifiant de la visite en cours pour ne pas la
recommencer. Le script ne clique que trois choses : un bouton du menu,
un onglet, et le bouton caché de fin.
"""

import base64
import json
from pathlib import Path

CLE_FIN = "tutoriel_fini"

_VENDOR = Path(__file__).resolve().parent / "vendor"


def _b64(nom: str) -> str:
    return base64.b64encode((_VENDOR / nom).read_bytes()).decode("ascii")


def _suffixe_menu(page: str) -> str:
    # « 📊 Dashboard » → classe st-key-nav_---Dashboard (cf. tests/conftest).
    return page.split(" ", 1)[1]


_PILOTAGE = r"""
(function () {
  var w = window, d = document;
  if (w.__wrTour && w.__wrTour.id === ID) { return; }
  if (w.__wrTour && w.__wrTour.drv) { try { w.__wrTour.drv.destroy(); } catch (e) {} }
  var etat = w.__wrTour = { id: ID, drv: null };
  if (!w.__wrDriverCharge) {
    var s = d.createElement("script"); s.textContent = JS64; d.head.appendChild(s);
    var st = d.createElement("style"); st.textContent = CSS64; d.head.appendChild(st);
    w.__wrDriverCharge = true;
  }
  var N = ETAPES.length;
  var pause = function (ms) { return new Promise(function (ok) { setTimeout(ok, ms); }); };
  function attendre(test, ms) {
    return new Promise(function (ok) {
      var debut = Date.now();
      (function boucle() {
        var r = test();
        if (r) { return ok(r); }
        if (Date.now() - debut > ms) { return ok(null); }
        setTimeout(boucle, 120);
      })();
    });
  }
  function visible(el) {
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.right > 0 && w.innerWidth > r.left;
  }
  function trouver(e) {
    if (!e.cible) { return null; }
    var selecteurs = e.cible.split(",");
    for (var sel of selecteurs) {
      for (var el of d.querySelectorAll(sel.trim())) {
        if (e.contient && el.textContent.indexOf(e.contient) === -1) { continue; }
        if (visible(el)) { return el; }
      }
    }
    return null;
  }
  function pageActive(suffixe) {
    return d.querySelector(".st-key-nav_---" + suffixe + ' button[kind="primary"]');
  }
  function finir() {
    if (etat.drv) { try { etat.drv.destroy(); } catch (e) {} etat.drv = null; }
    var fin = d.querySelector(".st-key-""" + CLE_FIN + r""" button");
    if (fin) { fin.click(); }
  }
  async function aller(i) {
    if (etat !== w.__wrTour) { return; }
    var e = ETAPES[i];
    if (e.page) {
      var suffixe = SUFFIXES[e.page];
      if (!pageActive(suffixe)) {
        var bouton = d.querySelector(".st-key-nav_---" + suffixe + " button");
        if (bouton) { bouton.click(); }
        await attendre(function () { return pageActive(suffixe); }, 6000);
        await pause(500);
      }
    }
    if (e.onglet) {
      var onglet = Array.from(d.querySelectorAll('[data-baseweb="tab"]'))
        .find(function (t) { return t.textContent.trim() === e.onglet; });
      if (onglet && onglet.getAttribute("aria-selected") !== "true") { onglet.click(); await pause(400); }
    }
    var el = e.cible ? await attendre(function () { return trouver(e); }, 4000) : null;
    if (etat !== w.__wrTour) { return; }
    montrer(i, el);
  }
  function montrer(i, el) {
    var e = ETAPES[i], derniere = i === N - 1;
    var boutons = i === 0 ? ["next", "close"] : ["previous", "next", "close"];
    var drv = w.driver.js.driver({
      animate: !w.matchMedia("(prefers-reduced-motion: reduce)").matches,
      overlayOpacity: 0.55, stagePadding: 6, stageRadius: 12,
      allowClose: true, popoverClass: "wr-bulle",
      // On montre, on ne fait pas : l'élément éclairé (« Lancer la veille »…)
      // ne reçoit pas les clics pendant la visite.
      disableActiveInteraction: true,
      // Échap, clic sur le voile ou croix : passent tous par ce crochet (pas
      // par onCloseClick). Nos propres destroy() ne le déclenchent pas.
      onDestroyStarted: finir,
      showProgress: true, progressText: "Étape " + (i + 1) + " sur " + N,
      showButtons: boutons,
      nextBtnText: derniere ? "Terminer" : "Suivant",
      // Une visite d'une seule bulle par étape : driver.js la croit toujours
      // dernière et affiche doneBtnText. Le libellé suit donc l'étape.
      prevBtnText: "Précédent", doneBtnText: derniere ? "Terminer" : "Suivant",
      onPopoverRender: function (p) {
        var passer = d.createElement("button");
        passer.type = "button"; passer.className = "wr-passer";
        passer.textContent = "Passer le tutoriel";
        passer.addEventListener("click", finir);
        p.footer.insertBefore(passer, p.footer.firstChild);
      },
      onNextClick: function () {
        drv.destroy(); etat.drv = null;
        if (derniere) { finir(); } else { aller(i + 1); }
      },
      onPrevClick: function () {
        // La flèche gauche du clavier l'appelle même sans bouton visible.
        if (i === 0) { return; }
        drv.destroy(); etat.drv = null; aller(i - 1);
      },
      // disableButtons: [] — seule dans sa visite, la bulle n'a jamais
      // d'étape précédente aux yeux de driver.js, qui griserait « Précédent ».
      steps: [{ element: el || undefined,
                popover: { title: e.titre, description: e.texte, disableButtons: [] } }]
    });
    etat.drv = drv;
    drv.drive();
  }
  attendre(function () { return w.driver && w.driver.js && w.driver.js.driver; }, 5000)
    .then(function (pret) { if (pret) { aller(0); } });
})();
"""


def script_visite(etapes: list, identifiant: str) -> str:
    """HTML à passer à `st.html(..., unsafe_allow_javascript=True)`."""
    suffixes = {e["page"]: _suffixe_menu(e["page"]) for e in etapes if e["page"]}
    # ensure_ascii + échappement de « < » : aucun chevron ne survit dans le texte.
    def js(valeur):
        return json.dumps(valeur, ensure_ascii=True).replace("<", "\\u003c")
    entete = (
        f"var ID = {js(identifiant)};\n"
        f'var JS64 = atob("{_b64("driver.js.iife.js")}");\n'
        f'var CSS64 = atob("{_b64("driver.css")}");\n'
        f"var SUFFIXES = {js(suffixes)};\n"
        f"var ETAPES = {js(etapes)};\n"
    )
    return f"<script>{entete}{_PILOTAGE}</script>"
