// Gedeelde helpers voor de CBR Trading Journal.

const VALUES = { yes: "yes", maybe: "maybe", no: "no" };
const SYMBOLS = { yes: "✓", maybe: "?", no: "✗" };

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

function shotUrl(pad) {
  // pad = "screenshots/<datum>/<file>" -> "/screenshots/<datum>/<file>"
  return "/" + String(pad).replace(/^\/+/, "");
}

function fmtEur(n) {
  if (n === null || n === undefined) return "–";
  const s = (n >= 0 ? "+" : "") + n.toFixed(2).replace(".", ",");
  return "€ " + s;
}

function eurClass(n) {
  if (n === null || n === undefined || n === 0) return "";
  return n > 0 ? "pos" : "neg";
}

function todayISO() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

function qs(name) {
  return new URLSearchParams(location.search).get(name);
}

function toast(msg, isErr) {
  let t = document.getElementById("toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "toast";
    t.className = "toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  setTimeout(() => { t.className = "toast" + (isErr ? " err" : ""); }, 2600);
}

// Grade-logica ook client-side, zodat de grade LIVE meeverandert.
// (Server blijft autoritatief bij opslaan.)
const CRITICAL = ["crit1_conditie", "crit2_sweep", "crit3_shift"];
const ALL_CRITS = ["crit1_conditie", "crit2_sweep", "crit3_shift", "crit4_entry", "crit5_tp"];

function computeGrade(vals) {
  const crit = CRITICAL.map((k) => vals[k]);
  if (crit.some((v) => v === "no" || v === "maybe")) return "C";
  if (ALL_CRITS.every((k) => vals[k] === "yes")) return "A";
  return "B";
}

const GRADE_DESC = {
  A: "Perfecte setup — alle vijf criteria voldaan.",
  B: "Valide setup — drie kritische criteria voldaan.",
  C: "Dit was geen trade — een kritisch criterium ontbreekt.",
};

/* =====================================================================
   Commandopalet (fase 14.1) + sneltoetsen op elk scherm (fase 14.4).
   Ctrl+K opent het. Typ een pagina, een datum ("6 sep", "gisteren") of
   een woord uit een les, notitie of foutcode — alles zit in hetzelfde veld.
   ===================================================================== */

const CMD_ACTIES = [
  { t: "Home — saldo, grafieken, alles", h: "d", u: () => "/", i: "▤" },
  { t: "Nog te loggen — trades uit MetaTrader", h: "o", u: () => "/#te-loggen", i: "✓" },
  { t: "Saldo & stortingen", h: "", u: () => "/#saldo", i: "€" },
  { t: "Foto-logboek (telefoon)", h: "", u: () => "/logboek/foto", i: "📷" },
  { t: "Nieuwe trade", h: "n", u: () => "/nieuw?datum=" + cmdDatum(), i: "+" },
  { t: "Trading log", h: "l", u: () => "/log", i: "📒" },
  { t: "Nieuwe trade — uitgebreid formulier", h: "", u: () => "/trade?datum=" + cmdDatum(), i: "⋯" },
  { t: "Trade plannen", h: "p", u: () => "/trade?plan=1&datum=" + cmdDatum(), i: "◎" },
  { t: "Snel loggen (telefoon)", h: "", u: () => "/snel?datum=" + cmdDatum(), i: "📱" },
  { t: "Kalender", h: "k", u: () => "/kalender", i: "🗓" },
  { t: "Dashboard — Vandaag", h: "", u: () => "/dashboard?laag=vandaag", i: "📊" },
  { t: "Dashboard — Edge", h: "", u: () => "/dashboard?laag=edge", i: "◈" },
  { t: "Dashboard — Discipline", h: "", u: () => "/dashboard?laag=discipline", i: "🛡" },
  { t: "Dashboard — Patronen", h: "", u: () => "/dashboard?laag=patronen", i: "◍" },
  { t: "Foutenanalyse", h: "f", u: () => "/fouten", i: "⚠" },
  { t: "Weekreview", h: "w", u: () => "/week", i: "🗓" },
  { t: "PDF-rapport downloaden", h: "", u: () => "/export", i: "📄" },
  { t: "Regels en changelog", h: "", u: () => "/regels", i: "📋" },
  { t: "Dataset exporteren (CSV)", h: "", u: () => "/export", i: "⇩" },
  { t: "Setup-bibliotheek", h: "b", u: () => "/setups", i: "★" },
  { t: "Signalen & jouw oordeel", h: "i", u: () => "/signalen", i: "📡" },
];

const MAANDEN_NL = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];

function cmdDatum() {
  return qs("datum") || todayISO();
}

// "6 sep", "06-09", "2026-09-06", "vandaag", "gisteren" -> ISO-datum of null
function leesDatum(tekst) {
  const t = tekst.trim().toLowerCase();
  if (!t) return null;
  const nu = new Date();
  if (t === "vandaag") return todayISO();
  if (t === "gisteren") { nu.setDate(nu.getDate() - 1); return nu.toISOString().slice(0, 10); }
  if (/^\d{4}-\d{2}-\d{2}$/.test(t)) return t;
  let m = t.match(/^(\d{1,2})[-/](\d{1,2})(?:[-/](\d{4}))?$/);
  if (m) {
    const j = m[3] || nu.getFullYear();
    return `${j}-${String(m[2]).padStart(2, "0")}-${String(m[1]).padStart(2, "0")}`;
  }
  m = t.match(/^(\d{1,2})\s+([a-z]{3,})$/);
  if (m) {
    const i = MAANDEN_NL.findIndex((x) => m[2].startsWith(x));
    if (i >= 0) return `${nu.getFullYear()}-${String(i + 1).padStart(2, "0")}-${String(m[1]).padStart(2, "0")}`;
  }
  return null;
}

let cmdOpen = false, cmdKeuze = 0, cmdRijen = [], cmdTimer = null;

function bouwPalet() {
  if (document.getElementById("cmdk")) return;
  const el = document.createElement("div");
  el.id = "cmdk";
  el.className = "cmdk";
  el.innerHTML = `
    <div class="cmdk-doos" role="dialog" aria-label="Commandopalet">
      <input id="cmdkVeld" type="text" autocomplete="off" spellcheck="false"
             placeholder="Waar wil je heen? Of typ een datum, een woord uit een les…" />
      <div class="cmdk-lijst" id="cmdkLijst"></div>
      <div class="cmdk-voet">
        <span><kbd>↑</kbd><kbd>↓</kbd> kiezen</span>
        <span><kbd>Enter</kbd> openen</span>
        <span><kbd>Esc</kbd> sluiten</span>
      </div>
    </div>`;
  document.body.appendChild(el);
  el.addEventListener("click", (e) => { if (e.target === el) sluitPalet(); });
  const veld = document.getElementById("cmdkVeld");
  veld.addEventListener("input", () => vulPalet(veld.value));
  veld.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { cmdKeuze = Math.min(cmdKeuze + 1, cmdRijen.length - 1); verfPalet(); e.preventDefault(); }
    if (e.key === "ArrowUp") { cmdKeuze = Math.max(cmdKeuze - 1, 0); verfPalet(); e.preventDefault(); }
    if (e.key === "Enter") { kiesRij(cmdKeuze); e.preventDefault(); }
    if (e.key === "Escape") { sluitPalet(); e.preventDefault(); }
  });
}

function openPalet() {
  bouwPalet();
  cmdOpen = true;
  document.getElementById("cmdk").classList.add("aan");
  const veld = document.getElementById("cmdkVeld");
  veld.value = ""; veld.focus();
  vulPalet("");
}

function sluitPalet() {
  cmdOpen = false;
  const el = document.getElementById("cmdk");
  if (el) el.classList.remove("aan");
}

function vulPalet(tekst) {
  const q = tekst.trim().toLowerCase();
  cmdKeuze = 0;
  cmdRijen = [];

  const d = leesDatum(tekst);
  if (d) {
    cmdRijen.push({ i: "▤", t: "Ga naar " + d, s: "dag", url: "/?datum=" + d });
    cmdRijen.push({ i: "+", t: "Nieuwe trade op " + d, s: "dag", url: "/trade?datum=" + d });
  }
  CMD_ACTIES.filter((a) => !q || a.t.toLowerCase().includes(q))
    .forEach((a) => cmdRijen.push({ i: a.i, t: a.t, s: a.h ? "sneltoets " + a.h.toUpperCase() : "", url: a.u() }));
  verfPalet();

  clearTimeout(cmdTimer);
  if (q.length >= 2 && !d) {
    cmdTimer = setTimeout(async () => {
      try {
        const r = await api("/api/zoek?q=" + encodeURIComponent(q));
        if (!cmdOpen) return;
        r.resultaten.forEach((x) => cmdRijen.push({
          i: { trade: "▤", notitie: "📓", review: "✎", regel: "§" }[x.soort] || "·",
          t: x.titel, s: x.tekst || x.extra, url: x.url, gevonden: true,
        }));
        verfPalet();
      } catch (e) { /* zoeken is bijzaak */ }
    }, 180);
  }
}

function verfPalet() {
  const lijst = document.getElementById("cmdkLijst");
  if (!lijst) return;
  if (!cmdRijen.length) {
    lijst.innerHTML = `<div class="cmdk-leeg">Niets gevonden.</div>`;
    return;
  }
  lijst.innerHTML = cmdRijen.map((r, i) => `
    <div class="cmdk-rij ${i === cmdKeuze ? "op" : ""}${r.gevonden ? " gevonden" : ""}" data-i="${i}">
      <span class="ci">${r.i}</span>
      <span class="ct">${r.t}</span>
      ${r.s ? `<span class="cs">${r.s}</span>` : ""}
    </div>`).join("");
  lijst.querySelectorAll(".cmdk-rij").forEach((el) => {
    el.addEventListener("click", () => kiesRij(parseInt(el.dataset.i, 10)));
  });
  const op = lijst.querySelector(".cmdk-rij.op");
  if (op) op.scrollIntoView({ block: "nearest" });
}

function kiesRij(i) {
  const r = cmdRijen[i];
  if (!r) return;
  sluitPalet();
  location.href = r.url;
}

// Sneltoetsen op elk scherm. In een invoerveld doet alleen Ctrl+K iets.
document.addEventListener("keydown", (e) => {
  const tag = (e.target.tagName || "").toLowerCase();
  const inVeld = tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable;

  if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
    e.preventDefault();
    cmdOpen ? sluitPalet() : openPalet();
    return;
  }
  // Schermen met eigen lettertoetsen (het trade-formulier gebruikt J/T/N en 1–5)
  // houden hun eigen afhandeling; alleen Ctrl+K werkt daar globaal.
  if (cmdOpen || inVeld || window.EIGEN_TOETSEN || e.ctrlKey || e.altKey || e.metaKey) return;

  const naar = { d: "/", k: "/kalender", f: "/fouten", w: "/week",
                 b: "/setups", l: "/log", s: "/#prestaties", o: "/#te-loggen", i: "/signalen" };
  const k = e.key.toLowerCase();
  if (k === "n") { location.href = "/nieuw?datum=" + cmdDatum(); e.preventDefault(); }
  else if (k === "p") { location.href = "/trade?plan=1&datum=" + cmdDatum(); e.preventDefault(); }
  else if (naar[k]) { location.href = naar[k]; e.preventDefault(); }
  else if (k === "?") { openPalet(); e.preventDefault(); }
});

/* =====================================================================
   Spraaknotitie (fase 14.3). Praten is op een telefoon drie keer sneller
   dan typen, en dat is precies het moment waarop je anders niets opschrijft.
   Alles gebeurt in de browser zelf via de Web Speech API — geen server.
   ===================================================================== */

function spraakBeschikbaar() {
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

function maakSpraakKnop(veldId, label) {
  const veld = document.getElementById(veldId);
  if (!veld || !spraakBeschikbaar()) return null;

  const knop = document.createElement("button");
  knop.type = "button";
  knop.className = "spraak-knop";
  knop.title = label || "Inspreken in plaats van typen";
  knop.innerHTML = `<span class="sp-ic">🎤</span><span class="sp-t">Inspreken</span>`;

  const Herkenner = window.SpeechRecognition || window.webkitSpeechRecognition;
  let luistert = false, herkenner = null;

  knop.addEventListener("click", () => {
    if (luistert && herkenner) { herkenner.stop(); return; }
    herkenner = new Herkenner();
    herkenner.lang = "nl-NL";
    herkenner.interimResults = true;
    herkenner.continuous = false;

    const begin = veld.value ? veld.value.trim() + " " : "";
    herkenner.onstart = () => {
      luistert = true;
      knop.classList.add("luistert");
      knop.querySelector(".sp-t").textContent = "Luisteren… (klik om te stoppen)";
    };
    herkenner.onresult = (e) => {
      let tekst = "";
      for (let i = 0; i < e.results.length; i++) tekst += e.results[i][0].transcript;
      veld.value = begin + tekst.trim();
      veld.dispatchEvent(new Event("input", { bubbles: true }));
    };
    herkenner.onerror = (e) => {
      toast(e.error === "not-allowed"
        ? "Microfoon geweigerd — sta 'm toe in je browser"
        : "Inspreken lukt niet: " + e.error, true);
    };
    herkenner.onend = () => {
      luistert = false;
      knop.classList.remove("luistert");
      knop.querySelector(".sp-t").textContent = "Inspreken";
    };
    try { herkenner.start(); } catch (e) { toast("Inspreken lukt niet", true); }
  });

  veld.insertAdjacentElement("afterend", knop);
  return knop;
}

/* Versiestempel in de topbar: zo zie je meteen welke build je draait. */
(function () {
  function toon() {
    const bar = document.querySelector(".topbar") || document.querySelector(".snel-kop");
    const v = document.body.dataset.versie;
    if (!bar || !v || document.getElementById("versieChip")) return;
    const el = document.createElement("span");
    el.id = "versieChip";
    el.className = "versie-chip";
    el.title = "Versie van de journal. Klopt dit niet met wat je verwacht?\nDan is het uitpakken niet gelukt.";
    el.textContent = "v" + v + (document.body.dataset.build ? " · " + document.body.dataset.build : "");
    const h1 = bar.querySelector("h1");
    if (h1) h1.insertAdjacentElement("afterend", el); else bar.appendChild(el);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", toon);
  else toon();
})();

/* =====================================================================
   Eén vaste hoofdnavigatie op elk scherm.

   Reden: alles was per pagina een eigen rijtje links, waardoor je via-via
   moest navigeren -- van de kalender kwam je niet rechtstreeks bij het
   rapport. Dit menu staat op élk scherm, blijft bovenin plakken bij het
   scrollen, en groepeert de elf schermen in vier dropdowns.

   Wordt gevuld in <div id="hoofdnav"></div>, zodat er maar één plek is waar
   dit onderhouden wordt.
   ===================================================================== */

const NAV = [
  {
    naam: "Journal", icoon: "▤",
    items: [
      { t: "Home — alles in één", u: () => "/", h: "d", i: "▤" },
      { t: "Nog te loggen", u: () => "/#te-loggen", h: "o", i: "✓" },
      { t: "Trading log", u: () => "/log", h: "l", i: "📒" },
      { t: "Kalender", u: () => "/kalender", h: "k", i: "🗓" },
      { t: "Weekrapport + PDF", u: () => "/week", h: "w", i: "📈" },
    ],
  },
  {
    naam: "Toevoegen", icoon: "＋",
    items: [
      { t: "Nieuwe trade (handmatig)", u: () => "/nieuw?datum=" + navDatum(), h: "n", i: "＋" },
      { t: "Uitgebreid formulier", u: () => "/trade?datum=" + navDatum(), i: "⋯" },
      { t: "Foto-logboek (telefoon)", u: () => "/logboek/foto", i: "📷" },
    ],
  },
  {
    naam: "Leren", icoon: "◎",
    items: [
      { t: "Regels & setup-model", u: () => "/regels", i: "📋" },
      { t: "Foutenanalyse", u: () => "/fouten", h: "f", i: "⚠" },
      { t: "Setup-bibliotheek", u: () => "/setups", h: "b", i: "★" },
      { t: "Signalen & jouw oordeel", u: () => "/signalen", h: "i", i: "📡" },
      { t: "Setup Trainer", u: () => "/trainer", h: "t", i: "🎯" },
    ],
  },
  {
    naam: "Meer", icoon: "⋯",
    items: [
      { t: "PDF-rapport & dataset", u: () => "/export", i: "⇩" },
      { t: "Dashboard — Edge", u: () => "/dashboard?laag=edge", i: "◈" },
      { t: "Dashboard — Patronen", u: () => "/dashboard?laag=patronen", i: "◍" },
      { t: "Type 3 shift — guide (oud)", u: () => "/guide", h: "g", i: "📐" },
      { t: "Fase 1 — archief", u: () => "/archief", i: "🗄" },
    ],
  },
];

function navDatum() {
  const q = new URLSearchParams(location.search).get("datum");
  if (q) return q;
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function navActief(url) {
  const pad = location.pathname;
  const doel = url.split("?")[0];
  if (doel === "/") return pad === "/";
  return pad === doel;
}

function bouwNav() {
  const gastheer = document.getElementById("hoofdnav");
  if (!gastheer) return;

  const groepen = NAV.map((g, gi) => {
    const items = g.items.map((it) => {
      const url = it.u();
      const aan = navActief(url) ? " aan" : "";
      const hint = it.h ? `<kbd>${it.h}</kbd>` : "";
      const nieuw = it.nieuw ? `<span class="nav-nieuw">nieuw</span>` : "";
      return `<a href="${url}" class="nav-item${aan}">
        <span class="ni">${it.i || ""}</span><span class="nt">${it.t}</span>${nieuw}${hint}</a>`;
    }).join("");
    const groepAan = g.items.some((it) => navActief(it.u())) ? " aan" : "";
    return `<div class="nav-groep" data-g="${gi}">
      <button type="button" class="nav-knop${groepAan}" aria-expanded="false">
        <span class="ni">${g.icoon}</span>${g.naam}<span class="pijl">▾</span></button>
      <div class="nav-menu">${items}</div>
    </div>`;
  }).join("");

  gastheer.innerHTML = `
    <div class="nav-binnen">
      <a class="nav-merk" href="/"><span class="brand-dot">●</span> CBR Journal</a>
      <nav class="nav-groepen">${groepen}</nav>
      <div class="nav-rechts">
        <a class="nav-mt5" id="navMt5" href="/#te-loggen" title="Koppeling met MetaTrader 5">
          <span class="stip"></span><span class="tekst">MT5</span><span class="tel" hidden></span></a>
        <button type="button" class="nav-palet" id="navPalet" title="Commandopalet (Ctrl+K)">
          <span class="pk-icoon">⌘</span><span class="pk-tekst">zoek of spring</span><kbd>Ctrl K</kbd></button>
        <a class="btn btn-primary nav-nieuwe" href="/nieuw?datum=${navDatum()}">＋ Trade</a>
      </div>
      <button type="button" class="nav-hamburger" id="navHamburger" aria-label="Menu">☰</button>
    </div>`;

  // Openen op klik; hover werkt alleen op een muis, dus klik is de basis.
  let open = null;
  const sluit = () => {
    gastheer.querySelectorAll(".nav-groep").forEach((el) => el.classList.remove("open"));
    gastheer.querySelectorAll(".nav-knop").forEach((b) => b.setAttribute("aria-expanded", "false"));
    open = null;
  };
  gastheer.querySelectorAll(".nav-groep").forEach((groep) => {
    const knop = groep.querySelector(".nav-knop");
    knop.addEventListener("click", (e) => {
      e.stopPropagation();
      const was = groep.classList.contains("open");
      sluit();
      if (!was) {
        groep.classList.add("open");
        knop.setAttribute("aria-expanded", "true");
        open = groep;
      }
    });
    // Al open? Dan volgt de muis, zoals in een echte menubalk.
    groep.addEventListener("mouseenter", () => {
      if (open && open !== groep) { sluit(); groep.classList.add("open"); open = groep; }
    });
  });
  document.addEventListener("click", sluit);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") sluit(); });

  const palet = document.getElementById("navPalet");
  if (palet) palet.addEventListener("click", (e) => {
    e.stopPropagation();
    if (typeof openPalet === "function") openPalet();
  });

  const burger = document.getElementById("navHamburger");
  if (burger) burger.addEventListener("click", (e) => {
    e.stopPropagation();
    gastheer.classList.toggle("uitgeklapt");
  });
}

document.addEventListener("DOMContentLoaded", bouwNav);

/* =====================================================================
   Het muntje (ronde 3, punt 9).

   Vuurt alleen bij een WINST die ook een grade A is. Dat is bewust: belonen
   op winst alleen leert je van uitkomsten houden, en dat is precies de
   gewoonte die dit hele journal probeert af te leren. Een A die verliest
   krijgt geen muntje, en een C die wint al helemaal niet.

   Geen geluidsbestand: de pling wordt in de browser zelf gemaakt.
   ===================================================================== */

function _rustigeAnimaties() {
  try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
  catch (e) { return false; }
}

function playPling() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    // Twee tonen, kort na elkaar: een muntje dat in een spaarpot valt.
    [[988, 0], [1319, 0.09]].forEach(([hz, t]) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(hz, ctx.currentTime + t);
      gain.gain.setValueAtTime(0.0001, ctx.currentTime + t);
      gain.gain.exponentialRampToValueAtTime(0.16, ctx.currentTime + t + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + t + 0.42);
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start(ctx.currentTime + t);
      osc.stop(ctx.currentTime + t + 0.45);
    });
    setTimeout(() => { try { ctx.close(); } catch (e) {} }, 900);
  } catch (e) { /* geluid is nooit belangrijk genoeg om iets te breken */ }
}

function spawnCoin() {
  return new Promise((klaar) => {
    if (_rustigeAnimaties()) { klaar(); return; }
    const munt = document.createElement("div");
    munt.className = "munt";
    munt.innerHTML = `<span class="munt-vlak">★</span>`;
    document.body.appendChild(munt);
    // opruimen gebeurt hoe dan ook, ook als de animatie niet afvuurt
    const weg = () => { munt.remove(); klaar(); };
    munt.addEventListener("animationend", weg, { once: true });
    setTimeout(weg, 2400);
  });
}

/**
 * Aanroepen direct na het succesvol opslaan van een trade.
 * Vuurt bij result > 0 && grade === 'A'  ->  playPling() + spawnCoin().
 * Geeft een promise terug zodat je pas na het muntje doornavigeert.
 */
function maybeCelebrate({ result, grade }) {
  const winst = Number(result) > 0;
  if (!(winst && grade === "A")) return Promise.resolve(false);
  playPling();
  return spawnCoin().then(() => true);
}


/* =====================================================================
   MT5-lampje rechtsboven (22 sep 2026). Groen = de journal leest je trades
   uit MetaTrader; het getal = trades die nog op je checks/criteria wachten.
   ===================================================================== */
async function mt5Lampje() {
  const el = document.getElementById("navMt5");
  if (!el) return;
  try {
    const s = await (await fetch("/api/mt5/status")).json();
    el.classList.toggle("aan", !!s.verbonden);
    el.classList.toggle("fout", !s.verbonden && s.aan !== false);
    const tijd = s.laatste_ronde ? " · laatst gekeken " + s.laatste_ronde.slice(11, 16) : "";
    el.title = (s.verbonden ? "MT5 verbonden" + tijd : "MT5: " + (s.melding || "niet verbonden"));
    const tel = el.querySelector(".tel");
    if (s.te_beoordelen > 0) { tel.hidden = false; tel.textContent = s.te_beoordelen; }
    else { tel.hidden = true; }
  } catch (e) { /* journal zonder koppeling: lampje blijft grijs */ }
}
document.addEventListener("DOMContentLoaded", () => { mt5Lampje(); setInterval(mt5Lampje, 60000); });
