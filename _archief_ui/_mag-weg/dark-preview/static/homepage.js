/* =====================================================================
   Homepage v2 (29 sep 2026) — de journal in één geheel.
   Saldo (gelijk aan MT5) → nog te loggen → nu → wanneer → hoe → proces →
   coach → kalender → trades. Alles uit /api/prestaties, /api/beoordelen,
   /api/saldo, /api/fouten en /api/mt5/status.
   ===================================================================== */

const KLEUR = { groen: "#089981", rood: "#f23645", blauw: "#2962ff", goud: "#f2900d", grijs: "#98a2b3", plum: "#4c7dff" };
const GRID = "rgba(120,123,134,.15)", TICK = "#787b86";
const WD = ["ma", "di", "wo", "do", "vr", "za", "zo"];
const charts = {};
let DATA = null, LOG = null, SALDO = null, MT5 = null, curveModus = "saldo";

/* ---------- opmaak ---------- */
const nl = (n, d = 2) => Number(n).toFixed(d).replace(".", ",");
function eur(n) { if (n == null) return "–"; return "€ " + (n >= 0 ? "+" : "−") + nl(Math.abs(n)); }
function eurKaal(n) { if (n == null) return "–"; return "€ " + nl(n); }
function pct(n) { if (n == null) return "–"; return (n >= 0 ? "+" : "") + nl(n) + "%"; }
function r2(n) { if (n == null) return "–"; return (n >= 0 ? "+" : "") + nl(n) + "R"; }
function cls(n) { return n > 0 ? "pos" : (n < 0 ? "neg" : ""); }
function kort(datum) { if (!datum) return "start"; const [, m, d] = datum.split("-"); return `${+d}/${+m}`; }
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function vandaagISO() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }
function wd(datum) { return (new Date(datum + "T12:00").getDay() + 6) % 7; }
function maak(id, cfg) { if (charts[id]) charts[id].destroy(); const el = document.getElementById(id); if (!el) return; charts[id] = new Chart(el, cfg); }
const basisOpties = (extra = {}) => ({
  responsive: true, maintainAspectRatio: false, animation: false,
  plugins: { legend: { display: false }, ...(extra.plugins || {}) },
  scales: {
    x: { grid: { display: false }, ticks: { color: TICK, font: { size: 11 } }, ...(extra.x || {}) },
    y: { grid: { color: GRID }, ticks: { color: TICK, font: { size: 11 } }, ...(extra.y || {}) },
  },
});

/* ---------- laden ---------- */
async function boot() {
  try {
    [DATA, LOG, SALDO] = await Promise.all([
      api("/api/prestaties?bron=live"), api("/api/beoordelen"), api("/api/saldo")]);
  } catch (e) {
    document.querySelector(".container").insertAdjacentHTML("afterbegin",
      `<div class="panel"><b>Kon de cijfers niet laden.</b> ${esc(e.message)}</div>`);
    return;
  }
  api("/api/mt5/status").then((s) => { MT5 = s; renderHeroKop(); }).catch(() => {});
  renderHeroKop();
  renderCurve();
  renderKpi();
  renderTeLoggen();
  renderNu();
  if (DATA.kern && DATA.kern.n) {
    renderUur(); renderSessie(); renderHeatmap();
    renderRdist(); renderMfe(); renderRol(); renderDuur();
    renderProces(); renderRliggen(); renderKalender(); renderMaanden(); renderRecent();
    api("/api/fouten?bron=live").then(renderFouten).catch(() => {});
    api("/api/weken?aantal=12").then(renderWeken).catch(() => {});
  }
  document.getElementById("homeVoet").textContent =
    `Automatisch uit MetaTrader — ${DATA.kern.n} trades over ${DATA.kern.handelsdagen} handelsdagen.`;
  if (location.hash === "#saldo") { modal.hidden = false; renderSaldo(); }
  else if (location.hash) { const el = document.querySelector(location.hash); if (el) el.scrollIntoView(); }
}

async function herlaadCijfers() {
  [DATA, SALDO] = await Promise.all([api("/api/prestaties?bron=live"), api("/api/saldo")]);
  renderHeroKop(); renderCurve(); renderKpi(); renderNu();
  if (DATA.kern.n) { renderProces(); renderRecent(); renderUur(); renderSessie(); renderHeatmap(); }
}

/* ---------- 1. saldo ---------- */
function renderHeroKop() {
  const k = DATA.kern, s = SALDO;
  const live = MT5 && MT5.verbonden && MT5.balans != null;
  document.getElementById("heroSaldo").textContent = eurKaal(live ? MT5.balans : s.saldo);
  const chip = document.getElementById("mt5Chip");
  if (live) {
    const zw = MT5.zwevend ? ` · open ${eur(MT5.zwevend)}` : "";
    chip.innerHTML = `<span class="stip aan"></span>live uit MT5${zw}`;
  } else if (s.mt5) {
    chip.innerHTML = `<span class="stip"></span>MT5 laatst ${esc(s.mt5.ts.slice(5, 16).replace("T", " "))}`;
  } else chip.innerHTML = `<span class="stip"></span>handmatig`;
  const delen = [
    `<span class="${cls(k.groei_pct)}"><b>${pct(k.groei_pct)}</b> trading-rendement</span>`,
    `<span>trading ${`<b class="${cls(k.netto_eur)}">${eur(k.netto_eur)}</b>`}</span>`,
    `<span>ingelegd ${eurKaal(s.ingelegd)}</span>`,
  ];
  const overig = +(s.correcties + s.aansluiting).toFixed(2);
  if (Math.abs(overig) >= 0.01) delen.push(`<span title="Correcties + automatische MT5-aansluiting: geld dat niet uit gelogde trades komt">niet gelogd ${eur(overig)}</span>`);
  document.getElementById("heroSub").innerHTML = delen.join('<span class="dot">·</span>');
}

function renderCurve() {
  const e = DATA.equity || [];
  const trades = e.filter((p) => p.soort !== "kas");
  let labels, waarden, kleurRef;
  if (curveModus === "r") {
    let cum = 0;
    const rs = (DATA.scatter || []).slice().sort((a, b) => (a.datum + (a.tijd || "")).localeCompare(b.datum + (b.tijd || "")));
    labels = ["start", ...rs.map((x) => kort(x.datum))];
    waarden = [0, ...rs.map((x) => +(cum += x.r).toFixed(2))];
    kleurRef = 0;
  } else if (curveModus === "trading") {
    labels = trades.map((p) => kort(p.datum)); waarden = trades.map((p) => p.trading); kleurRef = DATA.kern.startkapitaal;
  } else {
    labels = e.map((p) => kort(p.datum)); waarden = e.map((p) => p.saldo); kleurRef = null;
  }
  const laatste = waarden[waarden.length - 1] ?? 0;
  const boven = kleurRef == null ? DATA.kern.netto_eur >= 0 : laatste >= kleurRef;
  const lijn = boven ? KLEUR.groen : KLEUR.rood;
  const ctx = document.getElementById("cCurve").getContext("2d");
  const grad = ctx.createLinearGradient(0, 0, 0, 280);
  grad.addColorStop(0, boven ? "rgba(8,153,129,.20)" : "rgba(242,54,69,.18)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  const kasIdx = curveModus === "saldo" ? e.map((p, i) => (p.soort === "kas" ? i : -1)).filter((i) => i >= 0) : [];
  const bron = curveModus === "saldo" ? e : (curveModus === "trading" ? trades : null);
  maak("cCurve", {
    type: "line",
    data: { labels, datasets: [{
      data: waarden, borderColor: lijn, backgroundColor: grad, fill: true, tension: .25, borderWidth: 2,
      pointRadius: waarden.map((_, i) => (kasIdx.includes(i) ? 6 : 0)),
      pointStyle: waarden.map((_, i) => (kasIdx.includes(i) ? "triangle" : "circle")),
      pointBackgroundColor: KLEUR.blauw, pointBorderColor: "#fff", pointBorderWidth: 2, pointHoverRadius: 5,
    }] },
    options: basisOpties({
      plugins: { tooltip: { callbacks: {
        title: (it) => { const p = bron && bron[it[0].dataIndex]; return p ? (p.datum ? kort(p.datum) + (p.tijd && p.tijd !== "00:00" ? " " + p.tijd : "") : "start") : labels[it[0].dataIndex]; },
        label: (c) => {
          if (curveModus === "r") return `Totaal ${r2(c.parsed.y)}`;
          const p = bron[c.dataIndex];
          if (p.soort === "kas") return [`${p.kas_soort}: ${eur(p.bedrag)}`, `Saldo ${eurKaal(p.saldo)}`, p.notitie || ""].filter(Boolean);
          return [`${curveModus === "saldo" ? "Saldo" : "Trading"} ${eurKaal(c.parsed.y)}`,
            p.netto != null ? `Trade ${eur(p.netto)}` : "", `Rendement ${pct(p.pct)}`].filter(Boolean);
        },
      } } },
      x: { ticks: { color: TICK, font: { size: 11 }, maxTicksLimit: 9 } },
    }),
  });
  // drawdown
  const dd = DATA.drawdown || [];
  document.getElementById("ddTekst").innerHTML =
    `max <b class="neg">${eur(DATA.kern.max_dd_eur)}</b> (${pct(DATA.kern.max_dd_pct)}) · nu ${eur(DATA.kern.huidige_dd_eur)}`;
  maak("cDD", {
    type: "line",
    data: { labels: dd.map((p) => kort(p.datum)), datasets: [{ data: dd.map((p) => p.dd_eur), borderColor: KLEUR.rood,
      backgroundColor: "rgba(242,54,69,.15)", fill: true, pointRadius: 0, borderWidth: 1.5, tension: .2 }] },
    options: basisOpties({ x: { display: false }, y: { max: 0, ticks: { color: TICK, font: { size: 10 }, maxTicksLimit: 3 } },
      plugins: { tooltip: { callbacks: { label: (c) => `Onder de piek: ${eur(c.parsed.y)} (${pct(dd[c.dataIndex].dd_pct)})` } } } }),
  });
}

document.getElementById("curveTabs").addEventListener("click", (ev) => {
  const b = ev.target.closest("button"); if (!b) return;
  curveModus = b.dataset.m;
  document.querySelectorAll("#curveTabs button").forEach((x) => x.classList.toggle("on", x === b));
  renderCurve();
});

/* ---------- KPI ---------- */
function renderKpi() {
  const k = DATA.kern, p = DATA.proces || {};
  const cellen = [
    { key: "Trading P/L", val: eur(k.netto_eur), cls: cls(k.netto_eur), accent: true, sub: `${k.n} trades` },
    { key: "Winrate", val: k.winrate + "%", sub: `${k.winst_dagen} winst- / ${k.verlies_dagen} verliesdagen` },
    { key: "Expectancy", val: r2(k.expectancy_r), cls: cls(k.expectancy_r), sub: "per trade" },
    { key: "Profit factor", val: k.profit_factor != null ? nl(k.profit_factor) : "–", cls: k.profit_factor >= 1 ? "pos" : "neg", sub: "winst ÷ verlies" },
    { key: "Gem. winst / verlies", val: `${r2(k.gem_winst_r)} / ${r2(k.gem_verlies_r)}`, sub: `${eur(k.gem_winst_eur)} / ${eur(k.gem_verlies_eur)}` },
    { key: "Max drawdown", val: eur(k.max_dd_eur), cls: "neg", sub: pct(k.max_dd_pct) },
    { key: "Proces-score", val: p.gem_score != null ? p.gem_score + "%" : "–", sub: p.n_scores ? `over ${p.n_scores} gelogde trades` : "log je trades" },
    { key: "Kosten", val: eur(k.kosten_eur), sub: "charges/commissie" },
  ];
  document.getElementById("kpiBar").innerHTML = `<div class="mt-bar">${cellen.map((c) => `
    <div class="mt-cell${c.accent ? " accent" : ""}"><div class="k">${c.key}</div>
      <div class="val ${c.cls || ""}">${c.val}</div>${c.sub ? `<div class="mt-sub">${c.sub}</div>` : ""}</div>`).join("")}</div>`;
}

/* ---------- 2. nog te loggen ---------- */
function renderTeLoggen() {
  const box = document.getElementById("te-loggen");
  const open = LOG.open || [];
  if (!open.length) {
    box.innerHTML = `<div class="h2-alles-gelogd">✓ Alles gelogd. Nieuwe trades uit MT5 verschijnen hier vanzelf.</div>`;
    return;
  }
  box.innerHTML = `<div class="section-title">Nog te loggen <span class="h2-teller">${open.length}</span></div>
    <p class="hint h2-uitleg">Deze trades kwamen uit MetaTrader maar zijn nog niet beoordeeld. Setup + emotie invullen = gelogd.
      Discipline heb ik al uit MT5 gehaald — tik om als het niet klopt.</p>
    <div class="h2-logs">${open.map(logKaart).join("")}</div>`;
  box.querySelectorAll(".h2-log").forEach(koppelKaart);
}

function logKaart(t) {
  const netto = (t.resultaat || 0) + (t.charges || 0);
  const krit = new Set(LOG.kritisch || []);
  const seg = (sleutel, w, isCheck) => {
    const ja = isCheck ? w === 1 : w === "yes", nee = isCheck ? w === 0 : w === "no";
    return `<div class="h2-seg" data-sleutel="${sleutel}">
      <button type="button" data-w="1" class="${ja ? "ja" : ""}">ja</button>
      <button type="button" data-w="0" class="${nee ? "nee" : ""}">nee</button></div>`;
  };
  const tp = t.criteria.f2_tp;
  return `<div class="h2-log panel ${t.beoordeeld === 1 ? "klaar" : ""}" data-id="${t.id}">
    <div class="h2-log-kop">
      <div>
        <div class="h2-log-titel">${t.richting === "long" ? "▲ long" : "▼ short"} · ${kort(t.datum)} ${esc(t.tijd || "")}–${esc(t.tijd_exit || "")}
          <span class="h2-log-nr">#${t.id}</span></div>
        <div class="h2-log-feiten">
          <b class="${cls(netto)}">${eur(netto)}</b>
          ${t.r != null ? `<span class="${cls(t.r)}">${r2(t.r)}</span>` : ""}
          <span>${esc(t.exit_reden || "")}</span>
          ${t.duur != null ? `<span>${t.duur} min</span>` : ""}
          ${t.sl_points != null ? `<span>SL ${Math.round(t.sl_points)} pts</span>` : ""}
          ${t.mfe_r != null ? `<span title="Max in je voordeel / tegen je">MFE ${nl(t.mfe_r)}R · MAE ${nl(t.mae_r)}R</span>` : ""}
          ${t.signaal_id ? `<span class="h2-sig" title="De signaalwachter vond deze setup">⚡ signaal</span>` : ""}
        </div>
      </div>
      <div class="h2-log-grade"><span class="grade-mini g-${t.grade}" data-rol="grade">${t.grade || "?"}</span>
        <span class="h2-score" data-rol="score">${t.proces_score != null ? t.proces_score + "%" : ""}</span></div>
    </div>
    <div class="h2-log-body">
      ${t.chart ? `<a class="h2-log-chart" href="${t.chart}" target="_blank"><img src="${t.chart}" alt="chart" loading="lazy"></a>` : ""}
      <div class="h2-log-velden">
        <div class="h2-blok"><div class="h2-blok-titel">Setup <span class="hint">(bepaalt de grade)</span></div>
          ${LOG.criteria.map(([k, l]) => `<div class="h2-rij"><span>${krit.has(k) ? "<b>" + esc(l) + "</b>" : esc(l)}</span>${seg(k, t.criteria[k], false)}</div>`).join("")}
          <div class="h2-rij auto"><span>TP op 1:1 <span class="hint">(uit MT5)</span></span>
            <span class="h2-auto ${tp === "yes" ? "ja" : tp === "no" ? "nee" : ""}">${tp === "yes" ? "ja" : tp === "no" ? "nee" : "onbekend"}</span></div>
        </div>
        <div class="h2-blok"><div class="h2-blok-titel">Discipline <span class="hint">(uit MT5 — tik om)</span></div>
          ${LOG.checks.map(([k, l]) => `<div class="h2-rij"><span>${esc(l)}</span>${seg(k, t.checks[k], true)}</div>`).join("")}
          <div class="h2-blok-titel" style="margin-top:14px">Jij</div>
          <div class="h2-lbl">Emotie vóór de trade</div>
          <div class="h2-chips" data-veld="emotie_voor">${LOG.emoties.map(([k, l, s]) =>
            `<button type="button" class="h2-chip ${s} ${t.emotie_voor === k ? "on" : ""}" data-w="${k}">${l}</button>`).join("")}</div>
          <div class="h2-lbl">Uitvoering</div>
          <div class="h2-chips" data-veld="uitvoering">${[1, 2, 3, 4, 5].map((n) =>
            `<button type="button" class="h2-chip ${t.uitvoering === n ? "on" : ""}" data-w="${n}">${n}</button>`).join("")}
            <span class="hint">1 = slordig · 5 = perfect uitgevoerd</span></div>
          <div class="h2-lbl">Zou je deze trade opnieuw nemen?</div>
          <div class="h2-chips" data-veld="opnieuw">
            <button type="button" class="h2-chip goed ${t.opnieuw === 1 ? "on" : ""}" data-w="1">ja, precies zo</button>
            <button type="button" class="h2-chip slecht ${t.opnieuw === 0 ? "on" : ""}" data-w="0">nee</button></div>
        </div>
      </div>
    </div>
    ${t.sl_prijs == null ? `<div class="h2-niveaus"><b class="neg">SL/TP niet gezien in MT5.</b>
      <span>Entry ${t.entry != null ? nl(t.entry) : "–"}</span>
      <label>SL <input type="text" inputmode="decimal" data-niv="sl" placeholder="bv. ${t.entry != null ? nl(t.entry + (t.richting === "short" ? 4 : -4)) : ""}"></label>
      <label>TP <input type="text" inputmode="decimal" data-niv="tp" placeholder="bv. ${t.entry != null ? nl(t.entry + (t.richting === "short" ? -4 : 4)) : ""}"></label>
      <button type="button" class="btn" data-rol="niveaus">Opslaan</button><span class="hint" data-rol="nivmelding"></span></div>` : ""}
    <div class="h2-lbl">Wat ging er mis? <span class="hint">(optioneel)</span></div>
    <div class="h2-chips multi" data-veld="foutcodes">${(LOG.fouttags || []).map((f) =>
      `<button type="button" class="h2-chip ${t.foutcodes.includes(f) ? "on" : ""}" data-w="${esc(f)}">${esc(f)}</button>`).join("")}</div>
    <textarea class="h2-les" data-veld="les" rows="2" placeholder="Les in één zin — wat neem je mee naar de volgende trade?">${esc(t.les)}</textarea>
    <div class="h2-log-voet"><span data-rol="status">${statusTekst(t)}</span>
      <a href="/trade?id=${t.id}" class="hint">volledige trade →</a>
      <button type="button" class="btn btn-primary" data-rol="klaar" ${t.beoordeeld === 1 ? "" : "hidden"}>✓ Klaar</button></div>
  </div>`;
}

function statusTekst(t) {
  const ontbreekt = LOG.criteria.filter(([k]) => !["yes", "no"].includes(t.criteria[k])).length;
  if (t.beoordeeld === 1) return `<b class="pos">Gelogd</b> — grade ${t.grade}${t.schoon === 1 ? " · regels gevolgd" : t.schoon === 0 ? " · regel gebroken" : ""}`;
  const d = [];
  if (ontbreekt) d.push(`${ontbreekt} setup-punt${ontbreekt > 1 ? "en" : ""}`);
  if (!t.emotie_voor) d.push("je emotie");
  return `Nog: ${d.join(" en ")}`;
}

async function stuur(id, body) {
  return api(`/api/beoordeel/${id}`, { method: "POST", body: JSON.stringify(body) });
}

function koppelKaart(kaart) {
  const id = +kaart.dataset.id;
  const werkBij = (t) => {
    const g = kaart.querySelector('[data-rol="grade"]');
    g.textContent = t.grade || "?"; g.className = `grade-mini g-${t.grade}`;
    kaart.querySelector('[data-rol="score"]').textContent = t.proces_score != null ? t.proces_score + "%" : "";
    kaart.querySelector('[data-rol="status"]').innerHTML = statusTekst(t);
    kaart.querySelector('[data-rol="klaar"]').hidden = t.beoordeeld !== 1;
    kaart.classList.toggle("klaar", t.beoordeeld === 1);
    const i = LOG.open.findIndex((x) => x.id === id); if (i >= 0) LOG.open[i] = t;
  };
  kaart.querySelectorAll(".h2-seg").forEach((seg) => seg.addEventListener("click", async (ev) => {
    const b = ev.target.closest("button"); if (!b) return;
    const aan = b.classList.contains("ja") || b.classList.contains("nee");
    const waarde = aan ? "" : b.dataset.w;
    seg.querySelectorAll("button").forEach((x) => x.classList.remove("ja", "nee"));
    if (!aan) b.classList.add(b.dataset.w === "1" ? "ja" : "nee");
    werkBij(await stuur(id, { sleutel: seg.dataset.sleutel, waarde }));
  }));
  kaart.querySelectorAll(".h2-chips").forEach((groep) => groep.addEventListener("click", async (ev) => {
    const b = ev.target.closest("button"); if (!b) return;
    const veld = groep.dataset.veld;
    let waarde;
    if (groep.classList.contains("multi")) {
      b.classList.toggle("on");
      waarde = [...groep.querySelectorAll(".on")].map((x) => x.dataset.w);
    } else {
      const was = b.classList.contains("on");
      groep.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
      if (!was) b.classList.add("on");
      waarde = was ? "" : b.dataset.w;
    }
    werkBij(await stuur(id, { veld, waarde }));
  }));
  const nivKnop = kaart.querySelector('[data-rol="niveaus"]');
  if (nivKnop) nivKnop.onclick = async () => {
    const sl = kaart.querySelector('[data-niv="sl"]').value.trim(), tp = kaart.querySelector('[data-niv="tp"]').value.trim();
    const meld = kaart.querySelector('[data-rol="nivmelding"]');
    try {
      const t = await api(`/api/trade/${id}/niveaus`, { method: "POST", body: JSON.stringify({ sl, tp }) });
      werkBij(t);
      meld.innerHTML = `<span class="pos">✓ ${t.r != null ? r2(t.r) : ""} · RR ${t.rr != null ? nl(t.rr) : "–"}</span>`;
      const img = kaart.querySelector(".h2-log-chart img"); if (img && t.chart) img.src = t.chart;
    } catch (e) { meld.innerHTML = `<span class="neg">${esc(e.message)}</span>`; }
  };
  const les = kaart.querySelector(".h2-les");
  les.addEventListener("change", async () => werkBij(await stuur(id, { veld: "les", waarde: les.value })));
  kaart.querySelector('[data-rol="klaar"]').addEventListener("click", async () => {
    if (les.value) await stuur(id, { veld: "les", waarde: les.value });
    kaart.classList.add("weg");
    setTimeout(async () => {
      LOG.open = LOG.open.filter((x) => x.id !== id);
      renderTeLoggen();
      herlaadCijfers();
    }, 250);
  });
}

/* ---------- 3. nu ---------- */
function periodePanel(elId, titel, dagen, extra) {
  const n = dagen.reduce((s, r) => s + r.n, 0);
  const netto = +dagen.reduce((s, r) => s + r.netto_eur, 0).toFixed(2);
  const nr = +dagen.reduce((s, r) => s + (r.netto_r || 0), 0).toFixed(2);
  const win = dagen.reduce((s, r) => s + (r.winnaars || 0), 0);
  const bars = dagen.length > 1 ? `<div class="wk-bars">${dagen.map((r) => {
    const h = Math.min(100, Math.abs(r.netto_eur) * 6 + 8);
    return `<div class="wk-day" title="${kort(r.datum)}: ${eur(r.netto_eur)} · ${r.n} trades"><div class="wk-col">
      <div class="wk-fill ${r.netto_eur >= 0 ? "pos" : "neg"}" style="height:${h}%"></div></div>
      <div class="wk-lbl">${dagen.length > 7 ? +r.datum.slice(8) : WD[wd(r.datum)]}</div></div>`; }).join("")}</div>` : "";
  document.getElementById(elId).innerHTML = `
    <div class="pp-kop"><h3>${titel}</h3><span class="pp-badge ${cls(netto)}">${eur(netto)}</span></div>
    ${n ? `<div class="pp-cijfers">
      <div><div class="pp-val ${cls(nr)}">${r2(nr)}</div><div class="pp-cap">resultaat</div></div>
      <div><div class="pp-val">${n}</div><div class="pp-cap">trades</div></div>
      <div><div class="pp-val">${Math.round(100 * win / n)}%</div><div class="pp-cap">winrate</div></div></div>${bars}${extra || ""}`
      : `<div class="empty wachtend"><b>Nog geen trades.</b><span></span></div>${extra || ""}`}`;
}
function renderNu() {
  const pd = DATA.per_dag || [], nu = vandaagISO();
  const d = new Date(); const ma = new Date(d); ma.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  const maISO = `${ma.getFullYear()}-${String(ma.getMonth() + 1).padStart(2, "0")}-${String(ma.getDate()).padStart(2, "0")}`;
  const dag = pd.filter((r) => r.datum === nu);
  const n = dag.reduce((s, r) => s + r.n, 0);
  let regel = `<div class="pp-voet">Dagmaximum 2 trades${n >= 2 ? ' — <b class="neg">bereikt, stop voor vandaag</b>' : ""}</div>`;
  periodePanel("dagPanel", "Vandaag", dag, regel);
  periodePanel("weekPanel", "Deze week", pd.filter((r) => r.datum >= maISO));
  const m = nu.slice(0, 7);
  const mrow = (DATA.per_maand || []).find((x) => x.maand === m);
  periodePanel("maandPanel", mrow ? mrow.label : "Deze maand", pd.filter((r) => r.datum.startsWith(m)),
    mrow ? `<div class="pp-voet">rendement ${pct(mrow.pct)}</div>` : "");
}

/* ---------- 3b. progressie per week ---------- */
function renderWeken(res) {
  const w = res.weken || [];
  const huidig = w.length ? w[w.length - 1].maandag : null;
  const mini = (id, key, eenheid, polar) => {
    const vals = w.map((x) => x[key]);
    maak(id, { type: "bar",
      data: { labels: w.map((x) => "wk " + x.week), datasets: [{ data: vals, borderRadius: 3, maxBarThickness: 24,
        backgroundColor: w.map((x, i) => { const nu = x.maandag === huidig, v = vals[i];
          if (polar) return nu ? (v >= 0 ? KLEUR.groen : KLEUR.rood) : (v >= 0 ? "rgba(8,153,129,.35)" : "rgba(242,54,69,.35)");
          return nu ? KLEUR.plum : "rgba(76,125,255,.28)"; }) }] },
      options: basisOpties({
        x: { ticks: { color: TICK, font: { size: 10 }, maxRotation: 0, autoSkip: true } },
        y: { ticks: { color: TICK, font: { size: 10 }, maxTicksLimit: 4 }, ...(polar ? {} : { min: 0, max: 100 }) },
        plugins: { tooltip: { callbacks: {
          title: (it) => `Week ${w[it[0].dataIndex].week} · ${w[it[0].dataIndex].bereik}`,
          label: (c) => (c.parsed.y == null ? "geen data" : (polar ? r2(c.parsed.y) : c.parsed.y + eenheid) + ` · ${w[c.dataIndex].n} trades`) } } } }) });
    charts[id].options.onClick = (e, el) => { if (el.length) location.href = "/week?datum=" + w[el[0].index].maandag; };
  };
  mini("wR", "netto_r", "R", true); mini("wProces", "proces_score", "%"); mini("wWin", "winrate", "%"); mini("wSchoon", "schoon_pct", "%");
}

/* ---------- 4. wanneer ---------- */
function renderUur() {
  const rij = DATA.per_uur.rijen;
  const uren = []; const min = Math.min(...rij.map((r) => r.uur)), max = Math.max(...rij.map((r) => r.uur));
  for (let u = min; u <= max; u++) uren.push(rij.find((r) => r.uur === u) || { uur: u, n: 0, netto_eur: 0, winrate: 0, expectancy_r: 0 });
  const venster = { id: "venster", beforeDraw(c) {
    const x = c.scales.x, a = c.chartArea; const i0 = uren.findIndex((r) => r.uur === 10), i1 = uren.findIndex((r) => r.uur === 14);
    if (i0 < 0 || i1 < 0) return; const w = x.getPixelForValue(1) - x.getPixelForValue(0);
    c.ctx.save(); c.ctx.fillStyle = "rgba(41,98,255,.06)";
    c.ctx.fillRect(x.getPixelForValue(i0) - w / 2, a.top, (i1 - i0 + 1) * w, a.bottom - a.top); c.ctx.restore(); } };
  maak("cUur", { type: "bar", plugins: [venster],
    data: { labels: uren.map((r) => String(r.uur).padStart(2, "0") + "u"), datasets: [{ data: uren.map((r) => r.netto_eur),
      backgroundColor: uren.map((r) => (r.netto_eur >= 0 ? KLEUR.groen : KLEUR.rood)), borderRadius: 4, maxBarThickness: 34 }] },
    options: basisOpties({ plugins: { tooltip: { callbacks: { label: (c) => { const r = uren[c.dataIndex];
      return r.n ? [`${eur(r.netto_eur)} · ${r.n} trades`, `winrate ${r.winrate}% · ${r2(r.expectancy_r)} per trade`] : "geen trades"; } } } } }) });
}
function renderSessie() {
  const rij = DATA.per_sessie.rijen;
  maak("cSessie", { type: "bar",
    data: { labels: rij.map((r) => r.naam), datasets: [{ data: rij.map((r) => r.expectancy_r),
      backgroundColor: rij.map((r) => (r.expectancy_r >= 0 ? KLEUR.groen : KLEUR.rood)), borderRadius: 4, maxBarThickness: 44 }] },
    options: basisOpties({ plugins: { tooltip: { callbacks: { label: (c) => { const r = rij[c.dataIndex];
      return [`${r2(r.expectancy_r)} per trade`, `${r.n} trades · winrate ${r.winrate}% · ${eur(r.netto_eur)}`, `${r.van}–${r.tot}`]; } } } } }) });
  document.getElementById("sessieTabel").innerHTML = `<div class="h2-mini">${rij.map((r) =>
    `<span><b>${esc(r.naam)}</b> ${r.n}× · ${r.winrate}% · <span class="${cls(r.netto_eur)}">${eur(r.netto_eur)}</span>${r.genoeg ? "" : ' <i title="minder dan 5 trades">*</i>'}</span>`).join("")}</div>`;
}
function heatKleur(v) {
  if (v == null) return "transparent";
  const a = Math.min(1, Math.abs(v) / 1.0) * .75 + .1;
  return v >= 0 ? `rgba(8,153,129,${a})` : `rgba(242,54,69,${a})`;
}
function renderHeatmap() {
  const h = DATA.heatmap;
  if (!h.uren.length) return;
  document.getElementById("heatmap").innerHTML = `<div class="h2-heat" style="grid-template-columns:34px repeat(${h.uren.length},1fr)">
    <div></div>${h.uren.map((u) => `<div class="hh">${String(u).padStart(2, "0")}</div>`).join("")}
    ${h.rijen.map((r) => `<div class="hw">${r.weekdag.slice(0, 2)}</div>${r.cellen.map((c) =>
      `<div class="hc ${c.n ? "" : "leeg"} ${c.expectancy_r != null && Math.abs(c.expectancy_r) < 0.45 ? "licht" : ""}" style="background:${heatKleur(c.expectancy_r)}"
        title="${r.weekdag} ${String(c.uur).padStart(2, "0")}:00 — ${c.n} trades${c.n ? `, ${r2(c.expectancy_r)} gem., ${eur(c.netto_eur)}` : ""}">${c.n || ""}</div>`).join("")}`).join("")}
  </div><div class="h2-heat-leg"><span style="background:${heatKleur(-1)}"></span>−1R <span style="background:#eee"></span>0 <span style="background:${heatKleur(1)}"></span>+1R</div>`;
}

/* ---------- 5. hoe ---------- */
function renderRdist() {
  const d = DATA.r_verdeling;
  maak("cRdist", { type: "bar",
    data: { labels: d.labels, datasets: [{ data: d.aantallen, borderRadius: 4, maxBarThickness: 40,
      backgroundColor: d.labels.map((l, i) => (i < 3 ? KLEUR.rood : i === 3 ? KLEUR.grijs : KLEUR.groen)) }] },
    options: basisOpties({ y: { ticks: { precision: 0, color: TICK } },
      plugins: { tooltip: { callbacks: { label: (c) => `${c.parsed.y} trades` } } } }) });
}
function renderMfe() {
  const pts = (DATA.scatter || []).filter((x) => x.mfe_r != null);
  maak("cMfe", { type: "scatter",
    data: { datasets: [{ data: pts.map((x) => ({ x: x.mfe_r, y: x.mae_r })), pointRadius: 5, pointHoverRadius: 7,
      backgroundColor: pts.map((x) => (x.r >= 0 ? "rgba(8,153,129,.75)" : "rgba(242,54,69,.75)")), borderColor: "#fff", borderWidth: 1.5 }] },
    options: basisOpties({ x: { title: { display: true, text: "MFE (R in je voordeel)", color: TICK }, grid: { color: GRID } },
      y: { title: { display: true, text: "MAE (R tegen je)", color: TICK } },
      plugins: { tooltip: { callbacks: { label: (c) => { const x = pts[c.dataIndex];
        return [`#${x.id} ${kort(x.datum)} ${x.tijd || ""}`, `pakte ${r2(x.r)} · MFE ${nl(x.mfe_r)}R · MAE ${nl(x.mae_r)}R`]; } } } } }) });
  document.getElementById("cMfe").onclick = (ev) => { const p = charts.cMfe.getElementsAtEventForMode(ev, "nearest", { intersect: true }, false); if (p.length) location.href = "/trade?id=" + pts[p[0].index].id; };
}
function renderRol() {
  const p = DATA.rollend.punten;
  maak("cRol", { type: "line",
    data: { labels: p.map((x) => "#" + x.n), datasets: [{ data: p.map((x) => x.expectancy_r), borderColor: KLEUR.blauw, borderWidth: 2,
      pointRadius: 0, pointHoverRadius: 4, tension: .25, fill: { target: { value: 0 }, above: "rgba(8,153,129,.12)", below: "rgba(242,54,69,.12)" } }] },
    options: basisOpties({ x: { ticks: { color: TICK, maxTicksLimit: 8 } },
      plugins: { tooltip: { callbacks: { label: (c) => [`expectancy ${r2(p[c.dataIndex].expectancy_r)}`, `winrate ${p[c.dataIndex].winrate}% (laatste 10)`] } } } }) });
}
function renderDuur() {
  const pts = (DATA.scatter || []).filter((x) => x.duur != null);
  maak("cDuur", { type: "scatter",
    data: { datasets: [{ data: pts.map((x) => ({ x: x.duur, y: x.r })), pointRadius: 5, pointHoverRadius: 7,
      backgroundColor: pts.map((x) => (x.r >= 0 ? "rgba(8,153,129,.75)" : "rgba(242,54,69,.75)")), borderColor: "#fff", borderWidth: 1.5 }] },
    options: basisOpties({ x: { title: { display: true, text: "minuten in de trade", color: TICK }, grid: { color: GRID } },
      y: { title: { display: true, text: "R", color: TICK } },
      plugins: { tooltip: { callbacks: { label: (c) => { const x = pts[c.dataIndex]; return `#${x.id} · ${x.duur} min · ${r2(x.r)}`; } } } } }) });
}

/* ---------- 6. proces ---------- */
function vergelijk(titel, uitleg, rijen) {
  const max = Math.max(0.1, ...rijen.map((r) => Math.abs(r.expectancy_r)));
  return `<div class="panel h2-verg"><h3>${titel}</h3><p class="hint">${uitleg}</p>
    ${rijen.map((r) => `<div class="h2-vrij"><div class="h2-vnaam">${esc(r.naam)} <span class="hint">${r.n}×</span></div>
      <div class="h2-vbar"><div class="${r.expectancy_r >= 0 ? "pos" : "neg"}" style="width:${r.n ? Math.max(2, 50 * Math.abs(r.expectancy_r) / max) : 0}%;${r.expectancy_r >= 0 ? "left:50%" : "right:50%"}"></div></div>
      <div class="h2-vwaarde ${cls(r.expectancy_r)}">${r.n ? r2(r.expectancy_r) : "–"}</div></div>`).join("")}</div>`;
}
function renderProces() {
  const p = DATA.proces;
  const emo = (DATA.emoties || []).map((r) => ({ ...r, naam: ((LOG.emoties || []).find((e) => e[0] === r.naam) || [0, r.naam])[1] }));
  document.getElementById("procesBlok").innerHTML =
    vergelijk("Grade tegen resultaat", "Gemiddelde R per trade. Loont een A-setup echt meer dan een C?", p.grade) +
    vergelijk("Regels gevolgd?", "Trades met alle discipline-punten groen tegen trades waar je een regel brak.", p.schoon.concat(p.opnieuw.filter((r) => r.n))) +
    (emo.length ? vergelijk("Emotie vóór de trade", "Hoe je je voelde tegen wat het opleverde.", emo)
      : `<div class="panel h2-verg"><h3>Emotie vóór de trade</h3><p class="hint">Vul bij het loggen je emotie in — na een paar trades zie je hier of FOMO of twijfel je geld kost.</p></div>`);
}

/* ---------- 7. coach ---------- */
function renderRliggen() {
  const rl = DATA.r_liggen, box = document.getElementById("rliggenBlok");
  if (!rl || !rl.n) { box.innerHTML = ""; return; }
  const rijen = rl.top.filter((x) => x.gepakt_r >= 0 && x.liggen_r > 0.15).slice(0, 5);
  const omgeslagen = rl.top.filter((x) => x.gepakt_r < 0 && x.max_r >= 0.5).slice(0, 5);
  const tabel = (lijst, kop) => `<div class="mt-table-wrap" style="margin-top:10px"><table class="mt"><thead><tr><th>Trade</th><th>Richting</th><th class="num">Pakte</th><th class="num">Zat erin</th><th class="num">${kop}</th></tr></thead>
    <tbody>${lijst.map((x) => `<tr onclick="location.href='/trade?id=${x.id}'"><td>${kort(x.datum)} ${x.tijd}</td>
      <td>${x.richting === "long" ? "▲ long" : "▼ short"}</td><td class="num ${cls(x.gepakt_r)}">${nl(x.gepakt_r)}R</td>
      <td class="num">${nl(x.max_r)}R</td><td class="num neg">${nl(x.liggen_r)}R</td></tr>`).join("")}</tbody></table></div>`;
  box.innerHTML = `<div class="section-title">Wat liet je liggen</div><div class="panel coach">
    <p class="coach-zin">${rl.n_winnaars ? `Je liet gemiddeld <b>${nl(rl.gem_winnaars_r)}R</b> liggen op je winnaars.` : "Nog geen winnaars met een gemeten kaars."}
      <span class="coach-uitleg">Het verschil tussen hoever de kaars in je voordeel liep en wat je pakte — de prijs van te vroeg sluiten.</span></p>
    ${rijen.length ? tabel(rijen, "Liet liggen") : ""}
    ${omgeslagen.length ? `<p class="coach-zin" style="margin-top:16px"><b>${omgeslagen.length}</b> verliezer${omgeslagen.length > 1 ? "s" : ""} stond${omgeslagen.length > 1 ? "en" : ""} eerst ≥0,5R in je voordeel.
      <span class="coach-uitleg">Kandidaten voor een vaste regel (bv. SL naar break-even vanaf +0,7R) — test dat eerst op je data.</span></p>${tabel(omgeslagen, "Verschil")}` : ""}
  </div>`;
}
function renderFouten(f) {
  const box = document.getElementById("foutenBlok");
  const sig = (f.signalen || []).filter((s) => s.aantal).slice(0, 4);
  const dm = DATA.discipline_mt5 || {};
  if (!sig.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="section-title">Discipline (automatisch uit de feiten)</div>
    <div class="panel"><p class="coach-zin"><b>${f.schoon_pct}%</b> van je trades zonder één automatische fout.
      ${dm.n_met_positie ? `Stop verschoven bij <b>${dm.sl_verschoven}</b> van ${dm.n_met_positie} MT5-trades.` : ""}</p>
    <div class="h2-fouten">${sig.map((s) => `<div class="h2-fout"><div class="h2-fout-kop"><b>${esc(s.label)}</b><span class="neg">${s.aantal}× · ${s.pct}%</span></div>
      <div class="hint">${esc(s.correctie || s.uitleg || "")}</div></div>`).join("")}</div>
    <a class="hint" href="/fouten">alle fouten →</a></div>`;
}

/* ---------- 8. kalender + maanden ---------- */
let kalMaand = null;
function renderKalender() {
  const pd = DATA.per_dag || [];
  if (!kalMaand) kalMaand = vandaagISO().slice(0, 7);
  const [j, m] = kalMaand.split("-").map(Number);
  const eerste = new Date(j, m - 1, 1), dagen = new Date(j, m, 0).getDate();
  const leeg = (eerste.getDay() + 6) % 7;
  const per = Object.fromEntries(pd.filter((r) => r.datum.startsWith(kalMaand)).map((r) => [r.datum, r]));
  const naam = eerste.toLocaleDateString("nl-NL", { month: "long", year: "numeric" });
  let cellen = "";
  for (let i = 0; i < leeg; i++) cellen += `<div class="kc leeg"></div>`;
  for (let d = 1; d <= dagen; d++) {
    const iso = `${kalMaand}-${String(d).padStart(2, "0")}`, r = per[iso];
    cellen += `<a class="kc ${r ? (r.netto_eur >= 0 ? "w" : "v") : ""} ${iso === vandaagISO() ? "nu" : ""}" href="/log#${iso}"
      title="${r ? `${r.n} trades · ${eur(r.netto_eur)} · ${pct(r.pct)}` : ""}"><span class="kd">${d}</span>${r ? `<span class="kb">${eur(r.netto_eur).replace("€ ", "")}</span>` : ""}</a>`;
  }
  const tot = Object.values(per).reduce((s, r) => s + r.netto_eur, 0);
  document.getElementById("kalender").innerHTML = `<div class="h2-kal-kop">
    <button class="btn btn-ghost" data-k="-1" type="button">‹</button><b>${naam}</b>
    <span class="${cls(tot)}">${eur(+tot.toFixed(2))}</span><button class="btn btn-ghost" data-k="1" type="button">›</button></div>
    <div class="h2-kal">${["ma", "di", "wo", "do", "vr", "za", "zo"].map((x) => `<div class="kh">${x}</div>`).join("")}${cellen}</div>`;
  document.querySelectorAll("#kalender [data-k]").forEach((b) => b.onclick = () => {
    const d = new Date(j, m - 1 + +b.dataset.k, 1);
    kalMaand = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; renderKalender(); });
}
function renderMaanden() {
  const pm = DATA.per_maand || [], rk = DATA.reeksen || {}, u = DATA.uitschieters || {};
  document.getElementById("maandTabel").innerHTML = `<h3 style="margin:0 0 8px">Per maand</h3>
    <div class="mt-table-wrap"><table class="mt"><thead><tr><th>Maand</th><th class="num">Trades</th><th class="num">Winrate</th>
      <th class="num">R</th><th class="num">Netto</th><th class="num">%</th></tr></thead>
    <tbody>${pm.slice().reverse().map((x) => `<tr><td>${esc(x.label)}</td><td class="num">${x.n}</td><td class="num">${x.winrate}%</td>
      <td class="num ${cls(x.netto_r)}">${r2(x.netto_r)}</td><td class="num ${cls(x.netto_eur)}">${eur(x.netto_eur)}</td>
      <td class="num ${cls(x.pct)}">${pct(x.pct)}</td></tr>`).join("")}</tbody></table></div>
    <div class="h2-feiten">
      <div><span class="hint">Langste winstreeks</span><b>${rk.langste_winstreeks ?? "–"}</b></div>
      <div><span class="hint">Langste verliesreeks</span><b>${rk.langste_verliesreeks ?? "–"}</b></div>
      <div><span class="hint">Nu</span><b>${rk.huidige_winstreeks ? rk.huidige_winstreeks + "× winst" : rk.huidige_verliesreeks ? rk.huidige_verliesreeks + "× verlies" : "–"}</b></div>
      <div><span class="hint">Beste dag</span><b class="pos">${u.beste_dag ? eur(u.beste_dag.netto) + " (" + kort(u.beste_dag.datum) + ")" : "–"}</b></div>
      <div><span class="hint">Slechtste dag</span><b class="neg">${u.slechtste_dag ? eur(u.slechtste_dag.netto) + " (" + kort(u.slechtste_dag.datum) + ")" : "–"}</b></div>
      <div><span class="hint">Payoff</span><b>${u.payoff != null ? nl(u.payoff) : "–"}</b></div>
    </div>${u.aandeel_waarschuwing ? `<p class="hint waarschuwing">${esc(u.aandeel_waarschuwing)}</p>` : ""}`;
}

/* ---------- 9. trades ---------- */
function renderRecent() {
  const r = DATA.recent || [], box = document.getElementById("recentBlok");
  const EM = Object.fromEntries((LOG.emoties || []).map((e) => [e[0], e[1]]));
  box.innerHTML = `<div class="mt-table-wrap"><table class="mt"><thead><tr><th>Datum</th><th>Tijd</th><th>Sessie</th><th>Richting</th>
    <th>Grade</th><th>Regels</th><th>Emotie</th><th>Exit</th><th class="num">R</th><th class="num">Netto</th></tr></thead>
    <tbody>${r.map((t) => `<tr onclick="location.href='/trade?id=${t.id}'">
      <td>${kort(t.datum)}</td><td>${esc(t.tijd || "–")}</td><td>${esc(t.sessie)}</td>
      <td>${t.richting === "long" ? "▲ long" : t.richting === "short" ? "▼ short" : "–"}</td>
      <td>${t.beoordeeld === 0 ? '<span class="h2-open">te loggen</span>' : `<span class="grade-mini g-${t.grade}">${t.grade || "?"}</span>`}</td>
      <td>${t.schoon === 1 ? '<span class="pos">✓</span>' : t.schoon === 0 ? '<span class="neg">✗</span>' : "–"}</td>
      <td>${esc(EM[t.emotie] || "")}</td><td class="hint">${esc(t.exit_reden)}</td>
      <td class="num ${cls(t.r)}">${r2(t.r)}</td><td class="num ${cls(t.netto)}">${eur(t.netto)}</td></tr>`).join("")}</tbody></table></div>
    <p class="hint"><a href="/log">Alle trades in het trading log →</a></p>`;
}

/* ---------- saldo-venster ---------- */
const modal = document.getElementById("saldoModal");
document.getElementById("saldoKnop").onclick = () => { modal.hidden = false; renderSaldo(); };
document.getElementById("saldoDicht").onclick = () => { modal.hidden = true; };
modal.addEventListener("click", (e) => { if (e.target === modal) modal.hidden = true; });

async function renderSaldo() {
  SALDO = await api("/api/saldo");
  const s = SALDO, SOORT = { storting: "↓ storting", opname: "↑ opname", correctie: "± correctie", aansluiting: "⟳ MT5-aansluiting" };
  const mt5 = s.mt5 ? `<div class="h2-mt5-box">MT5-balans <b>${eurKaal(s.mt5.balance)}</b> · equity ${eurKaal(s.mt5.equity)}
      <span class="hint">(${esc(s.mt5.ts.replace("T", " ").slice(0, 16))})</span>
      ${Math.abs(s.verschil_mt5) >= 0.01 ? `<div class="neg">Journal wijkt ${eur(s.verschil_mt5)} af van MT5.</div>` : `<div class="pos">Journal = MT5 ✓</div>`}</div>`
    : `<div class="h2-mt5-box hint">Nog geen MT5-balans gelezen. Zodra de koppeling draait, verschijnt hij hier.</div>`;
  document.getElementById("saldoInhoud").innerHTML = `
    <div class="h2-saldo-opbouw">
      <div><span>Startkapitaal</span><b>${eurKaal(s.startkapitaal)}</b></div>
      <div><span>Stortingen / opnames</span><b>${eur(s.stortingen + s.opnames)}</b></div>
      <div><span>Trading</span><b class="${cls(s.trading_netto)}">${eur(s.trading_netto)}</b></div>
      <div><span>Correcties + aansluiting</span><b>${eur(s.correcties + s.aansluiting)}</b></div>
      <div class="tot"><span>Saldo journal</span><b>${eurKaal(s.saldo)}</b></div>
    </div>${mt5}
    <label class="h2-schakel"><input type="checkbox" id="volgen" ${s.mt5_volgen ? "checked" : ""}>
      <span><b>Saldo automatisch gelijk houden aan MT5</b><br><span class="hint">Stortingen en opnames uit MT5 komen er vanzelf in. Wat daarna nog verschilt
      (testtrades, andere symbolen) wordt per dag als "MT5-aansluiting" geboekt — zichtbaar, en het telt niet als rendement.</span></span></label>
    <div class="h2-formrij">
      <label>Mijn saldo is nu<input type="number" step="0.01" id="fSaldo" value="${s.mt5 ? s.mt5.balance : s.saldo}"></label>
      <button class="btn btn-primary" id="bSaldo" type="button">Gelijkzetten</button>
      <span class="hint">maakt één correctie voor het verschil</span></div>
    <div class="h2-formrij">
      <select id="fSoort"><option value="storting">Storting</option><option value="opname">Opname</option><option value="correctie">Correctie (±)</option></select>
      <input type="number" step="0.01" id="fBedrag" placeholder="bedrag">
      <input type="date" id="fDatum" value="${vandaagISO()}">
      <input type="text" id="fNotitie" placeholder="notitie (optioneel)">
      <button class="btn" id="bKas" type="button">Toevoegen</button></div>
    <div class="h2-formrij"><label>Startkapitaal<input type="number" step="0.01" id="fStart" value="${s.startkapitaal}"></label>
      <button class="btn" id="bStart" type="button">Opslaan</button></div>
    <h4 style="margin:18px 0 6px">Kasstromen</h4>
    <div class="mt-table-wrap"><table class="mt"><thead><tr><th>Datum</th><th>Soort</th><th>Notitie</th><th class="num">Bedrag</th><th></th></tr></thead>
    <tbody>${s.kasstromen.map((k) => `<tr style="cursor:default"><td>${kort(k.datum)} ${esc(k.tijd || "")}</td><td>${SOORT[k.soort] || k.soort}${k.bron === "mt5" ? ' <span class="hint">MT5</span>' : ""}</td>
      <td class="hint" style="white-space:normal">${esc(k.notitie)}</td><td class="num ${cls(k.bedrag)}">${eur(k.bedrag)}</td>
      <td><button class="btn btn-ghost" data-weg="${k.id}" type="button" title="verwijderen">✕</button></td></tr>`).join("") ||
      '<tr><td colspan="5" class="hint">Nog geen kasstromen.</td></tr>'}</tbody></table></div>`;
  const klaar = async () => { await renderSaldo(); herlaadCijfers(); };
  document.getElementById("bSaldo").onclick = async () => {
    await api("/api/saldo/zet", { method: "POST", body: JSON.stringify({ saldo: +document.getElementById("fSaldo").value }) }); klaar(); };
  document.getElementById("bKas").onclick = async () => {
    const b = +document.getElementById("fBedrag").value; if (!b) return;
    await api("/api/kasstroom", { method: "POST", body: JSON.stringify({ soort: document.getElementById("fSoort").value, bedrag: b,
      datum: document.getElementById("fDatum").value, notitie: document.getElementById("fNotitie").value }) }); klaar(); };
  document.getElementById("bStart").onclick = async () => {
    await api("/api/startkapitaal", { method: "PUT", body: JSON.stringify({ startkapitaal: +document.getElementById("fStart").value }) }); klaar(); };
  document.getElementById("volgen").onchange = async (e) => {
    await api("/api/saldo/volgen", { method: "PUT", body: JSON.stringify({ aan: e.target.checked }) }); };
  document.querySelectorAll("#saldoInhoud [data-weg]").forEach((b) => b.onclick = async () => {
    if (!confirm("Deze kasstroom verwijderen?")) return;
    await api("/api/kasstroom/" + b.dataset.weg, { method: "DELETE" }); klaar(); });
}

document.addEventListener("DOMContentLoaded", boot);
