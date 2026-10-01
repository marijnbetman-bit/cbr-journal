// Performance-dashboard — MetaTrader-vibes, veel grafieken, beloning.

const C = (() => {
  // Kleuren uit de CSS-variabelen, zodat het thema op één plek staat.
  const v = (naam, terugval) => {
    const x = getComputedStyle(document.documentElement).getPropertyValue(naam).trim();
    return x || terugval;
  };
  return {
    green: v("--c-green", "#549a6b"),
    blue: v("--c-teal", "#519890"),
    red: v("--c-red", "#ca6861"),
    amber: v("--c-gold", "#a98247"),
    purple: v("--c-plum", "#9977c1"),
    text: v("--text", "#ece4f0"),
    muted: v("--muted", "#a597ae"),
    grid: "color-mix(in srgb, " + v("--border", "#35283f") + " 70%, transparent)",
  };
})();

// Doorzichtige variant van een themakleur, voor vlakken onder een lijn.
function mix(kleur, pct) {
  return `color-mix(in srgb, ${kleur} ${pct}%, transparent)`;
}
const GRADE_COLOR = { A: C.green, B: C.blue, C: C.red };
const charts = {};
let VALUTA = "€";

Chart.defaults.color = C.muted;
Chart.defaults.font.family = "'Segoe UI', system-ui, -apple-system, sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.elements.bar.borderRadius = 2;
Chart.defaults.borderColor = C.grid;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 8;

let period = "all";
let bron = (function () { try { return localStorage.getItem("cbr_bron") || "live"; } catch (e) { return "live"; } })();

function periodRange(p) {
  const now = new Date();
  const iso = (d) => d.toISOString().slice(0, 10);
  if (p === "week") {
    const day = (now.getDay() + 6) % 7; // maandag=0
    const mon = new Date(now); mon.setDate(now.getDate() - day);
    return { van: iso(mon), tot: iso(now) };
  }
  if (p === "month") {
    const first = new Date(now.getFullYear(), now.getMonth(), 1);
    return { van: iso(first), tot: iso(now) };
  }
  return { van: null, tot: null };
}

async function boot() {
  const settings = await api("/api/settings");
  VALUTA = settings.valuta || "€";
  document.getElementById("startkapitaal").value = settings.startkapitaal || "0";
  document.getElementById("maxTrades").value = settings.max_trades_dag ?? 3;
  document.getElementById("stopNa").value = settings.stop_na_verliezen ?? 2;

  document.querySelectorAll("#periodTabs button").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#periodTabs button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      period = b.dataset.p;
      load();
    });
  });
  document.querySelectorAll("#bronTabs button").forEach((b) => {
    b.classList.toggle("on", b.dataset.b === bron);
    b.addEventListener("click", () => {
      document.querySelectorAll("#bronTabs button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      bron = b.dataset.b;
      try { localStorage.setItem("cbr_bron", bron); } catch (e) {}
      load();
    });
  });
  document.getElementById("saveKapitaal").addEventListener("click", async () => {
    const val = parseFloat(document.getElementById("startkapitaal").value) || 0;
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ startkapitaal: val }) });
    toast("Startkapitaal bijgewerkt");
    load();
  });

  document.getElementById("saveRegels").addEventListener("click", async () => {
    await api("/api/settings", { method: "PUT", body: JSON.stringify({
      max_trades_dag: parseInt(document.getElementById("maxTrades").value, 10) || 0,
      stop_na_verliezen: parseInt(document.getElementById("stopNa").value, 10) || 0,
    }) });
    toast("Dagregels bijgewerkt");
  });

  setupLagen();
  await load();
}

// ---------- Fase 13.1 + 16.2: vier lagen, en alleen rekenen wat je opent ----------
let laag = (function () {
  const uit = new URLSearchParams(location.search).get("laag");
  if (uit) return uit;
  try { return localStorage.getItem("cbr_laag") || "vandaag"; } catch (e) { return "vandaag"; }
})();
const geladen = new Set();          // welke lagen al data hebben voor de huidige filters

function setupLagen() {
  document.querySelectorAll("#lagen button").forEach((b) => {
    b.classList.toggle("on", b.dataset.l === laag);
    b.addEventListener("click", () => kiesLaag(b.dataset.l));
  });
  toonLaag();
}

function toonLaag() {
  document.querySelectorAll("#lagen button").forEach((b) =>
    b.classList.toggle("on", b.dataset.l === laag));
  document.querySelectorAll(".laag").forEach((el) => {
    el.hidden = el.dataset.laag !== laag;
  });
  history.replaceState(null, "", "/dashboard?laag=" + laag);
}

async function kiesLaag(nieuw) {
  laag = nieuw;
  try { localStorage.setItem("cbr_laag", laag); } catch (e) {}
  toonLaag();
  if (!geladen.has(laag)) await load();
  else window.scrollTo({ top: 0, behavior: "smooth" });
}

// Filters veranderen: alle lagen opnieuw ophalen zodra je ze opent.
function verversAlles() {
  geladen.clear();
  load();
}

async function load() {
  const { van, tot } = periodRange(period);
  const qp = ["deel=" + laag];
  if (van) qp.push("van=" + van);
  if (tot) qp.push("tot=" + tot);
  if (period === "regel") qp.push("sinds_regel=true");
  qp.push("bron=" + encodeURIComponent(bron));
  if (laag === "edge" && simSl !== null) qp.push("sl_points=" + simSl);

  document.body.classList.add("laadt");
  let s;
  try { s = await api("/api/stats?" + qp.join("&")); }
  finally { document.body.classList.remove("laadt"); }
  geladen.add(laag);

  // Altijd aanwezig, want ze staan in de kop of sturen de andere lagen aan.
  renderBron(s);
  renderRegelFilter(s);

  if (laag === "vandaag") {
    renderMtBar(s);
    renderBalans(s);
    renderDubbels(s);
    renderDataBar(s);
    renderReward(s);
    renderProces(s.proces);
    renderEquityNote(s);
    grafiekenVandaag(s);
    renderHistory(s);
  } else if (laag === "edge") {
    renderSweep(s.sweep);
    renderEdge(s.edge);
    renderSimulatie(s.simulatie);
    grafiekenEdge(s);
  } else if (laag === "discipline") {
    renderAdherentie(s.adherentie);
    renderGemist(s.gemist, s.adherentie);
    renderDisciplineMeter(s);
    renderVenster(s.proces);
    renderSessies(s.proces);
    renderDataBar(s);
    grafiekenDiscipline(s);
  } else if (laag === "patronen") {
    renderKwaliteit(s.kwaliteit, s.in_hourly);
    renderPatronen(s);
    grafiekenPatronen(s);
  }
}

// ---------- helpers ----------
function eur(n) {
  if (n === null || n === undefined) return "–";
  return VALUTA + " " + (n >= 0 ? "+" : "") + Number(n).toFixed(2).replace(".", ",");
}
function cls(n) { return n > 0 ? "pos" : (n < 0 ? "neg" : ""); }
function mkChart(id, cfg) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), cfg);
}
function signColors(arr, pos, neg) {
  return arr.map((v) => (v >= 0 ? pos : neg));
}

// ---------- MT account-bar ----------
function renderMtBar(s) {
  const k = s.kpi;
  const cells = [
    { key: "Balance", val: eur(k.eindkapitaal), cls: "", accent: true, mono: true },
    { key: "Netto P/L", val: eur(k.netto_eur), cls: cls(k.netto_eur), mono: true },
    { key: "Winrate", val: k.winrate + "%", cls: "" },
    { key: "★ Perfecte trades", val: String(s.grade_dist.A || 0), cls: "", accent: true },
    { key: "Valide setups", val: k.valide_pct + "%", cls: "" },
    { key: "Groei", val: (k.groei_pct >= 0 ? "+" : "") + k.groei_pct + "%", cls: cls(k.groei_pct), mono: true },
  ];
  document.getElementById("mtBar").innerHTML = cells.map((c) => `
    <div class="mt-cell ${c.accent ? "accent" : ""}">
      <div class="k">${c.key}</div>
      <div class="val ${c.mono ? "mono" : ""} ${c.cls}">${c.val}</div>
    </div>`).join("");
}

// ---------- Balans-check: klopt de journal met je broker? ----------
function renderBalans(s) {
  const b = s.balans || {};
  const box = document.getElementById("balansCheck");
  const invoer = `<input type="number" step="0.01" id="werkBalans" placeholder="bv 64.57"
      value="${b.werkelijk !== null && b.werkelijk !== undefined ? b.werkelijk : ""}" />
    <button class="btn" id="saveBalans">Bijwerken</button>`;

  let klasse = "", ic = "", txt;
  if (b.werkelijk === null || b.werkelijk === undefined) {
    txt = `<b>Balans-check.</b> Vul hier het saldo in dat je broker laat zien, dan waarschuw ik
      zodra de journal daarvan afwijkt — meestal een trade die je vergeten bent te loggen.`;
  } else if (Math.abs(b.verschil) < 0.01) {
    klasse = "match"; ic = "✓";
    txt = `<b>Journal klopt met je broker.</b> Beide staan op ${eur(b.journaal)}. Alles gelogd.`;
  } else {
    klasse = "mismatch"; ic = "!";
    const meer = b.verschil > 0;
    txt = `<b>Er ontbreekt iets.</b> Je broker staat op ${eur(b.werkelijk)}, de journal op
      ${eur(b.journaal)} — een verschil van <b>${eur(b.verschil)}</b>.
      ${meer ? "Waarschijnlijk een winnende trade die nog niet gelogd is."
             : "Waarschijnlijk een verliezende trade die nog niet gelogd is, of een storting/opname."}`;
  }

  box.innerHTML = `<div class="balans ${klasse}">
      <span class="ic">${ic}</span>
      <div class="txt">${txt}</div>
      <div style="display:flex;gap:8px;align-items:center">${invoer}</div>
    </div>`;

  document.getElementById("saveBalans").addEventListener("click", async () => {
    const v = parseFloat(document.getElementById("werkBalans").value);
    if (isNaN(v)) { toast("Vul een bedrag in", true); return; }
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ werkelijke_balans: v }) });
    toast("Balans bijgewerkt");
    load();
  });
}

// ---------- Reward-paneel ----------
function longestWinStreak(history) {
  let best = 0, cur = 0;
  history.forEach((h) => { if (h.resultaat > 0) { cur++; best = Math.max(best, cur); } else if (h.resultaat < 0) cur = 0; });
  return best;
}
function renderMilestone(s) {
  const m = s.mijlpaal, k = s.kpi;
  const box = document.getElementById("milestone");
  if (!m || !m.volgende) {
    box.innerHTML = `<div class="row"><span class="lbl-l">Portfolio</span>
      <span class="lbl-r">${eur(k.eindkapitaal)}</span></div>`;
    return;
  }
  box.innerHTML = `
    <div class="row">
      <span class="lbl-l">Onderweg naar je volgende mijlpaal</span>
      <span class="lbl-r">${eur(k.eindkapitaal)} → ${VALUTA} ${m.volgende}
        <span style="color:var(--muted);font-weight:400"> (nog ${eur(m.te_gaan).replace("+","")})</span></span>
    </div>
    <div class="bar"><div class="fill" style="width:${m.voortgang_pct}%"></div></div>`;
}

function renderStreaks(s) {
  const k = s.kpi;
  const items = [
    { n: k.win_streak_huidig, txt: "wins op rij", hot: k.win_streak_huidig >= 2 },
    { n: k.win_streak_langste, txt: "langste win-reeks", hot: false },
    { n: k.discipline_streak_huidig, txt: "valide op rij", hot: k.discipline_streak_huidig >= 2 },
    { n: k.discipline_streak_langste, txt: "langste valide-reeks", hot: false },
  ];
  document.getElementById("streaks").innerHTML = items.map((i) =>
    `<div class="streak ${i.hot ? "hot" : ""}"><b>${i.n}</b> ${i.txt}</div>`).join("");
}

function renderReward(s) {
  const k = s.kpi;
  renderMilestone(s);
  renderStreaks(s);
  const perfect = s.grade_dist.A || 0;
  const groeneDagen = s.per_dag.filter((d) => d.netto > 0).length;
  const streak = longestWinStreak(s.history);

  const stats = [
    { big: perfect, cap: "Perfecte trades (A)", cls: "" },
    { big: k.n_valide, cap: "Valide setups (A+B)", cls: "blue" },
    { big: eur(k.beste_eur), cap: "Beste trade", cls: "" },
    { big: k.n_no_trades, cap: "Bewuste no-trades", cls: "blue" },
    { big: groeneDagen, cap: "Groene dagen", cls: "" },
    { big: k.n_overgeslagen || 0, cap: "Setups overgeslagen", cls: "blue" },
  ];
  document.getElementById("rewardGrid").innerHTML = stats.map((x) => `
    <div class="reward-stat ${x.cls}">
      <div class="cap">${x.cap}</div>
      <div class="big">${x.big}</div>
    </div>`).join("");

  const badges = [
    { txt: "Perfecte setup (A)", on: perfect >= 1 },
    { txt: "Eerste valide setup", on: k.n_valide >= 1 },
    { txt: "Groene dag", on: groeneDagen >= 1 },
    { txt: "Discipline: no-trade", on: k.n_no_trades >= 1 },
    { txt: "Plan gevolgd: setup overgeslagen", on: (k.n_overgeslagen || 0) >= 1 },
    { txt: "Win-streak ×3", on: streak >= 3 },
    { txt: "Gejournald met screenshot", on: (k.n_screenshots || 0) >= 1 },
    { txt: "In de plus", on: k.netto_eur > 0 },
    { txt: "Winrate ≥ 50%", on: k.winrate >= 50 },
  ];
  const behaald = badges.filter((b) => b.on).length;
  document.getElementById("badges").innerHTML =
    `<div class="badge-kop">Behaald · ${behaald} van ${badges.length}</div>` +
    badges.map((b) => `<div class="badge ${b.on ? "on" : ""}">${b.on ? "✓" : "·"} ${b.txt}</div>`).join("");
}

// ---------- Edge: werkt het model? ----------
function rTxt(v) { return (v >= 0 ? "+" : "") + Number(v).toFixed(2) + "R"; }

function renderEdge(e) {
  if (!e) return;

  // Betrouwbaarheid
  const b = e.betrouwbaar;
  document.getElementById("betrouwbaar").innerHTML = `
    <div class="betrouwbaar ${b.niveau === "ruis" ? "ruis" : ""}">
      <span class="ic">${b.niveau === "ruis" ? "⏳" : b.niveau === "indicatie" ? "📊" : "✅"}</span>
      <div>${b.tekst}</div>
    </div>`;

  // Kerncijfers
  const pf = e.profit_factor;
  const dd = e.drawdown;
  const cells = [
    { hero: true, k: "Expectancy per trade", v: rTxt(e.expectancy_r),
      band: e.expectancy_band, sub: `${e.n_trades} trades · kosten inbegrepen` },
    { k: "Profit factor", v: pf === null ? "–" : pf.toFixed(2),
      sub: pf === null ? "nog geen verliezers" : "1,5+ is solide" },
    { k: "Gem. winst", v: rTxt(e.gem_winst_r), sub: "per winnende trade" },
    { k: "Gem. verlies", v: rTxt(e.gem_verlies_r), sub: "per verliezende trade" },
    { k: "Max drawdown", v: eur(-dd.max_eur).replace("+", ""),
      sub: dd.max_pct ? dd.max_pct + "% van de piek" : "geen terugval" },
    { k: "Totaal", v: rTxt(e.totaal_r), sub: "opgeteld resultaat in R" },
  ];
  document.getElementById("edgeBar").innerHTML = cells.map((c) => `
    <div class="edge-cell ${c.hero ? "hero" : ""}">
      <div class="k">${c.k}</div>
      <div class="v mono ${c.v.startsWith("-") || c.v.startsWith("−") ? "neg" : ""}">${c.v}</div>
      ${c.band ? `<span class="band band-${c.band.kleur}">${c.band.label}</span>` : ""}
      <div class="sub2">${c.sub}</div>
    </div>`).join("");

  renderCritEdge(e);
  renderMaeMfe(e);
}

function renderCritEdge(e) {
  const body = document.getElementById("critBody");
  body.innerHTML = e.crit_edge.map((c) => {
    const d = c.delta_r;
    const dCls = d === null ? "" : (d > 0 ? "delta-pos" : (d < 0 ? "delta-neg" : ""));
    const dTxt = d === null ? "–" : rTxt(d);
    return `<tr>
      <td style="text-align:left">${c.num}. ${c.title}${c.critical ? ' <span class="crit-badge-kritisch">kritisch</span>' : ""}</td>
      <td class="mono">${c.met.n}</td>
      <td class="mono">${c.met.n ? c.met.winrate + "%" : "–"}</td>
      <td class="mono">${c.met.n ? rTxt(c.met.expectancy_r) : "–"}</td>
      <td class="mono">${c.zonder.n}</td>
      <td class="mono">${c.zonder.n ? c.zonder.winrate + "%" : "–"}</td>
      <td class="mono">${c.zonder.n ? rTxt(c.zonder.expectancy_r) : "–"}</td>
      <td class="mono ${dCls}">${dTxt}</td>
    </tr>`;
  }).join("");
}

function renderMaeMfe(e) {
  const box = document.getElementById("maemfe");
  const balk = (titel, tel, totaal, kleuren, labels) => {
    if (!totaal) return "";
    const keys = Object.keys(labels);
    const segs = keys.map((k) => {
      const n = tel[k].totaal;
      if (!n) return "";
      const pct = (100 * n / totaal).toFixed(1);
      return `<div class="mm-seg" style="width:${pct}%;background:${kleuren[k]}" title="${labels[k]}: ${n}">${n}</div>`;
    }).join("");
    const legend = keys.map((k) =>
      `<span><i class="mm-key" style="background:${kleuren[k]}"></i>${labels[k]}</span>`).join("");
    return `<div class="mm-rij">
      <div class="mm-kop">${titel}</div>
      <div class="mm-balk">${segs}</div>
      <div class="mm-legend">${legend}</div>
    </div>`;
  };

  let html = "";
  html += balk("Hoe dicht kwam de prijs bij je SL", e.sl_nabijheid, e.n_sl_ingevuld,
    { nooit: C.green, halverwege: C.amber, bijna: C.red },
    { nooit: "nooit dichtbij", halverwege: "halverwege", bijna: "bijna geraakt" });
  html += balk("Hoe liep je TP af", e.tp_verloop, e.n_tp_ingevuld,
    { precies: C.green, liep_door: C.blue, te_vroeg: C.amber },
    { precies: "precies goed", liep_door: "liep nog door", te_vroeg: "te vroeg gesloten" });

  if (!e.n_sl_ingevuld && !e.n_tp_ingevuld) {
    html = `<div class="mm-leeg">Nog niets ingevuld. Bij je volgende trade zie je onder
      "Uitkomst &amp; risico" twee vragen — twee klikken, en hier verschijnt of je stop te krap staat.</div>`;
  }
  html += (e.signalen || []).map((sg) => `<div class="signaal">${sg}</div>`).join("");
  box.innerHTML = html;
}

// Eerlijke duiding onder de portfolio-grafiek.
function renderEquityNote(s) {
  const k = s.kpi, el = document.getElementById("equityNote");
  if (!el) return;
  if (!k.n_trades) { el.textContent = ""; return; }
  const d = k.discipline_edge;                 // valide-only minus echt
  const weinig = k.n_trades < 20;
  let txt;
  if (Math.abs(d) < 0.005) {
    txt = "Je valide setups leveren tot nu toe precies hetzelfde op als al je trades samen.";
  } else if (d > 0) {
    txt = `Had je alléén valide setups genomen, dan stond je nu ${eur(k.eindkapitaal_valide)} — dat is ${eur(d)} méér. Dat is wat je filter je oplevert.`;
  } else {
    txt = `Je C-trades vielen tot nu toe goed uit: alleen valide setups zou ${eur(k.eindkapitaal_valide)} zijn, ${eur(Math.abs(d)).replace("+","")} minder. Geluk, geen edge — de checklist blijft leidend.`;
  }
  el.innerHTML = txt + (weinig ? ` <span style="opacity:.7">(nog ${k.n_trades} trades — te weinig om conclusies aan te hangen.)</span>` : "");
}

// Verticale streep in de equity-curve op de dag dat je je regels wijzigde (fase 11.4).
function regelLijnPlugin(labels, wijzigingen) {
  return {
    id: "regellijnen",
    afterDatasetsDraw(chart) {
      if (!wijzigingen || !wijzigingen.length) return;
      const { ctx, chartArea, scales } = chart;
      if (!chartArea) return;
      wijzigingen.forEach((w) => {
        // labels zien eruit als "2026-09-04 #1"; match op de datum ervoor.
        let i = labels.findIndex((l) => String(l).startsWith(w.datum));
        if (i < 0) i = labels.findIndex((l) => String(l).slice(0, 10) >= w.datum);
        if (i < 0) return;
        const x = scales.x.getPixelForValue(i);
        ctx.save();
        ctx.strokeStyle = C.purple;
        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = C.purple;
        ctx.font = "10px 'Segoe UI', system-ui, sans-serif";
        // dicht bij de rechterrand? Dan het label links van de streep.
        const rechts = x > chartArea.right - 130;
        ctx.textAlign = rechts ? "right" : "left";
        ctx.fillText("§ " + w.titel.slice(0, 26), x + (rechts ? -5 : 5), chartArea.top + 11);
        ctx.restore();
      });
    },
  };
}

// ---------- Grafieken ----------
const baseScales = (opts = {}) => ({
  x: { grid: { color: C.grid, display: opts.xgrid !== false }, ticks: { maxRotation: 0, autoSkip: true } },
  y: { grid: { color: C.grid }, ...opts.y },
});

function grafiekenVandaag(s) {
  const eq = s.equity;
  const regelLijn = regelLijnPlugin(eq.labels, s.regelwijzigingen || []);
  const rpt = s.resultaat_per_trade;
  const pd = s.per_dag;
  // Spaarverloop (equity €)
  mkChart("cEquity", {
    type: "line",
    data: { labels: eq.labels, datasets: [
      {
        label: "Mijn portfolio", data: eq.eur, borderColor: C.blue, borderWidth: 2,
        pointRadius: 2.5, pointBackgroundColor: C.blue, tension: 0.2, fill: true,
        backgroundColor: (ctx) => {
          const { chart } = ctx; const { ctx: c, chartArea } = chart;
          if (!chartArea) return mix(C.blue, 12);
          const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          g.addColorStop(0, mix(C.blue, 22)); g.addColorStop(1, mix(C.blue, 1));
          return g;
        },
      },
      {
        label: "Alleen valide setups (A/B)", data: eq.valide, borderColor: C.green,
        borderWidth: 1.6, borderDash: [5, 4], pointRadius: 2, pointBackgroundColor: C.green,
        tension: 0.25, fill: false,
      },
    ] },
    options: { maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom" },
        tooltip: { callbacks: { label: (i) => i.dataset.label + ": " + eur(i.parsed.y) } } },
      scales: baseScales() },
    plugins: [regelLijn],
  });
mkChart("cPerDag", {
    type: "bar",
    data: { labels: pd.map((d) => d.datum), datasets: [{
      label: "Netto", data: pd.map((d) => d.netto),
      backgroundColor: signColors(pd.map((d) => d.netto), C.green, C.red), borderRadius: 4,
    }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false },
      tooltip: { callbacks: { label: (i) => "Netto: " + eur(i.parsed.y) } } },
      scales: baseScales() },
  });
mkChart("cPerTrade", {
    type: "bar",
    data: { labels: rpt.map((r) => r.label), datasets: [{
      label: "Netto", data: rpt.map((r) => r.netto),
      backgroundColor: signColors(rpt.map((r) => r.netto), C.green, C.red),
      borderRadius: 4,
    }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false },
      tooltip: { callbacks: { label: (i) => "Netto: " + eur(i.parsed.y) } } },
      scales: baseScales() },
  });
}

function grafiekenEdge(s) {
  const eq = s.equity;
  // Equity in R
  mkChart("cR", {
    type: "line",
    data: { labels: eq.labels, datasets: [{
      label: "R", data: eq.r, borderColor: C.plum, borderWidth: 1.6,
      pointRadius: 2.5, pointBackgroundColor: C.purple, tension: 0.25, fill: false,
    }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false },
      tooltip: { callbacks: { label: (i) => i.parsed.y + " R" } } },
      scales: baseScales() },
  });
  // Kosten cumulatief
  mkChart("cKosten", {
    type: "line",
    data: { labels: eq.labels, datasets: [{
      label: "Kosten", data: eq.kosten_cum, borderColor: C.amber, borderWidth: 2,
      pointRadius: 2, tension: 0.2, fill: true, backgroundColor: mix(C.amber, 12),
    }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false },
      tooltip: { callbacks: { label: (i) => "Kosten: " + eur(i.parsed.y) } } },
      scales: baseScales() },
  });
}

function grafiekenDiscipline(s) {
  const ws = s.winrate_split;
  const gd = s.grade_dist;
mkChart("cWinrate", {
    type: "bar",
    data: { labels: ["Valide (A+B)", "C (geen trade)"], datasets: [{
      label: "Winrate", data: [ws.valide, ws.c],
      backgroundColor: [C.green, C.red], borderRadius: 6,
    }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false },
      tooltip: { callbacks: { label: (i) => i.parsed.y + "% winrate" } } },
      scales: { x: { grid: { display: false } }, y: { grid: { color: C.grid }, min: 0, max: 100, ticks: { callback: (v) => v + "%" } } } },
  });
mkChart("cGrades", {
    type: "doughnut",
    data: { labels: ["A — perfect", "B — valide", "C — geen trade"], datasets: [{
      data: [gd.A, gd.B, gd.C], backgroundColor: [C.green, C.blue, C.red],
      borderColor: getComputedStyle(document.documentElement).getPropertyValue("--panel").trim() || "#211926", borderWidth: 3,
    }] },
    options: { maintainAspectRatio: false, cutout: "62%",
      plugins: { legend: { position: "bottom" } } },
  });
}

function grafiekenPatronen(s) {
  const f = s.foutcodes;
  const cq = s.crit_quality;
mkChart("cFouten", {
    type: "bar",
    data: { labels: f.map((x) => x.code), datasets: [{
      label: "Aantal", data: f.map((x) => x.n), backgroundColor: C.blue, borderRadius: 4,
    }] },
    options: { maintainAspectRatio: false, indexAxis: "y",
      plugins: { legend: { display: false },
        tooltip: { callbacks: { title: (i) => f[i[0].dataIndex].code + " — " + f[i[0].dataIndex].desc,
          label: (i) => i.parsed.x + "×" } } },
      scales: { x: { grid: { color: C.grid }, ticks: { precision: 0 } }, y: { grid: { display: false } } } },
  });
mkChart("cCrits", {
    type: "bar",
    data: { labels: cq.map((c) => c.num + (c.critical ? "★" : "")), datasets: [
      { label: "✓", data: cq.map((c) => c.yes), backgroundColor: C.green, borderRadius: 3, stack: "s" },
      { label: "?", data: cq.map((c) => c.maybe), backgroundColor: C.amber, borderRadius: 3, stack: "s" },
      { label: "✗", data: cq.map((c) => c.no), backgroundColor: C.red, borderRadius: 3, stack: "s" },
    ] },
    options: { maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" },
        tooltip: { callbacks: { title: (i) => cq[i[0].dataIndex].title } } },
      scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, grid: { color: C.grid }, ticks: { precision: 0 } } } },
  });
}

// ---------- Trade-historie ----------
function renderHistory(s) {
  const body = document.getElementById("histBody");
  if (!s.history.length) {
    body.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:24px">Geen trades in deze periode.</td></tr>`;
    return;
  }
  body.innerHTML = s.history.map((h) => `
    <tr onclick="location.href='/trade?id=${h.id}'">
      <td>${h.datum}</td>
      <td class="mono">${h.tijd || "–"}</td>
      <td>${h.instrument}</td>
      <td>${h.richting ? `<span class="dir-pill ${h.richting}">${h.richting === "long" ? "▲ long" : "▼ short"}</span>` : "–"}</td>
      <td><span class="pill grade-${h.grade}">${h.grade}</span></td>
      <td class="mono">${h.rr != null ? h.rr : "–"}</td>
      <td class="mono ${cls(h.resultaat)}">${eur(h.resultaat)}</td>
      <td class="mono ${cls(h.netto)}">${eur(h.netto)}</td>
      <td>${(h.foutcodes || "").split(",").filter(Boolean).map((c) => `<span class="tag fout">${c}</span>`).join(" ") || "–"}</td>
    </tr>`).join("");
}

boot();


// ---------- fase 8: bronkeuze ----------
function renderBron(s) {
  const box = document.getElementById("bronNote");
  const b = s.bron || {};
  if (!box) return;
  if (b.gekozen === "live") {
    box.innerHTML = b.n_backtest
      ? `<div class="bron-note">Je hebt <b>${b.n_backtest}</b> backtest-trade(s) die hier niet in meetellen.
           Zet de schakelaar op <b>Alles</b> om ze mee te nemen in je edge-analyse — je portfolio in euro's blijft live-only.</div>`
      : "";
    return;
  }
  const tekst = b.gekozen === "backtest"
    ? `<b>Backtest-modus.</b> Je kijkt naar ${b.n_backtest} gebacktestte setup(s). Geen echt geld — dit is volume om sneller richting een betrouwbaar oordeel te komen.`
    : `<b>Live + backtest samen.</b> ${b.n_live} live en ${b.n_backtest} backtest. Goed voor de checklist-statistiek; de eurobedragen kloppen zo niet met je broker.`;
  box.innerHTML = `<div class="bron-note waarschuwing">${tekst}</div>`;
}

function renderDubbels(s) {
  const box = document.getElementById("dubbels");
  if (!box) return;
  const d = s.dubbels || [];
  if (!d.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="dubbel-waarschuwing">
      <b>⚠ Mogelijk dubbel ingevoerd</b>
      <p>${d.length} paar trades lijkt op elkaar. Ik verwijder nooit zelf iets — kijk even na:</p>
      <ul>${d.map((x) => `<li>${x.datum}${x.tijd ? " " + x.tijd : ""} — ${x.reden}
        (<a href="/trade?id=${x.ids[0]}">#${x.ids[0]}</a> en <a href="/trade?id=${x.ids[1]}">#${x.ids[1]}</a>)</li>`).join("")}</ul>
    </div>`;
}

// ---------- fase 12.1 + 8.2: back-up en export ----------
function renderDataBar(s) {
  const box = document.getElementById("dataBar");
  if (!box) return;
  const b = s.backup || {};
  const leeftijd = b.uur_geleden === null || b.uur_geleden === undefined
    ? "nog geen"
    : b.uur_geleden < 1 ? "zojuist" : `${b.uur_geleden} uur geleden`;
  box.innerHTML = `
    <div class="data-cel">
      <div class="k">Back-ups</div>
      <div class="val">${b.aantal || 0}</div>
      <div class="sub">laatste: ${leeftijd}</div>
    </div>
    <div class="data-acties">
      <button class="btn" id="backupNu">Nu back-uppen</button>
      <a class="btn btn-primary" href="/export">PDF-rapport</a>
      <p class="hint" style="margin:8px 0 0">Bij elke start maakt de journal automatisch een back-up
        (30 dagen bewaard, in de map <code>backups/</code>).</p>
    </div>`;
  const knop = document.getElementById("backupNu");
  if (knop) knop.addEventListener("click", async () => {
    knop.disabled = true;
    try {
      const r = await api("/api/backup", { method: "POST" });
      toast(r.gemaakt ? "Back-up gemaakt: " + r.bestand : "Back-up mislukt", !r.gemaakt);
      load();
    } catch (e) { toast("Back-up mislukt: " + e.message, true); }
    knop.disabled = false;
  });
}


// ---------- Fase 11.1: regel-adherentie ----------
function renderAdherentie(a) {
  if (!a) return;
  if (!a.n) {
    document.getElementById("adhScore").innerHTML =
      leeg(10, 0, "Zodra je trades logt, staat hier hoe vaak je je eigen regels volgde.");
    document.getElementById("adhBanden").innerHTML = "";
    document.getElementById("adhRedenen").innerHTML = "";
    document.getElementById("adhVergelijk").innerHTML = "";
    return;
  }
  const kleur = { goed: "pos", "let-op": "amber", slecht: "neg" }[a.band.kleur] || "";
  document.getElementById("adhScore").innerHTML = `
    <div class="adh-score">
      <div class="adh-pct ${kleur}">${a.pct}<span>%</span></div>
      <div class="adh-tekst">
        <div class="adh-band ${kleur}">${a.band.label}</div>
        <div class="adh-sub">${a.n_gevolgd} van ${a.n} trades volgden je regels</div>
      </div>
    </div>
    <p class="adh-advies">${a.band.advies}</p>`;

  // bandschaal: 0-60-75-85-100
  const punten = [[0, 60], [60, 75], [75, 85], [85, 100]];
  const namen = ["systeem klopt niet", "op weg", "sterk", "elite"];
  const pos = Math.min(100, Math.max(0, a.pct));
  document.getElementById("adhBanden").innerHTML = `
    <div class="adh-wrap">
      <div class="adh-wijzer" style="left:${pos}%"><b>${a.pct}%</b><i></i></div>
      <div class="adh-schaal">
        ${punten.map((p, i) => {
          const actief = a.pct >= p[0] && (i === 3 ? true : a.pct < p[1]);
          return `<div class="adh-vak s${i}${actief ? " actief" : ""}" style="flex:${p[1] - p[0]}">
            <span>${namen[i]}</span></div>`;
        }).join("")}
      </div>
      <div class="adh-ticks">
        ${[0, 60, 75, 85, 100].map((v) =>
          `<span style="left:${v}%">${v}%</span>`).join("")}
      </div>
    </div>`;

  const r = a.redenen || [];
  document.getElementById("adhRedenen").innerHTML = r.length
    ? `<div class="adh-redenen"><div class="k">Waarom je ze brak</div>
        ${r.map((x) => `<div class="adh-rij"><span>${x.reden}</span><b>${x.aantal}×</b></div>`).join("")}</div>`
    : `<div class="adh-redenen"><div class="k">Geen enkele overtreding. Netjes.</div></div>`;

  const g = a.gevolgd, b = a.gebroken;
  const rij = (label, gv, gb, fmt) => `
    <tr><td style="text-align:left">${label}</td>
      <td class="pos">${gv === null || gv === undefined ? "–" : fmt(gv)}</td>
      <td class="${b.n ? "neg" : ""}">${gb === null || gb === undefined ? "–" : fmt(gb)}</td></tr>`;
  const nr = (x) => (x >= 0 ? "+" : "") + Number(x).toFixed(2) + "R";
  document.getElementById("adhVergelijk").innerHTML = `
    <div class="mt-table-wrap">
      <table class="mt">
        <thead><tr><th style="text-align:left"></th><th>Regels gevolgd</th><th>Regels gebroken</th></tr></thead>
        <tbody>
          ${rij("Trades", g.n, b.n, (x) => x)}
          ${rij("Winrate", g.winrate, b.winrate, (x) => x + "%")}
          ${rij("Expectancy", g.expectancy_r, b.expectancy_r, nr)}
          ${rij("Profit factor", g.profit_factor, b.profit_factor, (x) => Number(x).toFixed(2))}
          ${rij("Netto", g.netto_eur, b.netto_eur, (x) => eur(x))}
        </tbody>
      </table>
    </div>
    ${a.n_gebroken === 0
      ? `<p class="hint" style="margin-top:10px">Je hebt nog geen trade waarbij je je regels brak — dus valt er nog niets te vergelijken. Dat is een goed probleem.</p>`
      : `<p class="hint" style="margin-top:10px">Verschil in expectancy: <b class="${a.verschil_expectancy >= 0 ? "pos" : "neg"}">${nr(a.verschil_expectancy)}</b> per trade in het voordeel van je regels volgen.</p>`}
    ${a.genoeg_data ? "" : `<p class="hint" style="margin-top:6px">Onder de tien trades zegt deze vergelijking nog niets.</p>`}`;
}

// ---------- Fase 11.2: gemiste setups ----------
function renderGemist(m, a) {
  const box = document.getElementById("gemist");
  if (!box || !m) return;
  if (!m.n_overgeslagen) {
    box.innerHTML = `<div class="empty">Nog geen overgeslagen setups. Zodra je een plan maakt en
      besluit weg te blijven, komt hier het onderscheid tussen discipline en aarzeling.</div>`;
    return;
  }
  const kosten = m.geschat_r > 0
    ? `<p class="hint" style="margin-top:12px">Geschatte kosten van aarzelen:
        <b class="neg">−${m.geschat_r.toFixed(2)}R</b> — dat is ${m.n_gemist} gemiste valide setup(s)
        × je expectancy op trades waarbij je je regels volgde (${(a.gevolgd.expectancy_r >= 0 ? "+" : "") + a.gevolgd.expectancy_r.toFixed(2)}R).
        Een schatting, geen feit: we weten niet wat die trades hadden gedaan.</p>`
    : "";
  box.innerHTML = `
    <div class="gemist-grid">
      <div class="gemist-cel goed">
        <div class="val">${m.n_discipline}</div>
        <div class="k">🛡 discipline-winst</div>
        <div class="sub">terecht weggebleven</div>
      </div>
      <div class="gemist-cel ${m.n_gemist ? "slecht" : ""}">
        <div class="val">${m.n_gemist}</div>
        <div class="k">gemiste valide setups</div>
        <div class="sub">A of B die je liet lopen</div>
      </div>
      <div class="gemist-redenen">
        ${m.per_reden.map((r) => `<div class="adh-rij"><span>${r.label}</span><b>${r.aantal}×</b></div>`).join("")}
      </div>
    </div>
    ${m.gemiste.length ? `<div class="mt-table-wrap" style="margin-top:14px">
      <table class="mt"><thead><tr><th>Datum</th><th>Grade</th><th>RR</th><th style="text-align:left">Reden</th><th></th></tr></thead>
      <tbody>${m.gemiste.map((x) => `<tr>
        <td>${x.datum}</td><td><span class="grade grade-${x.grade} mini">${x.grade}</span></td>
        <td>${x.rr ? Number(x.rr).toFixed(2) : "–"}</td>
        <td style="text-align:left">${x.reden || "geen reden ingevuld"}</td>
        <td><a href="/trade?id=${x.id}">bekijk</a></td></tr>`).join("")}</tbody></table>
    </div>` : ""}
    ${kosten}`;
}


// ---------- Fase 11.3: hoe zeker is zeker ----------
// Fase 16.3 -- een paneel dat nog niets kan zeggen, zegt wát het nodig heeft.
function leeg(vanaf, nu, wat) {
  return `<div class="empty wachtend">
    <b>Nog niet te zeggen.</b>
    <span>${wat}</span>
    <span class="tel">${nu} van de ${vanaf} trades</span>
    <div class="balkje"><i style="width:${Math.min(100, Math.round(100 * nu / vanaf))}%"></i></div>
  </div>`;
}

function renderSimulatie(sim) {
  const wbox = document.getElementById("wilson");
  const mbox = document.getElementById("monte");
  if (!sim || !wbox) return;
  if (sim.n < 2) {
    wbox.innerHTML = leeg(20, sim.n, "Een betrouwbaarheidsinterval op één trade is geen interval.");
    if (mbox) mbox.innerHTML = leeg(20, sim.n, "De simulatie trekt uit je eigen trades — daar zijn er minstens twee voor nodig.");
    return;
  }

  const w = sim.winrate;
  wbox.innerHTML = `
    <div class="wil-getal"><b>${w.punt}%</b><span>gemeten winrate over ${sim.n} trades</span></div>
    <div class="wil-baan">
      <div class="wil-band" style="left:${w.laag}%;width:${Math.max(w.hoog - w.laag, 1)}%"></div>
      <div class="wil-punt" style="left:${w.punt}%"></div>
      <div class="wil-50"></div>
    </div>
    <div class="wil-ticks"><span style="left:0%">0%</span><span style="left:50%">50%</span><span style="left:100%">100%</span></div>
    <div class="wil-uitleg">
      <b>${w.laag}% – ${w.hoog}%</b> is waar je échte winrate met 95% zekerheid ligt.
      De band is nu <b>${w.breedte} procentpunt</b> breed.
    </div>
    <p class="hint" style="margin-top:10px">${sim.oordeel}</p>`;

  const mc = sim.monte_carlo;
  if (!mc) {
    mbox.innerHTML = `<div class="empty">Vanaf twee trades kan de simulatie draaien.</div>`;
    return;
  }
  const z = mc.zelfde, v = mc.vooruit;
  const span = Math.max(Math.abs(z.p5), Math.abs(z.p95), Math.abs(mc.werkelijk_r)) * 1.15 || 1;
  const pos = (x) => 50 + (x / span) * 50;
  const nr = (x) => (x >= 0 ? "+" : "") + Number(x).toFixed(2) + "R";

  mbox.innerHTML = `
    <div class="mc-blok">
      <div class="mc-kop">Dezelfde ${mc.n} trades, opnieuw getrokken</div>
      <div class="mc-baan">
        <div class="mc-nul" style="left:50%"></div>
        <div class="mc-band breed" style="left:${pos(z.p5)}%;width:${pos(z.p95) - pos(z.p5)}%"></div>
        <div class="mc-band smal" style="left:${pos(z.p25)}%;width:${pos(z.p75) - pos(z.p25)}%"></div>
        <div class="mc-mediaan" style="left:${pos(z.p50)}%"></div>
        <div class="mc-echt" style="left:${pos(mc.werkelijk_r)}%"><i></i><b>jij</b></div>
      </div>
      <div class="mc-rijen">
        <div><span>slechtste 5%</span><b class="${z.p5 < 0 ? "neg" : ""}">${nr(z.p5)}</b></div>
        <div><span>mediaan</span><b>${nr(z.p50)}</b></div>
        <div><span>beste 5%</span><b class="pos">${nr(z.p95)}</b></div>
        <div><span>kans op verlies</span><b class="${z.kans_negatief > 30 ? "neg" : ""}">${z.kans_negatief}%</b></div>
      </div>
    </div>
    <div class="mc-blok">
      <div class="mc-kop">Na nog ${mc.n_vooruit} trades, als je edge blijft wat hij lijkt</div>
      <div class="mc-rijen">
        <div><span>slechtste 5%</span><b class="${v.p5 < 0 ? "neg" : ""}">${nr(v.p5)}</b></div>
        <div><span>mediaan</span><b>${nr(v.p50)}</b></div>
        <div><span>beste 5%</span><b class="pos">${nr(v.p95)}</b></div>
        <div><span>kans op verlies</span><b class="${v.kans_negatief > 30 ? "neg" : ""}">${v.kans_negatief}%</b></div>
      </div>
      <p class="hint" style="margin-top:8px">Verwachte grootste drawdown onderweg: mediaan
        <b>${mc.drawdown.p50.toFixed(2)}R</b>, in 5% van de gevallen <b>${mc.drawdown.p95.toFixed(2)}R</b> of erger.
        Daar moet je doorheen kunnen zitten.</p>
      ${sim.genoeg ? "" : `<p class="hint waarschuwing" style="margin-top:8px">
        <b>Lees dit als je naar die vooruitblik kijkt.</b> De simulatie trekt uit jouw ${mc.n} trades,
        en die zijn tot nu toe goed gevallen. Ze projecteert dus je geluk mee. Zolang je onder de
        twintig trades zit is dit geen voorspelling maar een rekensom over een te kleine steekproef.</p>`}
    </div>`;
}

// ---------- Fase 11.4: regel-changelog ----------
function renderRegelFilter(s) {
  const knop = document.querySelector('#periodTabs button[data-p="regel"]');
  if (!knop) return;
  const lijst = s.regelwijzigingen || [];
  knop.style.display = lijst.length ? "" : "none";
  if (lijst.length) knop.title = "Alleen trades sinds: " + lijst[0].datum + " — " + lijst[0].titel;
  const note = document.getElementById("regelNote");
  if (note) {
    note.innerHTML = (s.sinds_regel && lijst.length)
      ? `<div class="bron-note"><b>Sinds je laatste regelwijziging</b> —
          ${lijst[0].datum}: ${lijst[0].titel}. Alles op deze pagina telt alleen trades vanaf die dag.</div>`
      : "";
  }
}


// ---------- Fase 10.2–10.4: wanneer ben ik goed? ----------
const rLabel = (x) => (x >= 0 ? "+" : "") + Number(x).toFixed(2) + "R";

// Bakken met te weinig trades tekenen we doorzichtig: zichtbaar, maar niet als feit.
function bakKleuren(cellen) {
  return cellen.map((c) => {
    const basis = c.expectancy_r >= 0 ? C.green : C.red;
    return c.genoeg ? basis : (c.expectancy_r >= 0 ? mix(C.green, 42) : mix(C.red, 42));
  });
}

function bakChart(id, cellen, titel) {
  mkChart(id, {
    type: "bar",
    data: { labels: cellen.map((c) => c.naam), datasets: [{
      label: "Expectancy (R)", data: cellen.map((c) => c.expectancy_r),
      backgroundColor: bakKleuren(cellen), borderRadius: 4, maxBarThickness: 56,
    }] },
    options: { maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: {
          label: (i) => rLabel(i.parsed.y) + " per trade",
          afterLabel: (i) => {
            const c = cellen[i.dataIndex];
            return `${c.n} trade(s) · ${c.winrate}% winrate · ${eur(c.netto_eur)}` +
              (c.genoeg ? "" : "\nte weinig data — nog geen conclusie");
          },
        } } },
      scales: baseScales({ y: { title: { display: true, text: titel } } }) },
  });
}

// De discipline-meter hoort bij de laag Discipline, de rest bij Patronen —
// dus twee functies in plaats van één.
function renderDisciplineMeter(s) {
  const d = s.discipline;
  const box = document.getElementById("discTrend");
  if (!d || !box) return;
  const reeks = d.reeks || [];
  box.innerHTML = `
    <div class="disc-kop">
      <div class="disc-score ${d.gemiddeld >= 80 ? "pos" : d.gemiddeld >= 60 ? "amber" : "neg"}">
        ${d.gemiddeld}<span>/100</span></div>
      <div class="disc-tekst">${d.trend}</div>
    </div>`;
  mkChart("cDiscipline", {
    data: { labels: reeks.map((x) => x.datum), datasets: [
      { type: "bar", label: "Discipline", data: reeks.map((x) => x.score), yAxisID: "y",
        backgroundColor: reeks.map((x) => x.score >= 80 ? mix(C.green, 55)
          : x.score >= 60 ? mix(C.amber, 55) : mix(C.red, 55)),
        borderRadius: 4, maxBarThickness: 44 },
      { type: "line", label: "Netto die dag (€)", data: reeks.map((x) => x.netto_eur), yAxisID: "y1",
        borderColor: C.blue, borderWidth: 2, pointRadius: 3, pointBackgroundColor: C.blue, tension: 0.25 },
    ] },
    options: { maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom" },
        tooltip: { callbacks: { afterBody: (items) => {
          const x = reeks[items[0].dataIndex];
          return x.redenen.length ? "Aftrek: " + x.redenen.join(", ")
            : (x.skips ? `${x.skips} setup(s) bewust overgeslagen — bonuspunten` : "Niets op aan te merken.");
        } } } },
      scales: {
        x: { grid: { color: C.grid } },
        y: { position: "left", min: 0, max: 100, grid: { color: C.grid },
             title: { display: true, text: "discipline" } },
        y1: { position: "right", grid: { drawOnChartArea: false },
              title: { display: true, text: "netto €" } },
      } },
  });
}

function renderPatronen(s) {
  const t = s.timing, k = s.kalibratie;
  if (!t || !k) return;
  // 10.2 — kwartier en weekdag
  bakChart("cKwartier", t.kwartieren, "R per trade");
  document.getElementById("kwartierTabel").innerHTML = `
    <div class="bak-rijen">
      ${t.kwartieren.map((c) => `<div class="bak${c.n ? "" : " leeg"}">
        <span class="bn">min ${c.naam}</span>
        <b class="${c.expectancy_r >= 0 ? "pos" : "neg"}">${c.n ? rLabel(c.expectancy_r) : "–"}</b>
        <span class="bs">${c.n} trade${c.n === 1 ? "" : "s"}</span>
      </div>`).join("")}
    </div>
    ${t.conclusie ? `<p class="hint" style="margin-top:10px">${t.conclusie}</p>` : ""}
    ${t.zonder_tijd ? `<p class="hint" style="margin-top:6px">${t.zonder_tijd} trade(s) zonder entry-tijd tellen hier niet mee.</p>` : ""}`;

  bakChart("cWeekdag", t.weekdagen, "R per trade");

  // 10.3 — zekerheid en emotie
  if (k.niveaus.length) {
    bakChart("cZekerheid", k.niveaus.map((c) => ({ ...c, naam: "zekerheid " + c.naam })), "R per trade");
  } else {
    const wrap = document.getElementById("cZekerheid").closest(".chart-wrap");
    if (wrap) wrap.innerHTML = `<div class="empty wachtend"><b>Nog geen zekerheid ingevuld.</b>
      <span>Bij je entry staat "Hoe zeker was je vooraf?" met 1 tot 5. Twee seconden werk,
      en vanaf een stuk of twintig trades weet je of je onderbuik gekalibreerd is.</span></div>`;
  }
  document.getElementById("kalOordeel").innerHTML =
    `<p class="hint" style="margin-top:10px">${k.oordeel}</p>`;

  if (k.emoties.length) {
    bakChart("cEmotie", k.emoties.slice(0, 8), "R per trade");
  } else {
    const wrap = document.getElementById("cEmotie").closest(".chart-wrap");
    if (wrap) wrap.innerHTML = `<div class="empty wachtend"><b>Nog geen emotie-chips aangeklikt.</b>
      <span>Klik er één aan bij je volgende trade — onderin het formulier bij Reflectie.
      Vanaf een stuk of tien trades zie je hier welke mentale staat je geld kost.</span></div>`;
  }

  renderTags(s.tags);
}

function renderTags(tg) {
  const box = document.getElementById("tagPaneel");
  if (!box) return;
  if (!tg || !tg.tags.length) {
    box.innerHTML = `<div class="empty">Nog geen tags gebruikt. Voeg er een toe bij een trade
      (onderin het formulier) — bijvoorbeeld "sweep van high" of "na nieuws" — en je ziet hier
      meteen wat elke variant oplevert.</div>`;
    return;
  }
  box.innerHTML = `<div class="mt-table-wrap">
    <table class="mt"><thead><tr>
      <th style="text-align:left">Tag</th><th>Trades</th><th>Winrate</th><th>Expectancy</th><th>Netto</th>
    </tr></thead><tbody>
      ${tg.tags.map((t) => `<tr class="${t.betrouwbaar ? "" : "zwak"}">
        <td style="text-align:left">${t.tag}</td><td>${t.n}</td><td>${t.winrate}%</td>
        <td class="${t.expectancy_r >= 0 ? "pos" : "neg"}">${rLabel(t.expectancy_r)}</td>
        <td>${eur(t.netto_eur)}</td></tr>`).join("")}
    </tbody></table></div>
    <p class="hint" style="margin-top:8px">Grijs = minder dan ${tg.min_n} trades met die tag —
      te weinig om iets te betekenen. ${tg.n_getagd} van je trades heeft een tag.</p>`;
}


/* =====================================================================
   Ronde 2 -- SL-plaatsing t.o.v. de sweep.

   Belangrijk in de toon: dit is SL-PLAATSINGSDATA, geen gemiste winst.
   "SL geraakt, daarna TP" als gemiste winst tonen is een uitnodiging om de
   stop structureel te verruimen, en dat is meestal de verkeerde les -- het
   echte probleem zit vaker in de setup-kwaliteit of in waar de stop stond
   ten opzichte van de sweep dan in de breedte van de stop.
   ===================================================================== */
let simSl = null;          // stand van de schuifregelaar, null = nog niet gezet

function renderSweep(sw) {
  const dek = document.getElementById("sweepDekking");
  const hist = document.getElementById("overshootHist");
  const sim = document.getElementById("slSimulator");
  const binnen = document.getElementById("binnenSweep");
  if (!hist || !sim) return;

  if (!sw || !sw.dekking || sw.dekking.gemeten === 0) {
    const n = sw && sw.dekking ? sw.dekking.totaal : 0;
    if (dek) dek.innerHTML = "";
    hist.innerHTML = leeg(5, 0,
      "Vul bij je trades de overshoot en de SL-afstand in points in — ook bij je winnaars.");
    sim.innerHTML = leeg(5, 0,
      "Zonder gemeten sweeps valt er niets door te rekenen. Twee velden per trade is genoeg.");
    if (binnen) binnen.innerHTML = "";
    return;
  }

  // Dekking eerst: een scheve steekproef is hier de grootste valkuil.
  if (dek) {
    dek.innerHTML = sw.dekking.waarschuwing
      ? `<div class="dekking-waarschuwing"><strong>Let op je steekproef.</strong>
         ${sw.dekking.waarschuwing}
         Nu gemeten: ${sw.dekking.gemeten} van ${sw.dekking.totaal} trades,
         waarvan ${sw.dekking.winnaars_gemeten} van je ${sw.dekking.winnaars_totaal} winnaars.</div>`
      : "";
  }

  const gekozen = sw.gekozen || sw.nu;
  if (simSl === null) simSl = sw.gekozen_sl;

  // ---- histogram met de SL-lijn erin ----
  const h = sw.histogram;
  const maxN = Math.max(1, ...h.bins.map((b) => b.n));
  const grens = simSl;
  const balken = h.bins.map((b) => {
    const buiten = b.van >= grens;      // deze sweeps nemen je stop mee
    const hoogte = Math.round((b.n / maxN) * 100);
    return `<div class="hist-bar ${buiten ? "buiten" : ""}">
      <b>${b.n || ""}</b><i style="height:${b.n ? Math.max(hoogte, 4) : 0}%"></i></div>`;
  }).join("");
  const labels = h.bins.map((b) => `<span>${b.label}</span>`).join("");
  const pos = Math.min(100, (grens / Math.max(h.max, grens)) * 100);
  hist.innerHTML = `
    <div class="hist">${balken}
      <div class="hist-lijn" style="left:${pos}%" data-label="SL ${grens.toFixed(1)}"></div>
    </div>
    <div class="hist-labels">${labels}</div>
    <p class="hint" style="margin-top:8px">
      Mediane sweep ${h.mediaan} points, 80% blijft onder ${h.p80}, grootste ${h.max}.
      ${h.n} gemeten ${h.n === 1 ? "trade" : "trades"}.</p>`;

  // ---- schuifregelaar ----
  sim.innerHTML = `
    <div class="sim-kop">
      <span class="sim-waarde">${simSl.toFixed(1)}</span>
      <span class="sim-eenheid">points SL-afstand (= ${(simSl * 0.1).toFixed(2)} in prijs)</span>
    </div>
    <input type="range" class="sim-slider" id="slSlider"
           min="2" max="8" step="0.5" value="${simSl}" />
    <div class="sim-schaal"><span>2,0</span><span>5,0</span><span>8,0</span></div>
    ${gekozen && gekozen.n ? `
    <div class="sim-cijfers">
      <div class="sim-cel goed"><span class="lbl">Sweep overleefd</span>
        <span class="v">${gekozen.overleefd}/${gekozen.n}</span></div>
      <div class="sim-cel"><span class="lbl">Winrate</span>
        <span class="v">${gekozen.winrate}%</span></div>
      <div class="sim-cel"><span class="lbl">Gem. RR</span>
        <span class="v">${gekozen.rr_gemiddeld ?? "–"}</span></div>
      <div class="sim-cel ${gekozen.rr_onder_1 ? "let" : ""}"><span class="lbl">RR onder 1</span>
        <span class="v">${gekozen.rr_onder_1}</span></div>
    </div>
    <p class="hint" style="margin-top:10px">
      ${sw.huidige_sl ? `Je gebruikt nu mediaan ${sw.huidige_sl} points. ` : ""}
      ${gekozen.veranderd
        ? `Bij ${simSl.toFixed(1)} points ${gekozen.veranderd === 1 ? "zou 1 trade" : `zouden ${gekozen.veranderd} trades`} anders zijn afgelopen.`
        : "Bij deze afstand verandert er niets aan je uitkomsten."}
      ${gekozen.rr_onder_1
        ? ` Let op: bij ${gekozen.rr_onder_1} van de ${gekozen.n} zakt de RR dan onder 1 — dat is je harde vloer.`
        : " De RR blijft bij al je trades op of boven 1."}
      ${!gekozen.genoeg ? ` Nog ${sw.min_n - gekozen.n} metingen te gaan voordat dit echt iets zegt.` : ""}
    </p>` : ""}
    <div class="kader-noot">${sw.kader}</div>`;

  const slider = document.getElementById("slSlider");
  if (slider) {
    slider.addEventListener("input", (e) => {
      simSl = parseFloat(e.target.value);
      const w = sim.querySelector(".sim-waarde");
      const u = sim.querySelector(".sim-eenheid");
      if (w) w.textContent = simSl.toFixed(1);
      if (u) u.textContent = `points SL-afstand (= ${(simSl * 0.1).toFixed(2)} in prijs)`;
    });
    slider.addEventListener("change", () => { geladen.delete("edge"); load(); });
  }

  // ---- de trades waarvan de stop binnen de sweep lag ----
  if (binnen) {
    if (!sw.binnen_de_sweep.length) {
      binnen.innerHTML = "";
    } else {
      const rijen = sw.binnen_de_sweep.map((b) => `<tr>
        <td>${b.datum}</td>
        <td class="num">${b.overshoot.toFixed(1)}</td>
        <td class="num">${b.sl_afstand.toFixed(1)}</td>
        <td class="num neg">${b.marge.toFixed(2)}</td>
        <td>${b.daarna_tp ? "prijs haalde daarna het TP-niveau" : "—"}</td></tr>`).join("");
      binnen.innerHTML = `<div class="chart-panel" style="margin-top:16px">
        <h3>Stops die binnen de sweep lagen</h3>
        <p class="hint">Niet je verlies, maar je stopplaatsing. Bij deze trades was de
          beweging waar je setup op gebouwd is nog niet klaar toen je stop al geraakt werd.</p>
        <div class="mt-table-wrap"><table class="mt">
          <thead><tr><th>Datum</th><th class="num">Sweep</th><th class="num">SL</th>
            <th class="num">Marge</th><th>Daarna</th></tr></thead>
          <tbody>${rijen}</tbody></table></div></div>`;
    }
  }
}

/* ---- Shift-kwaliteit, volume en minuten in de hourly ---- */
function kwaliteitTabel(blok, kop) {
  if (!blok || !blok.rijen.length || blok.gelogd === 0) {
    return leeg(5, blok ? blok.gelogd : 0,
      "Dit veld staat in het trade-formulier — één klik per trade vult het.");
  }
  const rijen = blok.rijen.map((r) => `<tr>
    <td>${r.naam}</td>
    <td class="num">${r.n}</td>
    <td class="num">${r.n ? r.winrate + "%" : "–"}</td>
    <td class="num ${r.expectancy_r > 0 ? "pos" : r.expectancy_r < 0 ? "neg" : ""}">${r.n ? r.expectancy_r.toFixed(2) + "R" : "–"}</td>
    <td class="num ${r.netto_eur > 0 ? "pos" : r.netto_eur < 0 ? "neg" : ""}">${r.n ? "€ " + r.netto_eur.toFixed(2) : "–"}</td></tr>`).join("");
  const noot = blok.ontbreekt
    ? `<p class="hint" style="margin-top:8px">${blok.ontbreekt} ${blok.ontbreekt === 1 ? "trade heeft" : "trades hebben"} dit veld nog niet ingevuld.</p>`
    : "";
  return `<div class="mt-table-wrap"><table class="mt">
    <thead><tr><th>${kop}</th><th class="num">n</th><th class="num">Winrate</th>
      <th class="num">Expectancy</th><th class="num">Netto</th></tr></thead>
    <tbody>${rijen}</tbody></table></div>${noot}`;
}

function renderKwaliteit(k, inHourly) {
  const shift = document.getElementById("shiftKwaliteit");
  const vol = document.getElementById("volumeKwaliteit");
  const uur = document.getElementById("inHourly");
  const tip = document.getElementById("shiftTooltip");
  if (!shift) return;

  if (tip && k && k.tooltip) tip.textContent = k.tooltip;

  shift.innerHTML = kwaliteitTabel(k && k.shift, "Shift") +
    (k && k.oordeel ? `<p class="hint" style="margin-top:8px">${k.oordeel}</p>` : "");

  if (vol) {
    vol.innerHTML = kwaliteitTabel(k && k.volume, "Volume") +
      kwaliteitTabel(k && k.overextensie, "Overextensie");
  }
  if (uur) uur.innerHTML = kwaliteitTabel(inHourly && { rijen: inHourly.rijen, gelogd: inHourly.rijen.reduce((a, r) => a + r.n, 0), ontbreekt: inHourly.ontbreekt }, "Minuut");
}

/* =====================================================================
   Proces boven uitkomst (ronde 3, punt 1) — plus venster en de mens-laag.

   De winrate staat er nog, maar niet meer alleen. Ernaast staat wat je
   checklist ervan vindt, en wat er van je cijfers overblijft als je de
   trades die je zelf als geluk markeerde apart zet.
   ===================================================================== */
function renderProces(p) {
  const bord = document.getElementById("procesBord");
  if (!bord) return;
  if (!p || !p.scorebord || !p.scorebord.n) {
    bord.innerHTML = leeg(5, 0, "Zodra je trades hebt gelogd staat hier je proces-scorebord.");
    return;
  }
  const s = p.scorebord;
  const cel = (k, v, extra = "") => `<div class="mt-cell${extra}">
    <div class="k">${k}</div><div class="val">${v}</div></div>`;

  bord.innerHTML = `
    <div class="mt-bar">
      ${cel("Winrate (uitkomst)", s.winrate + "%")}
      ${cel("Valide-setup-ratio", s.valide_ratio + "%", " accent")}
      ${cel("Valide setups", `${s.valide} van ${s.n}`)}
      ${cel("Winrate zonder luck", s.winrate_zonder_luck + "%")}
      ${cel("Reeks valide setups", `${p.streak.huidig} (record ${p.streak.langste})`, " accent")}
      ${cel("Uit valide setups", s.aandeel_valide_pct === null || s.aandeel_valide_pct === undefined
            ? "–" : s.aandeel_valide_pct + "% van je netto")}
    </div>
    <p class="proces-uitleg">
      De valide-setup-ratio is het aandeel A- en B-setups. Dát is het cijfer dat je kunt sturen;
      je winrate is de uitkomst daarvan. Loopt de ratio omhoog en de winrate niet, dan heb je
      een geduldprobleem. Loopt de winrate omhoog terwijl de ratio daalt, dan word je betaald
      voor gedrag dat je niet wilt aanleren.
    </p>
    ${s.oordeel ? `<div class="luck-strook"><strong>Geluk apart gezet.</strong> ${s.oordeel}</div>` : ""}
    ${p.schone_weken ? `<div class="luck-strook" style="border-left-color:var(--green);
        background:color-mix(in srgb, var(--green) 7%, transparent)">
        <strong>Schone weken.</strong> ${p.schone_weken.boodschap}
        ${p.schone_weken.n_schoon ? ` Tot nu toe ${p.schone_weken.n_schoon} van de ${p.schone_weken.weken.length} weken zonder één C${
          p.schone_weken.huidige_reeks > 1 ? `, en je zit op een reeks van ${p.schone_weken.huidige_reeks}` : ""}.` : ""}
      </div>` : ""}
    ${!s.genoeg ? `<p class="hint">Nog ${s.min_n - s.n} trades voordat dit echt iets zegt.</p>` : ""}`;
}

function renderVenster(p) {
  const box = document.getElementById("vensterBlok");
  if (!box) return;
  if (!p || !p.venster) { box.innerHTML = ""; return; }
  const v = p.venster;
  const hint = document.getElementById("vensterHint2");
  if (hint) hint.textContent =
    `Je venster staat op ${v.van}–${v.tot} bij jou op de klok (${v.van_londen}–${v.tot_londen} Londen).`;

  if (!v.binnen.n && !v.buiten.n) {
    box.innerHTML = leeg(5, 0, "Vul entrytijden in bij je trades, dan verschijnt dit.");
    return;
  }
  const rij = (b) => `<tr>
    <td>${b.naam}</td><td class="num">${b.n}</td>
    <td class="num">${b.n ? b.winrate + "%" : "–"}</td>
    <td class="num">${b.n ? b.valide_ratio + "%" : "–"}</td>
    <td class="num ${cls(b.netto_eur)}">${b.n ? eur(b.netto_eur) : "–"}</td></tr>`;
  box.innerHTML = `<div class="mt-table-wrap"><table class="mt">
      <thead><tr><th></th><th class="num">n</th><th class="num">Winrate</th>
        <th class="num">Valide</th><th class="num">Netto</th></tr></thead>
      <tbody>${rij(v.binnen)}${rij(v.buiten)}</tbody></table></div>
    ${v.oordeel ? `<p class="hint" style="margin-top:8px">${v.oordeel}</p>` : ""}
    ${v.zonder_tijd ? `<p class="hint">${v.zonder_tijd} ${v.zonder_tijd === 1 ? "trade heeft" : "trades hebben"} geen entrytijd — die tellen hier niet mee.</p>` : ""}`;
}

function renderSessies(p) {
  const box = document.getElementById("sessieBlok");
  if (!box) return;
  if (!p || !p.sessies || !p.sessies.ingevuld) {
    box.innerHTML = leeg(3, p && p.sessies ? p.sessies.ingevuld : 0,
      "Vul op het dagoverzicht de kaart 'Hoe ging het vandaag?' in — drie klikken per dag.");
    return;
  }
  const s = p.sessies;
  const rijen = s.staten.filter((x) => x.dagen).map((x) => `<tr>
    <td>${x.key}</td><td class="num">${x.dagen}</td><td class="num">${x.trades}</td>
    <td class="num ${cls(x.netto_eur)}">${eur(x.netto_eur)}</td></tr>`).join("");
  const lessen = s.lessen.slice(-4).reverse().map((l) =>
    `<li><span class="mono" style="color:var(--muted)">${l.datum}</span> ${l.les}</li>`).join("");
  box.innerHTML = `<div class="mt-table-wrap"><table class="mt">
      <thead><tr><th>Staat vooraf</th><th class="num">Dagen</th><th class="num">Trades</th>
        <th class="num">Netto</th></tr></thead><tbody>${rijen}</tbody></table></div>
    ${s.oordeel ? `<p class="hint" style="margin-top:8px">${s.oordeel}</p>` : ""}
    ${lessen ? `<div class="section-title" style="margin-top:14px">Je eigen lessen</div>
       <ul class="lessen">${lessen}</ul>` : ""}`;
}
