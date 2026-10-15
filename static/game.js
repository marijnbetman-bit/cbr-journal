/* =====================================================================
   CBR Journal · GAME MODE (journal v2, 15 okt 2026)
   Dezelfde informatie als het klassieke overzicht, in de stijl van CBR Station, met:
     - filters (periode, richting, sessie, grade, emotie, regels, exit, TP-type, weekdag, uur): alles hieronder rekent mee
     - saldoverloop per trade / dag / week / maand, in € / R / %
     - ONTLEED: groeperen op wat je wilt (uur, emotie, grade, TP-type, trade-beheer, wat de bots deden, ...)
     - pixelscène met jou aan je bureau en de teamrace tegen de bots, badges, XP en levels
     - replay van elke trade op de candles, met de SL/TP-verschuivingen uit MT5 en wat de bots met die setup deden
   Alleen lezen (GET). Loggen blijft in het klassieke scherm (/#te-loggen).
   ===================================================================== */
"use strict";
const K = { hi: "#3dff8a", mid: "#2fb866", dim: "#1f6b3a", line: "#124a26", ink: "#d8ffe6", muted: "#6fae86", amber: "#ffb454", gold: "#ffd36b",
            cyan: "#7fe3ff", red: "#ff5a4f", rood: "#ff8f8a", bg: "#02120a" };
Chart.defaults.font.family = "VT323, monospace"; Chart.defaults.font.size = 15; Chart.defaults.color = K.muted;
Chart.defaults.borderColor = "rgba(18,74,38,.6)";
Chart.defaults.animation = { duration: 900, easing: "easeOutQuart" };

let LOGDATA = {}, ALLE = [], KAS = [], START = 0, BOTS = {}, TEAMS = null, OPEN = [], MT5 = null, SALDO = null, MAXDAG = 2, VENSTER = [];
const F = { periode: "alles", richting: [], sessie: [], grade: [], emotie: [], regels: [], exit: [], tp_type: [], weekdag: [], uur: [], extra: null };
const W = { per: "trade", eenheid: "eur", groep: "uur", metriek: "r_som" };
const charts = {};
const nl = (x, d = 2) => x == null || isNaN(x) ? "-" : Number(x).toFixed(d).replace(".", ",");
const plusR = (x) => x == null ? "-" : (x > 0 ? "+" : "") + nl(x) + "R";
const eur = (x) => x == null ? "-" : (x >= 0 ? "+€" : "-€") + nl(Math.abs(x));
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const kort = (d) => { const [, m, dd] = d.split("-"); return `${+dd}/${+m}`; };
const WD = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"];
const vandaagISO = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
function isoWeek(d) { const t = new Date(d + "T12:00"); const dag = (t.getDay() + 6) % 7; t.setDate(t.getDate() - dag + 3);
  const j = new Date(t.getFullYear(), 0, 4); return t.getFullYear() + "-W" + String(1 + Math.round(((t - j) / 864e5 - 3 + ((j.getDay() + 6) % 7)) / 7)).padStart(2, "0"); }
function maak(id, cfg) { if (charts[id]) charts[id].destroy(); const el = document.getElementById(id); if (el) charts[id] = new Chart(el, cfg); return charts[id]; }

/* ------------------------------------------------------------------ laden */
async function haal(pad) { const r = await fetch(pad, { cache: "no-store" }); return r.json(); }
async function boot() {
  const [t, mt5, beo, sal] = await Promise.all([haal("/api/game/trades"), haal("/api/mt5/status").catch(() => null),
    haal("/api/beoordelen").catch(() => ({})), haal("/api/saldo").catch(() => null)]);
  ALLE = t.trades || []; KAS = t.kasstromen || []; START = t.startkapitaal || 0; MT5 = mt5; OPEN = (beo && beo.open) || []; SALDO = sal; LOGDATA = beo || {};
  MAXDAG = +t.max_trades_dag || 2; VENSTER = t.venster || [];
  const nav = document.getElementById("hoofdnav"); if (nav) document.documentElement.style.setProperty("--g-nav-h", nav.offsetHeight + "px");
  const van = ALLE.length ? ALLE[0].datum : vandaagISO();
  haal("/api/game/station/teams").then((d) => { if (!d.error) TEAMS = d; tekenScene(); tekenRace(); }).catch(() => {});
  haal(`/api/game/station/vergelijk?van=${van}&tot=${vandaagISO()}`).then((d) => {
    BOTS = (d && d.setups) || {}; document.getElementById("g-bots-status").textContent = d.error ? "station niet bereikbaar" : "uit CBR Station (v3_demo_orders)";
    tekenAlles(); }).catch(() => {});
  bouwFilters(); bouwToggles(); tekenAlles(); tekenTeLoggen(); scenelus();
  if (typeof extraBoot === "function") extraBoot();                                    // game2.js: simulaties, gemist, nieuws, cockpit
  document.querySelectorAll(".g-paneel, .g-kpis").forEach((el, i) => { el.style.animationDelay = (i * 70) + "ms"; el.classList.add("g-boot"); });
  document.getElementById("g-voet").textContent = `Game mode · ${ALLE.length} trades uit MetaTrader · klassiek overzicht via de knop KLASSIEK bovenin`;
}

/* ------------------------------------------------------------------ filters */
function waarden(sleutel) { return [...new Set(ALLE.map((t) => t[sleutel]).filter((v) => v != null && v !== ""))].sort(); }
const GROEPEN = [
  ["periode", "PERIODE", () => [["7", "7 DAGEN"], ["30", "30 DAGEN"], ["90", "90 DAGEN"], ["alles", "ALLES"]], "enkel"],
  ["richting", "RICHTING", () => [["long", "▲ LONG"], ["short", "▼ SHORT"]]],
  ["sessie", "SESSIE", () => waarden("sessie").map((v) => [v, v.toUpperCase()])],
  ["grade", "GRADE", () => waarden("grade").map((v) => [v, v])],
  ["emotie", "EMOTIE", () => waarden("emotie").filter((v) => v !== "-").map((v) => [v, v.toUpperCase()])],
  ["regels", "REGELS", () => [["1", "GEVOLGD"], ["0", "GEBROKEN"]]],
  ["exit", "EXIT", () => waarden("exit").map((v) => [v, v.toUpperCase()])],
  ["tp_type", "TP-TYPE", () => waarden("tp_type").filter((v) => v !== "-").map((v) => [v, v.toUpperCase()])],
  ["weekdag", "WEEKDAG", () => WD.slice(0, 5).map((v) => [v, v.slice(0, 2).toUpperCase()])],
];
function bouwFilters() {
  const el = document.getElementById("g-filters");
  el.innerHTML = GROEPEN.map(([k, naam, opties, soort]) => {
    const o = opties(); if (!o.length) return "";
    return `<div class="g-frij"><span class="g-lbl">${naam}</span>${o.map(([v, l]) =>
      `<button class="g-chip" data-f="${k}" data-v="${esc(v)}" data-soort="${soort || "multi"}">${esc(l)}</button>`).join("")}
      ${k === "periode" ? `<span class="g-teller" id="g-teller"></span>` : ""}</div>`;
  }).join("") + `<div class="g-frij"><span class="g-lbl">UUR</span><span id="g-uurchips"></span>
     <button class="g-chip" data-reset="1" style="margin-left:auto">[ RESET FILTERS ]</button></div><div class="g-frij" id="g-extra"></div>`;
  document.getElementById("g-uurchips").innerHTML = [...new Set(ALLE.map((t) => t.uur).filter((u) => u != null))].sort((a, b) => a - b)
    .map((u) => `<button class="g-chip" data-f="uur" data-v="${u}">${String(u).padStart(2, "0")}</button>`).join("");
  el.addEventListener("click", (ev) => {
    const b = ev.target.closest("button"); if (!b) return;
    if (b.dataset.reset) { Object.keys(F).forEach((k) => F[k] = Array.isArray(F[k]) ? [] : null); F.periode = "alles"; }
    else if (b.dataset.extra) F.extra = null;
    else if (b.dataset.soort === "enkel") F[b.dataset.f] = b.dataset.v;
    else { const k = b.dataset.f, v = b.dataset.v, i = F[k].indexOf(v); i >= 0 ? F[k].splice(i, 1) : F[k].push(v); }
    tekenAlles();
  });
}
function filterChips() {
  document.querySelectorAll("#g-filters .g-chip[data-f]").forEach((b) => {
    const k = b.dataset.f, v = b.dataset.v;
    b.classList.toggle("aan", k === "periode" ? F.periode === v : F[k].includes(v));
  });
  document.getElementById("g-extra").innerHTML = F.extra ? `<span class="g-lbl">EXTRA</span><button class="g-chip aan" data-extra="1">${esc(F.extra.label)} ✕</button>` : "";
}
function gefilterd() {
  const grens = F.periode === "alles" ? null : (() => { const d = new Date(); d.setDate(d.getDate() - +F.periode); return d.toISOString().slice(0, 10); })();
  return ALLE.filter((t) => (!grens || t.datum >= grens)
    && (!F.richting.length || F.richting.includes(t.richting)) && (!F.sessie.length || F.sessie.includes(t.sessie))
    && (!F.grade.length || F.grade.includes(t.grade)) && (!F.emotie.length || F.emotie.includes(t.emotie))
    && (!F.regels.length || F.regels.includes(String(t.schoon))) && (!F.exit.length || F.exit.includes(t.exit))
    && (!F.tp_type.length || F.tp_type.includes(t.tp_type)) && (!F.weekdag.length || F.weekdag.includes(t.weekdag))
    && (!F.uur.length || F.uur.includes(String(t.uur))) && (!F.extra || F.extra.test(t)));
}

/* ------------------------------------------------------------------ alles tekenen */
let vorigN = null;
function tekenAlles() {
  filterChips();
  const T = gefilterd();
  const tel = document.getElementById("g-teller");
  if (tel) { tel.textContent = `${T.length} VAN ${ALLE.length} TRADES`; if (vorigN !== T.length) { tel.classList.remove("wiebel"); void tel.offsetWidth; tel.classList.add("wiebel"); } vorigN = T.length; }
  tekenHud(); tekenKpi(T); tekenSaldo(T); tekenOntleed(T); tekenHeat(T); tekenMfe(T); tekenLiggen(T); tekenBeheer(T); tekenBots(T);
  tekenBadges(); tekenKal(); tekenTrades(T); tekenScene();
  for (const f of NA_TEKENEN) { try { f(T); } catch (e) { console.error(e); } }      // game2.js: voorstellen 1-10
}
const NA_TEKENEN = [];                                                                   // game2.js zet hier zijn panelen in

/* ------------------------------------------------------------------ HUD + XP */
function xp() {
  let p = 0;
  for (const t of ALLE) { if (t.beoordeeld === 1) p += 10; if (t.schoon === 1) p += 10; if (t.proces) p += Math.round(t.proces / 10); if (t.r > 0) p += Math.min(30, Math.round(t.r * 5)); }
  p += badges().filter((b) => b.aan).length * 25;
  const lvl = Math.floor(Math.sqrt(p / 40)) + 1, vanaf = 40 * (lvl - 1) ** 2, tot = 40 * lvl ** 2;
  return { p, lvl, pct: Math.round(100 * (p - vanaf) / (tot - vanaf)) };
}
function tekenHud() {
  const vd = ALLE.filter((t) => t.datum === vandaagISO()), wk = ALLE.filter((t) => isoWeek(t.datum) === isoWeek(vandaagISO()));
  const som = (a, k) => a.reduce((s, t) => s + (t[k] || 0), 0), x = xp(), rk = reeks();
  const saldo = MT5 && MT5.verbonden && MT5.balans != null ? MT5.balans : SALDO ? SALDO.saldo : null;
  document.getElementById("g-hud").innerHTML =
    `<span class="vak">SALDO <b>€${nl(saldo)}</b>${MT5 && MT5.verbonden ? ' <b style="color:#3dff8a">●</b>' : ""}</span>` +
    `<span class="vak">VANDAAG <b class="${som(vd, "r") >= 0 ? "g-pos" : "g-neg"}">${plusR(som(vd, "r"))}</b> · ${eur(som(vd, "netto"))} · ` +
      `<b class="${vd.length > MAXDAG ? "g-neg" : vd.length === MAXDAG ? "g-gold" : ""}" title="trades vandaag / je dagmaximum">${vd.length}/${MAXDAG} TR${vd.length > MAXDAG ? " !" : ""}</b></span>` +
    `<span class="vak">WEEK <b class="${som(wk, "r") >= 0 ? "g-pos" : "g-neg"}">${plusR(som(wk, "r"))}</b></span>` +
    `<span class="vak">REEKS <b>${rk.soort === "w" ? "🔥 " + rk.n + "x WIN" : rk.soort === "v" ? rk.n + "x VERLIES" : "-"}</b></span>` +
    `<span class="vak">LEVEL <b>${x.lvl}</b> <span class="xp"><i style="width:${x.pct}%"></i></span> <b>${x.p} XP</b></span>` +
    (OPEN.length ? `<a class="vak" href="#g-teloggen">! ${OPEN.length} TE LOGGEN</a>` : `<span class="vak">ALLES GELOGD <b>✓</b></span>`) +
    (typeof cockpitHtml === "function" ? cockpitHtml() : "");
}
function reeks() { let n = 0, s = null; for (let i = ALLE.length - 1; i >= 0; i--) { const w = ALLE[i].r > 0 ? "w" : ALLE[i].r < 0 ? "v" : null; if (!w) continue; if (!s) s = w; if (w !== s) break; n++; } return { soort: s, n }; }

/* ------------------------------------------------------------------ KPI's (tellen op) */
function stats(T) {
  const rs = T.map((t) => t.r), n = T.length, w = rs.filter((r) => r > 0).length;
  const winst = rs.filter((r) => r > 0).reduce((a, b) => a + b, 0), verlies = -rs.filter((r) => r < 0).reduce((a, b) => a + b, 0);
  let piek = 0, cum = 0, dd = 0; for (const r of rs) { cum += r; piek = Math.max(piek, cum); dd = Math.min(dd, cum - piek); }
  const be = T.filter((t) => t.be_min != null).length, met = T.filter((t) => t.sl_moves != null).length;
  return { n, w, winrate: n ? Math.round(100 * w / n) : 0, r: rs.reduce((a, b) => a + b, 0), exp: n ? rs.reduce((a, b) => a + b, 0) / n : 0,
    netto: T.reduce((s, t) => s + t.netto, 0), pf: verlies ? winst / verlies : null, dd, duur: n ? T.reduce((s, t) => s + (t.duur || 0), 0) / n : 0,
    be: met ? Math.round(100 * be / met) : null };
}
function telOp(el, doel, fmt) {
  const van = +el.dataset.w || 0, t0 = performance.now(); el.dataset.w = doel;
  const stap = (t) => { const f = Math.min(1, (t - t0) / 700), v = van + (doel - van) * (1 - Math.pow(1 - f, 3)); el.textContent = fmt(v); if (f < 1) requestAnimationFrame(stap); };
  requestAnimationFrame(stap);
}
function tekenKpi(T) {
  const s = stats(T);
  const tegels = [["TRADES", s.n, (v) => Math.round(v), null], ["WINRATE", s.winrate, (v) => Math.round(v) + "%", null],
    ["R TOTAAL", s.r, plusR, s.r], ["R PER TRADE", s.exp, plusR, s.exp], ["NETTO", s.netto, eur, s.netto],
    ["PROFIT FACTOR", s.pf ?? 0, (v) => s.pf == null ? "-" : nl(v), s.pf == null ? null : s.pf - 1], ["MAX DRAWDOWN", s.dd, plusR, s.dd < 0 ? -1 : null],
    ["GEM. DUUR", s.duur, (v) => Math.round(v) + " MIN", null], ["SL NAAR BE", s.be ?? 0, (v) => s.be == null ? "-" : Math.round(v) + "%", null]];
  const box = document.getElementById("g-kpi");
  if (!box.children.length) box.innerHTML = tegels.map((x, i) => `<div class="g-kpi" data-i="${i}"><b data-w="0">-</b><span>${x[0]}</span></div>`).join("");
  tegels.forEach(([, v, fmt, teken], i) => { const k = box.children[i]; k.className = "g-kpi" + (teken == null ? "" : teken > 0 ? " pos" : teken < 0 ? " neg" : "");
    telOp(k.querySelector("b"), v, fmt); });
}

/* ------------------------------------------------------------------ saldoverloop per X */
function bouwToggles() {
  const seg = (id, sleutel, opties) => { const el = document.getElementById(id);
    el.innerHTML = opties.map(([v, l]) => `<button data-v="${v}" class="${W[sleutel] === v ? "aan" : ""}">${l}</button>`).join("");
    el.addEventListener("click", (ev) => { const b = ev.target.closest("button"); if (!b) return; W[sleutel] = b.dataset.v;
      el.querySelectorAll("button").forEach((x) => x.classList.toggle("aan", x === b)); tekenSaldo(gefilterd()); }); };
  seg("g-per", "per", [["trade", "TRADE"], ["dag", "DAG"], ["week", "WEEK"], ["maand", "MAAND"]]);
  seg("g-eenheid", "eenheid", [["eur", "€"], ["r", "R"], ["pct", "%"]]);
  const g = document.getElementById("g-groep"), m = document.getElementById("g-metriek");
  g.innerHTML = Object.entries(DIM).map(([k, d]) => `<option value="${k}">${d.naam}</option>`).join("");
  m.innerHTML = Object.entries(MET).map(([k, d]) => `<option value="${k}">${d.naam}</option>`).join("");
  g.value = W.groep; m.value = W.metriek;
  g.onchange = () => { W.groep = g.value; tekenOntleed(gefilterd()); }; m.onchange = () => { W.metriek = m.value; tekenOntleed(gefilterd()); };
}
function tekenSaldo(T) {
  const gefilt = T.length !== ALLE.length;
  const sleutel = (t) => W.per === "trade" ? t.id : W.per === "dag" ? t.datum : W.per === "week" ? isoWeek(t.datum) : t.maand;
  const label = (t) => W.per === "trade" ? kort(t.datum) + " " + t.tijd : W.per === "dag" ? kort(t.datum) : W.per === "week" ? "wk " + isoWeek(t.datum).slice(-2) : t.maand;
  const groepen = []; const idx = {};
  for (const t of T) { const k = sleutel(t); if (!(k in idx)) { idx[k] = groepen.length; groepen.push({ label: label(t), datum: t.datum, r: 0, netto: 0, n: 0 }); }
    const g = groepen[idx[k]]; g.r += t.r; g.netto += t.netto; g.n++; }
  // saldo in €: zonder filter het echte saldo (start + stortingen + trades), met filter alleen het opgetelde resultaat van de selectie
  let basis = gefilt ? 0 : START, cum = 0, kasI = 0; const kas = KAS.slice().sort((a, b) => (a.datum + (a.tijd || "")).localeCompare(b.datum + (b.tijd || "")));
  const punten = groepen.map((g) => {
    if (!gefilt) while (kasI < kas.length && kas[kasI].datum <= g.datum) { basis += kas[kasI].bedrag; kasI++; }
    cum += W.eenheid === "r" ? g.r : g.netto;
    const v = W.eenheid === "r" ? cum : W.eenheid === "pct" ? (START ? 100 * cum / START : 0) : basis + cum;
    return +v.toFixed(2);
  });
  const boven = (punten[punten.length - 1] ?? 0) >= (W.eenheid === "eur" ? (gefilt ? 0 : START) : 0);
  const c = document.getElementById("c-saldo").getContext("2d"), grad = c.createLinearGradient(0, 0, 0, 260);
  grad.addColorStop(0, boven ? "rgba(61,255,138,.28)" : "rgba(255,90,79,.25)"); grad.addColorStop(1, "rgba(0,0,0,0)");
  maak("c-saldo", { type: "line", data: { labels: groepen.map((g) => g.label), datasets: [{ data: punten, borderColor: boven ? K.hi : K.red, backgroundColor: grad,
      fill: true, stepped: W.per !== "trade" ? false : false, tension: 0, borderWidth: 2, pointRadius: groepen.length < 40 ? 3 : 0, pointBackgroundColor: K.ink, pointStyle: "rect" }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => {
        const g = groepen[x.dataIndex]; return [`${W.eenheid === "r" ? "totaal " + plusR(x.parsed.y) : W.eenheid === "pct" ? "totaal " + nl(x.parsed.y) + "%" : "€" + nl(x.parsed.y)}`,
          `${g.n} trade${g.n > 1 ? "s" : ""} · ${plusR(g.r)} · ${eur(g.netto)}`]; } } } },
      animations: { x: { type: "number", easing: "linear", duration: 900, from: NaN, delay: (ctx) => ctx.type === "data" ? ctx.index * Math.min(40, 900 / Math.max(1, punten.length)) : 0 } },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } }, y: { grid: { color: "rgba(18,74,38,.5)" } } } } });
  maak("c-periode", { type: "bar", data: { labels: groepen.map((g) => g.label), datasets: [{ data: groepen.map((g) => +(W.eenheid === "r" ? g.r : g.netto).toFixed(2)),
      backgroundColor: groepen.map((g) => (W.eenheid === "r" ? g.r : g.netto) >= 0 ? K.hi : K.red) }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { grid: { color: "rgba(18,74,38,.4)" }, ticks: { maxTicksLimit: 3 } } } } });
  document.getElementById("g-saldo-uitleg").textContent = gefilt
    ? `Filter actief: de lijn is het opgetelde resultaat van alleen deze ${T.length} trades (geen saldo).`
    : `Saldo = startkapitaal €${nl(START)} + stortingen/opnames + je trades. Onder: resultaat per ${W.per}.`;
}

/* ------------------------------------------------------------------ ONTLEED: groeperen op X */
const bak = (v, grenzen, labels) => { if (v == null) return "?"; for (let i = 0; i < grenzen.length; i++) if (v < grenzen[i]) return labels[i]; return labels[labels.length - 1]; };
const botKlasse = (t) => { const b = BOTS[t.v3_sleutel]; if (!t.v3_sleutel) return "geen v3-setup"; if (!b) return "bots zagen hem niet";
  const x = b.uitdager || b.kampioen; return ["tp", "sl", "gevuld", "geplaatst", "gesloten"].includes(x.status) ? "bots namen hem ook" : "bots weigerden"; };
const DIM = {
  uur: { naam: "UUR VAN INSTAP", f: (t) => t.uur == null ? "?" : String(t.uur).padStart(2, "0") + "u", sort: true },
  weekdag: { naam: "WEEKDAG", f: (t) => t.weekdag, volgorde: WD },
  sessie: { naam: "SESSIE", f: (t) => t.sessie },
  richting: { naam: "RICHTING", f: (t) => t.richting },
  grade: { naam: "GRADE", f: (t) => t.grade, sort: true },
  emotie: { naam: "EMOTIE VOORAF", f: (t) => t.emotie },
  regels: { naam: "REGELS GEVOLGD", f: (t) => t.schoon === 1 ? "gevolgd" : t.schoon === 0 ? "gebroken" : "?" },
  exit: { naam: "HOE GESLOTEN", f: (t) => t.exit },
  tp_type: { naam: "TP-TYPE", f: (t) => t.tp_type },
  duur: { naam: "DUUR", f: (t) => bak(t.duur, [5, 15, 60], ["< 5 min", "5-15 min", "15-60 min", "> 60 min"]), volgorde: ["< 5 min", "5-15 min", "15-60 min", "> 60 min", "?"] },
  sl: { naam: "SL-AFSTAND", f: (t) => bak(t.sl_points, [10, 20, 40], ["< 10 pts", "10-20 pts", "20-40 pts", "> 40 pts"]), volgorde: ["< 10 pts", "10-20 pts", "20-40 pts", "> 40 pts", "?"] },
  be: { naam: "SL NAAR BREAK-EVEN", f: (t) => t.sl_moves == null ? "geen MT5-data" : t.be_min != null ? "ja" : "nee" },
  verruimd: { naam: "SL VERRUIMD", f: (t) => t.sl_moves == null ? "geen MT5-data" : t.sl_verruimd > 0 ? "ja, verruimd" : "nee" },
  bots: { naam: "WAT DEDEN DE BOTS", f: botKlasse },
  maand: { naam: "MAAND", f: (t) => t.maand, sort: true },
};
const MET = {
  r_som: { naam: "R TOTAAL", f: (g) => g.r, fmt: plusR }, r_gem: { naam: "R PER TRADE", f: (g) => g.r / g.n, fmt: plusR },
  winrate: { naam: "WINRATE", f: (g) => 100 * g.w / g.n, fmt: (v) => Math.round(v) + "%" }, n: { naam: "AANTAL", f: (g) => g.n, fmt: (v) => String(v) },
  netto: { naam: "NETTO €", f: (g) => g.netto, fmt: eur },
};
function tekenOntleed(T) {
  const d = DIM[W.groep], m = MET[W.metriek], gr = {};
  for (const t of T) { const k = d.f(t); const g = gr[k] = gr[k] || { k, n: 0, w: 0, r: 0, netto: 0 }; g.n++; g.w += t.r > 0; g.r += t.r; g.netto += t.netto; }
  let rij = Object.values(gr);
  if (d.volgorde) rij.sort((a, b) => d.volgorde.indexOf(a.k) - d.volgorde.indexOf(b.k)); else if (d.sort) rij.sort((a, b) => String(a.k).localeCompare(String(b.k))); else rij.sort((a, b) => b.n - a.n);
  const vals = rij.map((g) => +m.f(g).toFixed(2)), polar = ["r_som", "r_gem", "netto"].includes(W.metriek);
  maak("c-ontleed", { type: "bar", data: { labels: rij.map((g) => g.k), datasets: [{ data: vals, backgroundColor: vals.map((v) => polar ? (v >= 0 ? K.hi : K.red) : K.cyan) }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => { const g = rij[x.dataIndex];
        return [m.fmt(x.parsed.y), `${g.n} trades · winrate ${Math.round(100 * g.w / g.n)}% · ${plusR(g.r)} · ${eur(g.netto)}`]; } } } },
      onClick: (e, el) => { if (!el.length) return; const k = rij[el[0].index].k; F.extra = { label: d.naam + ": " + k, test: (t) => d.f(t) === k }; tekenAlles(); },
      scales: { x: { grid: { display: false } }, y: { grid: { color: "rgba(18,74,38,.5)" } } } } });
  document.getElementById("g-ontleed-tabel").innerHTML = `<table class="g-t"><tr><th>${esc(d.naam)}</th><th class="n">TRADES</th><th class="n">WIN%</th><th class="n">R</th><th class="n">R/TR</th><th class="n">€</th></tr>` +
    rij.map((g) => `<tr><td>${esc(g.k)}</td><td class="n">${g.n}</td><td class="n">${Math.round(100 * g.w / g.n)}%</td><td class="n ${g.r >= 0 ? "g-pos" : "g-neg"}">${plusR(g.r)}</td>
      <td class="n">${plusR(g.r / g.n)}</td><td class="n ${g.netto >= 0 ? "g-pos" : "g-neg"}">${eur(g.netto)}</td></tr>`).join("") + `</table>` +
    (rij.some((g) => g.n < 5) ? `<div class="g-uitleg">Groepen met minder dan 5 trades zeggen nog weinig.</div>` : "");
}

/* ------------------------------------------------------------------ heatmap, MFE/MAE, liggen, beheer */
function tekenHeat(T) {
  const uren = [...new Set(ALLE.map((t) => t.uur).filter((u) => u != null))].sort((a, b) => a - b);
  if (!uren.length) { document.getElementById("g-heat").innerHTML = ""; return; }
  const kleur = (v) => v == null ? "transparent" : v >= 0 ? `rgba(61,255,138,${Math.min(1, .25 + Math.abs(v) / 1.5)})` : `rgba(255,90,79,${Math.min(1, .25 + Math.abs(v) / 1.5)})`;
  let h = `<div class="g-heat" style="grid-template-columns:34px repeat(${uren.length},1fr)"><div></div>${uren.map((u) => `<div class="hk">${String(u).padStart(2, "0")}</div>`).join("")}`;
  for (const d of WD.slice(0, 5)) {
    h += `<div class="hw">${d.slice(0, 2).toUpperCase()}</div>`;
    for (const u of uren) { const c = T.filter((t) => t.weekdag === d && t.uur === u), r = c.length ? c.reduce((s, t) => s + t.r, 0) / c.length : null;
      h += `<div class="hc ${c.length ? "" : "leeg"}" data-d="${d}" data-u="${u}" style="background:${kleur(r)}" title="${d} ${u}:00 · ${c.length} trades${c.length ? " · " + plusR(r) + " per trade" : ""}">${c.length || ""}</div>`; }
  }
  const el = document.getElementById("g-heat"); el.innerHTML = h + "</div>";
  el.onclick = (ev) => { const c = ev.target.closest(".hc:not(.leeg)"); if (!c) return; F.weekdag = [c.dataset.d]; F.uur = [c.dataset.u]; tekenAlles(); };
}
function tekenMfe(T) {
  const p = T.filter((t) => t.mfe_r != null && t.mae_r != null);
  maak("c-mfe", { type: "scatter", data: { datasets: [{ data: p.map((t) => ({ x: t.mfe_r, y: t.mae_r })), pointStyle: "rect", pointRadius: 5, pointHoverRadius: 8,
      backgroundColor: p.map((t) => t.r >= 0 ? K.hi : K.red) }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => { const t = p[x.dataIndex];
        return [`#${t.id} ${kort(t.datum)} ${t.tijd} · ${plusR(t.r)}`, `mee ${nl(t.mfe_r)}R · tegen ${nl(t.mae_r)}R`]; } } } },
      onClick: (e, el) => { if (el.length) replay(p[el[0].index].id); },
      scales: { x: { title: { display: true, text: "MFE (R mee)" } }, y: { title: { display: true, text: "MAE (R tegen)" } } } } });
}
function tekenLiggen(T) {
  const w = T.filter((t) => t.r > 0 && t.mfe_r != null).map((t) => ({ t, liggen: Math.max(0, t.mfe_r - t.r) })).sort((a, b) => b.liggen - a.liggen);
  const om = T.filter((t) => t.r < 0 && t.mfe_r != null && t.mfe_r >= .5);
  const gem = w.length ? w.reduce((s, x) => s + x.liggen, 0) / w.length : 0, max = Math.max(.1, ...w.map((x) => x.liggen));
  document.getElementById("g-liggen").innerHTML = w.length
    ? `<div class="g-uitleg">Op je winnaars liep de prijs gemiddeld nog <b class="g-gold">${nl(gem)}R</b> verder dan je pakte.</div>` +
      w.slice(0, 7).map((x) => `<div class="g-balk"><span>#${x.t.id} ${kort(x.t.datum)} ${x.t.tijd} (${plusR(x.t.r)})</span><i style="width:${70 * x.liggen / max}%;background:${K.gold}"></i><b>${nl(x.liggen)}R</b></div>`).join("") +
      (om.length ? `<div class="g-uitleg" style="margin-top:6px">${om.length} verliezer${om.length > 1 ? "s" : ""} stond${om.length > 1 ? "en" : ""} eerst ≥ 0,5R in je voordeel.</div>` : "")
    : `<div class="g-uitleg">Nog geen winnaars met MFE in deze selectie.</div>`;
}
function tekenBeheer(T) {
  const met = T.filter((t) => t.sl_moves != null);
  if (!met.length) { document.getElementById("g-beheer").innerHTML = `<div class="g-uitleg">Geen MT5-positiedata in deze selectie.</div>`; return; }
  const be = met.filter((t) => t.be_min != null), geen = met.filter((t) => t.be_min == null);
  const s = (a) => a.length ? a.reduce((x, t) => x + t.r, 0) / a.length : null;
  const tpv = met.filter((t) => t.tp_moves > 0);
  document.getElementById("g-beheer").innerHTML =
    `<div class="g-balk"><span>SL naar break-even</span><i style="width:${70 * be.length / met.length}%;background:${K.cyan}"></i><b>${be.length}/${met.length} · ${plusR(s(be))} per trade</b></div>` +
    `<div class="g-balk"><span>SL bleef staan</span><i style="width:${70 * geen.length / met.length}%;background:${K.muted}"></i><b>${geen.length}/${met.length} · ${plusR(s(geen))} per trade</b></div>` +
    `<div class="g-balk"><span>TP verplaatst</span><i style="width:${70 * tpv.length / met.length}%;background:${K.gold}"></i><b>${tpv.length}/${met.length} · ${plusR(s(tpv))} per trade</b></div>` +
    (() => { const vr = met.filter((t) => t.sl_verruimd > 0); return `<div class="g-balk"><span class="${vr.length ? "g-neg" : ""}">SL verruimd (meer risico)</span><i style="width:${70 * vr.length / met.length}%;background:${K.red}"></i><b>${vr.length}/${met.length}${vr.length ? " · " + plusR(s(vr)) + " per trade" : ""}</b></div>`; })() +
    (be.length ? `<div class="g-uitleg" style="margin-top:6px">SL naar BE gemiddeld na <b class="g-ink">${nl(be.reduce((x, t) => x + t.be_min, 0) / be.length, 1)} min</b>. ` +
      `${be.filter((t) => Math.abs(t.r) < .1).length} van de ${be.length} eindigden daarna op break-even.</div>` : "") +
    `<div class="g-uitleg">Uit de MT5-events per positie (elke SL/TP-wijziging en de koers per minuut).</div>`;
}

/* ------------------------------------------------------------------ jij tegen de bots */
function tekenBots(T) {
  const kl = {}; for (const t of T) { const k = botKlasse(t); (kl[k] = kl[k] || []).push(t); }
  const volgorde = ["bots namen hem ook", "bots weigerden", "bots zagen hem niet", "geen v3-setup"];
  const rijen = volgorde.filter((k) => kl[k]).map((k) => { const a = kl[k], r = a.reduce((s, t) => s + t.r, 0);
    const botR = k === "bots namen hem ook" ? a.reduce((s, t) => s + ((BOTS[t.v3_sleutel].uitdager || BOTS[t.v3_sleutel].kampioen).r || 0), 0) : null;
    return `<tr><td>${esc(k)}</td><td class="n">${a.length}</td><td class="n ${r >= 0 ? "g-pos" : "g-neg"}">${plusR(r)}</td><td class="n">${botR == null ? "-" : plusR(botR)}</td></tr>`; });
  document.getElementById("g-bots").innerHTML = Object.keys(BOTS).length ? `<table class="g-t"><tr><th>JOUW TRADES</th><th class="n">AANTAL</th><th class="n">JIJ</th><th class="n">BOTS OP DEZELFDE</th></tr>${rijen.join("")}</table>
    <div class="g-uitleg">Gekoppeld op de setup-sleutel (sweep + BOS). 'Weigerden' = model of filter zei nee; de reden zie je in de replay.</div>`
    : `<div class="g-uitleg">Geen botdata (CBR Station niet bereikbaar).</div>`;
}
function tekenRace() {
  const el = document.getElementById("g-race"); if (!TEAMS || !TEAMS.teams) { el.innerHTML = ""; return; }
  const deel = [["JIJ", TEAMS.teams.marijn, "#ffffff"], ["KAMPIOEN", TEAMS.teams.kampioen, K.gold], ["UITDAGER", TEAMS.teams.uitdager, K.cyan]].filter((x) => x[1]);
  const rs = deel.map((x) => x[1].week.r), lo = Math.min(0, ...rs), hi = Math.max(.5, ...rs);
  el.innerHTML = `<div class="g-lbl">TEAMRACE DEZE WEEK (R)</div>` + deel.map(([n, x, c]) => `<div class="g-race-baan"><span class="naam">${n} ${plusR(x.week.r)}</span><div class="finish"></div>
    <div class="loper" style="left:0" data-doel="${(8 + 80 * (x.week.r - lo) / (hi - lo)).toFixed(1)}"><canvas width="12" height="14" data-kleur="${c}"></canvas></div></div>`).join("");
  el.querySelectorAll("canvas").forEach((cv) => tekenPoppetje(cv.getContext("2d"), 0, 0, cv.dataset.kleur, 0, 1));
  requestAnimationFrame(() => el.querySelectorAll(".loper").forEach((l) => l.style.left = l.dataset.doel + "%"));
}

/* ------------------------------------------------------------------ badges */
function badges() {
  const op = (f, n) => { let b = 0, h = 0; for (const t of ALLE) { if (f(t)) { h++; b = Math.max(b, h); } else h = 0; } return b >= n; };
  const wk = (d) => isoWeek(d), weken = {}; ALLE.forEach((t) => weken[wk(t.datum)] = (weken[wk(t.datum)] || 0) + t.r);
  const dezeWeek = ALLE.filter((t) => wk(t.datum) === wk(vandaagISO()));
  return [
    { id: "bloed", naam: "EERSTE BLOED", uitleg: "eerste winnende trade", aan: ALLE.some((t) => t.r > 0), icoon: "zwaard" },
    { id: "3r", naam: "SCHERPSCHUTTER", uitleg: "een trade van 3R of meer", aan: ALLE.some((t) => t.r >= 3), icoon: "pijl" },
    { id: "6r", naam: "MONSTERTRADE", uitleg: "een trade van 6R of meer", aan: ALLE.some((t) => t.r >= 6), icoon: "kroon" },
    { id: "rij3", naam: "HATTRICK", uitleg: "drie winnaars op rij", aan: op((t) => t.r > 0, 3), icoon: "vuur" },
    { id: "schoon5", naam: "DISCIPLINE", uitleg: "5 trades op rij alle regels gevolgd", aan: op((t) => t.schoon === 1, 5), icoon: "schild" },
    { id: "rust10", naam: "ZEN", uitleg: "10 trades rustig of gefocust begonnen", aan: ALLE.filter((t) => ["rustig", "gefocust"].includes(t.emotie)).length >= 10, icoon: "lotus" },
    { id: "norevenge", naam: "GEEN WRAAK", uitleg: "10 trades op rij zonder revenge", aan: op((t) => t.emotie !== "revenge", 10), icoon: "hart" },
    { id: "be3", naam: "BREAK-EVEN BAAS", uitleg: "3 keer je SL naar break-even", aan: ALLE.filter((t) => t.be_min != null).length >= 3, icoon: "slot" },
    { id: "groen", naam: "GROENE WEEK", uitleg: "een week positief in R", aan: Object.values(weken).some((r) => r > 0), icoon: "blad" },
    { id: "logboek", naam: "BOEKHOUDER", uitleg: "alles van deze week gelogd", aan: dezeWeek.length > 0 && dezeWeek.every((t) => t.beoordeeld === 1), icoon: "boek" },
    { id: "botbeater", naam: "BOT-BEATER", uitleg: "winst op een setup die de bots weigerden", aan: ALLE.some((t) => t.r > 0 && botKlasse(t) === "bots weigerden"), icoon: "robot" },
    { id: "dagmax", naam: "STOPPER", uitleg: "10 dagen binnen het dagmaximum", aan: Object.values(ALLE.reduce((a, t) => (a[t.datum] = (a[t.datum] || 0) + 1, a), {})).filter((n) => n <= 2).length >= 10, icoon: "stop" },
  ];
}
function tekenBadges() {
  let gezien = []; try { gezien = JSON.parse(localStorage.getItem("cbr_badges") || "[]"); } catch (e) {}
  const B = badges();
  document.getElementById("g-badges").innerHTML = B.map((b) => `<div class="g-badge ${b.aan ? "aan" : ""} ${b.aan && !gezien.includes(b.id) ? "nieuw" : ""}">
    <canvas width="12" height="12" data-icoon="${b.icoon}" data-aan="${b.aan ? 1 : 0}"></canvas><b>${b.naam}</b><span>${b.uitleg}</span></div>`).join("");
  document.querySelectorAll("#g-badges canvas").forEach((c) => tekenIcoon(c.getContext("2d"), c.dataset.icoon, c.dataset.aan === "1"));
  try { localStorage.setItem("cbr_badges", JSON.stringify(B.filter((b) => b.aan).map((b) => b.id))); } catch (e) {}
}

/* ------------------------------------------------------------------ kalender, trades, te loggen */
let kalMaand = null;
function tekenKal() {
  if (!kalMaand) kalMaand = vandaagISO().slice(0, 7);
  const [j, m] = kalMaand.split("-").map(Number), eerste = new Date(j, m - 1, 1), dagen = new Date(j, m, 0).getDate(), leeg = (eerste.getDay() + 6) % 7;
  const per = {}; ALLE.filter((t) => t.maand === kalMaand).forEach((t) => { const p = per[t.datum] = per[t.datum] || { r: 0, n: 0 }; p.r += t.r; p.n++; });
  let h = `<div class="g-kop"><button class="g-knop" data-k="-1">‹</button><b>${eerste.toLocaleDateString("nl-NL", { month: "long", year: "numeric" }).toUpperCase()}</b><button class="g-knop" data-k="1">›</button></div>
    <div class="g-kal">${["MA", "DI", "WO", "DO", "VR", "ZA", "ZO"].map((x) => `<div class="kh">${x}</div>`).join("")}`;
  for (let i = 0; i < leeg; i++) h += `<div></div>`;
  for (let d = 1; d <= dagen; d++) { const iso = `${kalMaand}-${String(d).padStart(2, "0")}`, p = per[iso];
    h += `<div class="kc ${p ? (p.r >= 0 ? "w" : "v") : ""} ${iso === vandaagISO() ? "nu" : ""}" title="${p ? p.n + " trades · " + plusR(p.r) : ""}"><span>${d}</span>${p ? `<b>${plusR(p.r)}</b>` : ""}</div>`; }
  const el = document.getElementById("g-kal"); el.innerHTML = h + "</div>";
  el.querySelectorAll("[data-k]").forEach((b) => b.onclick = () => { const d = new Date(j, m - 1 + +b.dataset.k, 1); kalMaand = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; tekenKal(); });
}
function tekenTrades(T) {
  const kans = (t) => { const b = BOTS[t.v3_sleutel]; const x = b && (b.uitdager || b.kampioen); return x && x.kans != null ? Math.round(100 * x.kans) + "%" : "-"; };
  document.getElementById("g-trades").innerHTML = `<div class="g-tabelvak" style="max-height:420px"><table class="g-t"><tr><th>#</th><th>DATUM</th><th>TIJD</th><th>RICHTING</th><th>GRADE</th><th>EMOTIE</th><th>EXIT</th><th>BOTS</th><th class="n" title="modelkans van de bots op deze setup (tweede mening)">KANS</th><th class="n">R</th><th class="n">€</th></tr>` +
    T.slice().reverse().map((t) => `<tr class="klik" data-id="${t.id}"><td class="g-dim">${t.id}</td><td>${kort(t.datum)}</td><td>${esc(t.tijd)}</td><td>${t.richting === "long" ? "▲ LONG" : "▼ SHORT"}</td>
      <td class="g-gold">${esc(t.grade)}</td><td>${esc(t.emotie)}</td><td>${esc(t.exit)}</td><td class="g-dim">${esc(botKlasse(t).replace("bots ", ""))}</td><td class="n g-cyan">${kans(t)}</td>
      <td class="n ${t.r >= 0 ? "g-pos" : "g-neg"}">${plusR(t.r)}</td><td class="n ${t.netto >= 0 ? "g-pos" : "g-neg"}">${eur(t.netto)}</td></tr>`).join("") + `</table></div>`;
  document.getElementById("g-trades").onclick = (ev) => { const r = ev.target.closest("tr[data-id]"); if (r) replay(+r.dataset.id); };
}
function tekenTeLoggen() {
  if (typeof tekenLogKaarten === "function") return tekenLogKaarten();          // game3.js: loggen in game mode
  document.getElementById("g-teloggen").innerHTML = OPEN.length ? `<section class="g-paneel g-teloggen"><h3>! NOG TE LOGGEN: ${OPEN.length}</h3>
    <div class="g-uitleg">${OPEN.map((t) => `#${t.id} ${kort(t.datum)} ${esc(t.tijd || "")} ${t.richting === "long" ? "▲" : "▼"}`).join(" · ")} — <a href="/#te-loggen">nu loggen (klassiek scherm) →</a></div></section>` : "";
}

/* ------------------------------------------------------------------ pixelkunst: poppetjes, iconen, scène */
function tekenPoppetje(g, x, y, kleur, fase, s) {
  const p = (dx, dy, w, h, c) => { g.fillStyle = c; g.fillRect(x + dx * s, y + dy * s, w * s, h * s); };
  p(4, 0, 4, 4, "#f2c9a0"); p(3, 0, 6, 1, "#3a2a12");                          // hoofd + haar
  p(3, 4, 6, 5, kleur); p(4, 5, 1, 1, "#02120a");                             // lijf
  const l = fase % 2 === 0;
  p(l ? 3 : 4, 9, 2, 4, "#1f2a3a"); p(l ? 7 : 6, 9, 2, 4, "#1f2a3a");          // benen (lopen)
}
const ICOON = {
  zwaard: ["....X", "...X.", "X.X..", ".X...", "X.X.."], pijl: ["..X..", ".XXX.", "X.X.X", "..X..", "..X.."], kroon: ["X.X.X", "XXXXX", "XXXXX", ".....", "XXXXX"],
  vuur: ["..X..", ".XX..", ".XXX.", "XXXXX", ".XXX."], schild: ["XXXXX", "XXXXX", "XXXXX", ".XXX.", "..X.."], lotus: ["..X..", "X.X.X", "XXXXX", ".XXX.", "....."],
  hart: [".X.X.", "XXXXX", "XXXXX", ".XXX.", "..X.."], slot: [".XXX.", ".X.X.", "XXXXX", "XX.XX", "XXXXX"], blad: ["...XX", "..XXX", ".XXX.", "XXX..", "X...."],
  boek: ["XXXX.", "X..X.", "XXXX.", "X..X.", "XXXX."], robot: [".XXX.", "X.X.X", "XXXXX", ".X.X.", "XX.XX"], stop: [".XXX.", "XXXXX", "X...X", "XXXXX", ".XXX."],
};
function tekenIcoon(g, naam, aan) {
  g.clearRect(0, 0, 12, 12); const m = ICOON[naam] || ICOON.kroon;
  m.forEach((r, j) => [...r].forEach((c, i) => { if (c === "X") { g.fillStyle = aan ? (naam === "hart" || naam === "vuur" ? "#ff8f8a" : "#ffd36b") : "#2b6b43"; g.fillRect(1 + i * 2, 1 + j * 2, 2, 2); } }));
}
let sceneT = 0, munten = [];
function tekenScene() {
  const cv = document.getElementById("g-scene"); if (!cv) return; const g = cv.getContext("2d"); g.imageSmoothingEnabled = false;
  const W_ = cv.width, H_ = cv.height, vd = ALLE.filter((t) => t.datum === vandaagISO()), r = vd.reduce((s, t) => s + t.r, 0);
  g.fillStyle = "#02120a"; g.fillRect(0, 0, W_, H_);
  for (let x = 0; x < W_; x += 8) for (let y = 0; y < 86; y += 8) { g.fillStyle = ((x + y) / 8) % 2 ? "#0a2414" : "#0c2b18"; g.fillRect(x, y, 8, 8); }   // vloer
  g.fillStyle = "#124a26"; g.fillRect(0, 86, W_, 2);                                                                      // muurrand
  // bureau + scherm met je R-lijn (gefilterd)
  g.fillStyle = "#3a2a12"; g.fillRect(40, 52, 120, 8); g.fillStyle = "#6b4c1f"; g.fillRect(40, 52, 120, 1);
  g.fillStyle = "#020603"; g.fillRect(70, 18, 70, 34); g.strokeStyle = "#2fb866"; g.strokeRect(70.5, 18.5, 69, 33);
  const T = gefilterd(); let cum = 0; const pts = T.map((t) => (cum += t.r)); const lo = Math.min(0, ...pts), hi = Math.max(.5, ...pts);
  g.strokeStyle = cum >= 0 ? K.hi : K.red; g.beginPath(); pts.forEach((v, i) => { const x = 73 + i / Math.max(1, pts.length - 1) * 64, y = 48 - (v - lo) / (hi - lo) * 26; i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke();
  // jij
  const bob = Math.floor(sceneT / 30) % 2;
  tekenPoppetje(g, 44, 34 - bob, "#ffffff", 0, 2);
  // stemming boven je hoofd
  const st = !vd.length ? "z" : r > 0 ? "♥" : r < 0 ? "#" : "~";
  g.fillStyle = "#02120a"; g.fillRect(50, 14 - bob, 14, 14); g.strokeStyle = "#d8ffe6"; g.strokeRect(50.5, 14.5 - bob, 13, 13);
  g.fillStyle = r > 0 ? K.gold : r < 0 ? K.rood : K.muted; g.font = "16px VT323"; g.fillText(st, 54, 26 - bob);
  // munten bij een positieve dag, regen bij een negatieve
  if (vd.length && r > 0 && Math.random() < .25) munten.push({ x: 40 + Math.random() * 130, y: -4, v: .6 + Math.random() });
  munten = munten.filter((m) => (m.y += m.v) < 52); munten.forEach((m) => { g.fillStyle = K.gold; g.fillRect(m.x, m.y, 3, 3); });
  if (vd.length && r < 0) for (let i = 0; i < 12; i++) { g.fillStyle = "#7fe3ff"; g.fillRect(36 + ((i * 37 + sceneT * 3) % 130), (i * 11 + sceneT * 4) % 50, 1, 3); }
  // de kamer: raam met dag/nacht, klok, plank met je badges, bordje met je dagmaximum, plant
  const nu = new Date(), uur = nu.getHours(), dag = uur >= 7 && uur < 19;
  g.fillStyle = "#124a26"; g.fillRect(200, 10, 74, 44); g.fillStyle = dag ? "#1d5a7a" : "#06102a"; g.fillRect(203, 13, 68, 38);
  g.fillStyle = dag ? "#ffd36b" : "#d8ffe6"; g.fillRect(dag ? 250 : 255, dag ? 20 : 18, 6, 6);                                      // zon of maan
  if (!dag) for (let i = 0; i < 6; i++) { g.fillStyle = "#d8ffe6"; g.fillRect(208 + (i * 23) % 60, 16 + (i * 13) % 30, 1, 1); }
  g.fillStyle = "#124a26"; g.fillRect(236, 13, 2, 38); g.fillRect(203, 31, 68, 2);
  g.fillStyle = "#020603"; g.fillRect(300, 12, 70, 18); g.strokeStyle = "#2fb866"; g.strokeRect(300.5, 12.5, 69, 17);       // digitale klok
  g.fillStyle = K.hi; g.font = "18px VT323"; g.fillText(nu.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" }), 312, 26);
  const nb = badges().filter((b) => b.aan).length;                                                                       // plank met bekers
  g.fillStyle = "#6b4c1f"; g.fillRect(392, 38, 120, 3);
  for (let i = 0; i < Math.min(12, nb); i++) { g.fillStyle = K.gold; g.fillRect(396 + i * 10, 30, 6, 5); g.fillRect(398 + i * 10, 35, 2, 3); }
  g.fillStyle = K.muted; g.font = "13px VT323"; g.fillText(nb + " BADGES", 396, 52);
  const dm = vd.length > MAXDAG ? K.red : vd.length === MAXDAG ? K.gold : K.hi;                                         // bordje dagmaximum
  g.fillStyle = "#020603"; g.fillRect(534, 14, 78, 34); g.strokeStyle = dm; g.strokeRect(534.5, 14.5, 77, 33);
  g.fillStyle = dm; g.font = "14px VT323"; g.fillText("MAX " + MAXDAG + "/DAG", 541, 27); g.fillText("VANDAAG " + vd.length, 541, 41);
  g.fillStyle = "#2fb866"; g.fillRect(176, 60, 8, 10); g.fillStyle = "#3dff8a"; g.fillRect(174, 54, 4, 6); g.fillRect(182, 52, 4, 8); g.fillRect(178, 50, 4, 6);   // plant
  // de teamrace onderin (jij / kampioen / uitdager, positie = R deze week)
  g.fillStyle = "#061009"; g.fillRect(0, 90, W_, 42); for (let x = 0; x < W_; x += 16) { g.fillStyle = "#124a26"; g.fillRect(x, 110, 8, 1); }
  g.fillStyle = "#d8ffe6"; for (let y = 90; y < 132; y += 6) g.fillRect(W_ - 14, y, 4, 3);
  if (TEAMS && TEAMS.teams) {
    const d = [["JIJ", TEAMS.teams.marijn, "#ffffff"], ["KAMP", TEAMS.teams.kampioen, K.gold], ["UITD", TEAMS.teams.uitdager, K.cyan]].filter((x) => x[1]);
    const rs = d.map((x) => x[1].week.r), lo2 = Math.min(0, ...rs), hi2 = Math.max(.5, ...rs);
    g.fillStyle = K.muted; g.font = "13px VT323"; g.fillText("TEAMRACE DEZE WEEK (R) >", W_ - 150, 101);
    d.forEach(([n, x, c], i) => { const doel = 200 + (x.week.r - lo2) / (hi2 - lo2) * (W_ - 260);
      const xx = Math.min(doel, 200 + sceneT * 3), y = 92 + i * 13, loopt = xx < doel;
      tekenPoppetje(g, xx, y - 4, c, loopt ? Math.floor(sceneT / 3) + i : 0, 1);
      g.fillStyle = c; g.font = "13px VT323"; g.fillText(n + " " + plusR(x.week.r), 8, y + 7); });
  } else { g.fillStyle = K.muted; g.font = "15px VT323"; g.fillText("TEAMRACE: CBR STATION NIET BEREIKBAAR", 200, 116); }
}
function scenelus() { sceneT++; tekenScene(); setTimeout(() => requestAnimationFrame(scenelus), 90); }

/* ------------------------------------------------------------------ replay */
let rp = null;
async function replay(id) {
  const d = await haal("/api/game/replay/" + id); if (d.error) return;
  const t = ALLE.find((x) => x.id === id) || {};
  document.getElementById("g-replay").hidden = false;
  document.getElementById("g-replay-titel").textContent = `REPLAY #${id} · ${kort(d.trade.datum)} ${d.trade.tijd_entry} ${d.trade.richting === "long" ? "▲ LONG" : "▼ SHORT"} · ${plusR(t.r)}`;
  rp = { d, t, i: 0, snel: rp ? rp.snel : 2, speelt: true };
  const snel = document.getElementById("rp-snel");
  snel.innerHTML = [1, 2, 4].map((s) => `<button data-s="${s}" class="${rp.snel === s ? "aan" : ""}">${s}X</button>`).join("");
  snel.onclick = (ev) => { const b = ev.target.closest("button"); if (!b) return; rp.snel = +b.dataset.s; snel.querySelectorAll("button").forEach((x) => x.classList.toggle("aan", x === b)); };
  const b = BOTS[t.v3_sleutel] || {};
  document.getElementById("rp-info").innerHTML = `<table class="g-t">
    <tr><td>ENTRY</td><td>${nl(d.trade.entry_prijs)}</td><td>SL</td><td class="g-neg">${nl(d.trade.sl_prijs)}</td><td>TP</td><td class="g-pos">${nl(d.trade.tp_prijs)}</td></tr>
    <tr><td>EXIT</td><td>${nl(d.trade.exit_prijs)}</td><td colspan="4">${esc(d.trade.exit_reden || "")}</td></tr>
    <tr><td>GRADE</td><td class="g-gold">${esc(d.trade.grade || "?")}</td><td>EMOTIE</td><td colspan="3">${esc(d.trade.emotie_voor || "-")}</td></tr>
    <tr><td>BEHEER</td><td colspan="5">${t.sl_moves != null ? `SL ${t.sl_moves}x verplaatst${t.be_min != null ? " (naar BE na " + nl(t.be_min, 1) + " min)" : ""} · TP ${t.tp_moves}x` : "geen MT5-events"}</td></tr>
    ${d.trade.les ? `<tr><td>LES</td><td colspan="5">${esc(d.trade.les)}</td></tr>` : ""}</table>`;
  document.getElementById("rp-bots").innerHTML = `<div class="g-lbl">WAT DEDEN DE BOTS MET DEZE SETUP</div>` + (Object.keys(b).length
    ? Object.entries(b).map(([team, x]) => `<div class="g-balk"><span class="${team === "kampioen" ? "g-gold" : "g-cyan"}">${team.toUpperCase()}</span><b>${esc(x.status.toUpperCase())}${x.r != null ? " " + plusR(x.r) : ""}</b></div>
      <div class="g-uitleg">${esc(x.reden)}${x.entry ? ` · entry ${nl(x.entry)} SL ${nl(x.sl)}` : ""}</div>`).join("")
    : `<div class="g-uitleg">${t.v3_sleutel ? "De bots zagen deze setup niet (of het station was niet bereikbaar)." : "Geen v3-setup aan deze trade gekoppeld."}</div>`);
  if (!rp.loopt) { rp.loopt = true; rplus(); }
}
function rplus() {
  if (!rp || document.getElementById("g-replay").hidden) { if (rp) rp.loopt = false; return; }
  const C = rp.d.candles; if (rp.speelt && rp.i < C.length) rp.i = Math.min(C.length, rp.i + .12 * rp.snel);
  tekenReplay(); requestAnimationFrame(rplus);
}
function tekenReplay() {
  const cv = document.getElementById("rp-canvas"), g = cv.getContext("2d"), W_ = cv.width, H_ = cv.height, { d } = rp, C = d.candles, tr = d.trade;
  g.fillStyle = "#02120a"; g.fillRect(0, 0, W_, H_);
  if (!C.length) { g.fillStyle = K.muted; g.font = "22px VT323"; g.fillText("GEEN CANDLES VOOR DEZE TRADE IN MARKTDATA", 30, 60); return; }
  const prijzen = C.flatMap((c) => [c[2], c[3]]).concat([tr.entry_prijs, tr.sl_prijs, tr.tp_prijs].filter((x) => x != null));
  const lo = Math.min(...prijzen) - .5, hi = Math.max(...prijzen) + .5, y = (p) => 14 + (hi - p) / (hi - lo) * (H_ - 40), bw = (W_ - 70) / C.length;
  const ie = C.findIndex((c) => c[0].slice(11, 16) >= (tr.tijd_entry || "").slice(0, 5)), ix = C.findIndex((c) => c[0].slice(11, 16) >= (tr.tijd_exit || "99"));
  // niveaus
  const lijn = (p, kleur, label) => { if (p == null) return; g.strokeStyle = kleur; g.setLineDash([6, 4]); g.beginPath(); g.moveTo(0, y(p)); g.lineTo(W_ - 66, y(p)); g.stroke(); g.setLineDash([]);
    g.fillStyle = kleur; g.font = "16px VT323"; g.fillText(label + " " + nl(p), W_ - 64, y(p) + 4); };
  lijn(tr.tp_prijs, K.hi, "TP"); lijn(tr.sl_prijs, K.red, "SL"); lijn(tr.entry_prijs, K.ink, "IN");
  if (ie >= 0) { g.fillStyle = "rgba(127,227,255,.07)"; g.fillRect(ie * bw, 0, ((ix >= 0 ? ix : C.length) - ie) * bw, H_ - 24); }
  const n = Math.floor(rp.i);
  for (let i = 0; i < n; i++) { const [, o, h, l, c] = C[i], x = i * bw, op = c >= o;
    g.fillStyle = op ? K.hi : K.red; g.fillRect(x + bw / 2 - .5, y(h), 1, Math.max(1, y(l) - y(h))); g.fillRect(x + 1, y(Math.max(o, c)), Math.max(1, bw - 2), Math.max(1, Math.abs(y(o) - y(c)))); }
  if (ie >= 0 && n > ie) { g.fillStyle = K.gold; g.fillRect(ie * bw, y(tr.entry_prijs) - 3, 6, 6); g.font = "16px VT323"; g.fillText("ENTRY " + tr.tijd_entry, ie * bw + 8, y(tr.entry_prijs) - 6); }
  if (ix >= 0 && n > ix && tr.exit_prijs) { g.fillStyle = K.cyan; g.fillRect(ix * bw, y(tr.exit_prijs) - 3, 6, 6); g.fillText("EXIT " + (tr.tijd_exit || ""), ix * bw + 8, y(tr.exit_prijs) + 16); }
  // SL/TP-wijzigingen (MT5-events): de echte SL en TP als traplijn mee met de trade, plus een markering per wijziging
  const ev = (d.events || []).map((e) => ({ ...e, i: C.findIndex((c) => c[0].slice(11, 16) >= e.ts.slice(11, 16)) })).filter((e) => e.i >= 0);
  const eind = Math.min(n, ix >= 0 ? ix + 1 : C.length);
  for (const [veld, kleur] of [["sl", K.red], ["tp", K.hi]]) {
    g.strokeStyle = kleur; g.lineWidth = 3; g.beginPath(); let gestart = false;
    ev.forEach((e, j) => { if (e[veld] == null || e.i >= eind) return; const x0 = e.i * bw, x1 = (j + 1 < ev.length ? Math.min(ev[j + 1].i, eind) : eind) * bw;
      if (!gestart) { g.moveTo(x0, y(e[veld])); gestart = true; } else g.lineTo(x0, y(e[veld])); g.lineTo(x1, y(e[veld])); });
    g.stroke(); g.lineWidth = 1;
  }
  for (const e of ev) { if (e.i >= n) continue; g.fillStyle = K.amber; g.fillRect(e.i * bw, H_ - 22, 3, 8); }
  g.fillStyle = K.muted; g.font = "15px VT323"; g.fillText(C[0][0].slice(11, 16), 2, H_ - 4); g.fillText(C[C.length - 1][0].slice(11, 16), W_ - 110, H_ - 4);
  g.fillText("DIKKE LIJNEN = JOUW SL (ROOD) EN TP (GROEN) ZOALS IN MT5 · ORANJE = AANGEPAST", 140, H_ - 4);
}
document.getElementById("rp-play").onclick = () => { if (!rp) return; if (rp.i >= rp.d.candles.length) rp.i = 0; rp.speelt = !rp.speelt;
  document.getElementById("rp-play").textContent = rp.speelt ? "❚❚ PAUZE" : "▶ AFSPELEN"; };
document.getElementById("rp-dicht").onclick = () => { document.getElementById("g-replay").hidden = true; };
document.getElementById("g-replay").onclick = (e) => { if (e.target.id === "g-replay") e.target.hidden = true; };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") document.getElementById("g-replay").hidden = true; });

document.addEventListener("DOMContentLoaded", boot);
