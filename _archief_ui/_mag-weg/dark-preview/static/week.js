/* Weekrapport v2.1 — progressie per week. Alles uit /api/weekrapport. */
const K = { groen: "#089981", rood: "#f23645", plum: "#4c7dff", plumLicht: "rgba(76,125,255,.28)", grid: "rgba(120,123,134,.15)", tick: "#787b86" };
const nl = (n, d = 2) => Number(n).toFixed(d).replace(".", ",");
const eur = (n) => (n == null ? "–" : "€ " + (n >= 0 ? "+" : "−") + nl(Math.abs(n)));
const r2 = (n) => (n == null ? "–" : (n >= 0 ? "+" : "") + nl(n) + "R");
const cls = (n) => (n > 0 ? "pos" : n < 0 ? "neg" : "");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const kort = (d) => { const [, m, dd] = d.split("-"); return `${+dd}/${+m}`; };
const EMO = { rustig: "😌 rustig", gefocust: "🎯 gefocust", twijfel: "🤔 twijfel", gehaast: "⏱ gehaast", fomo: "😬 FOMO", revenge: "😤 revenge", moe: "😴 moe" };
const charts = {};
let W = null;

function datumParam() { return new URLSearchParams(location.search).get("datum") || ""; }

async function laad(datum) {
  W = await api("/api/weekrapport" + (datum ? "?datum=" + datum : ""));
  history.replaceState(null, "", "/week" + (datum ? "?datum=" + datum : ""));
  document.getElementById("titel").textContent = `Week ${W.week} · ${W.bereik} ${W.jaar}`;
  const m = W.meting;
  document.getElementById("sub").textContent = m.n
    ? `${m.n} trades over ${m.handelsdagen} handelsdagen · ${m.gelogd_pct ?? 0}% gelogd`
    : "Geen trades deze week.";
  document.getElementById("pdf").href = "/api/weekrapport.pdf?datum=" + W.maandag;
  renderKpi(); renderFocus(); renderProg(); renderDagen(); renderTrades(); renderLessen();
}

function delta(k, fmt) {
  const d = W.deltas[k];
  if (!d) return `<div class="mt-sub">–</div>`;
  const c = d.beter ? "pos" : d.beter === false ? "neg" : "";
  const pijl = d.delta > 0 ? "▲" : d.delta < 0 ? "▼" : "•";
  return `<div class="mt-sub ${c}">${pijl} ${fmt(d.delta)} vs vorige week</div>`;
}
function renderKpi() {
  const m = W.meting;
  const p = (v, s = "%") => (v == null ? "–" : v + s);
  const cellen = [
    ["Netto", eur(m.netto_eur), cls(m.netto_eur), delta("netto_eur", eur)],
    ["Resultaat", r2(m.netto_r), cls(m.netto_r), delta("netto_r", r2)],
    ["Winrate", p(m.winrate), "", delta("winrate", (x) => (x > 0 ? "+" : "") + x + "%")],
    ["Expectancy", r2(m.expectancy_r), cls(m.expectancy_r), delta("expectancy_r", r2)],
    ["Proces-score", p(m.proces_score), "", delta("proces_score", (x) => (x > 0 ? "+" : "") + x + "%")],
    ["Regels gevolgd", p(m.schoon_pct), "", delta("schoon_pct", (x) => (x > 0 ? "+" : "") + x + "%")],
    ["Goede staat vooraf", p(m.goede_staat_pct), "", delta("goede_staat_pct", (x) => (x > 0 ? "+" : "") + x + "%")],
    ["Uitvoering", m.uitvoering != null ? nl(m.uitvoering, 1) + "/5" : "–", "", delta("uitvoering", (x) => (x > 0 ? "+" : "") + nl(x, 1))],
  ];
  document.getElementById("kpi").innerHTML = `<div class="mt-bar">${cellen.map(([k, v, c, d], i) => `
    <div class="mt-cell${i === 4 ? " accent" : ""}"><div class="k">${k}</div><div class="val ${c}">${v}</div>${d}</div>`).join("")}</div>`;
}
function renderFocus() {
  const f = W.focus;
  document.getElementById("focus").innerHTML = `<div class="h2-blok-titel">Focus voor volgende week</div>
    <h3 style="margin:4px 0">${esc(f.titel)}</h3><p style="margin:0 0 6px">${esc(f.tekst)}</p><span class="hint">${esc(f.bron || "")}</span>`;
  const s = W.sterk || [];
  const b = W.beste, l = W.leerzaam;
  document.getElementById("sterk").innerHTML = `<div class="h2-blok-titel">Wat ging goed</div>
    ${s.length ? `<ul class="wk2-lijst">${s.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="hint">Nog weinig om te vergelijken — log elke trade.</p>`}
    ${b ? `<p style="margin:8px 0 0">⭐ Beste trade: <a href="/trade?id=${b.id}">#${b.id} ${kort(b.datum)} ${b.tijd}</a> — grade ${b.grade}, ${r2(b.r)}</p>` : ""}
    ${l ? `<p style="margin:4px 0 0">🔍 Leerzaamste: <a href="/trade?id=${l.id}">#${l.id} ${kort(l.datum)} ${l.tijd}</a> — proces ${l.proces_score ?? "–"}%</p>` : ""}`;
}
function mini(id, key, eenheid, polar) {
  const w = W.progressie || [];
  const vals = w.map((x) => x[key]);
  const kleur = w.map((x, i) => {
    const nu = x.maandag === W.maandag, v = vals[i];
    if (polar) return nu ? (v >= 0 ? K.groen : K.rood) : (v >= 0 ? "rgba(8,153,129,.35)" : "rgba(242,54,69,.35)");
    return nu ? K.plum : K.plumLicht;
  });
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), {
    type: "bar",
    data: { labels: w.map((x) => "wk " + x.week), datasets: [{ data: vals, backgroundColor: kleur, borderRadius: 3, maxBarThickness: 26 }] },
    options: { responsive: true, maintainAspectRatio: false, animation: false,
      onClick: (e, el) => { if (el.length) laad(w[el[0].index].maandag); },
      plugins: { legend: { display: false }, tooltip: { callbacks: {
        title: (it) => `Week ${w[it[0].dataIndex].week} · ${w[it[0].dataIndex].bereik}`,
        label: (c) => (c.parsed.y == null ? "geen data" : (polar ? r2(c.parsed.y) : c.parsed.y + eenheid) + ` · ${w[c.dataIndex].n} trades`) } } },
      scales: { x: { grid: { display: false }, ticks: { color: K.tick, font: { size: 10 }, maxRotation: 0, autoSkip: true } },
        y: { grid: { color: K.grid }, ticks: { color: K.tick, font: { size: 10 }, maxTicksLimit: 4 }, ...(polar ? {} : { min: 0, max: 100 }) } } },
  });
}
function renderProg() {
  mini("pR", "netto_r", "R", true); mini("pProces", "proces_score", "%"); mini("pWin", "winrate", "%");
  mini("pSchoon", "schoon_pct", "%"); mini("pStaat", "goede_staat_pct", "%"); mini("pVenster", "venster_pct", "%");
}
function renderDagen() {
  const d = W.dagen || [];
  document.getElementById("dagen").innerHTML = d.length ? `<div class="wk2-dagen">${d.map((x) => `
    <div class="wk2-dag ${x.netto_eur >= 0 ? "w" : "v"}"><div class="hint">${x.weekdag}</div><b>${kort(x.datum)}</b>
      <div class="${cls(x.netto_eur)}" style="font-size:18px;font-weight:700">${eur(x.netto_eur)}</div>
      <div class="hint">${x.n} trades · ${x.winrate}% · ${r2(x.netto_r)}</div></div>`).join("")}</div>`
    : `<p class="hint">Geen handelsdagen deze week.</p>`;
}
function renderTrades() {
  const t = W.trades || [];
  document.getElementById("nTrades").textContent = t.length ? `(${t.length})` : "";
  document.getElementById("trades").innerHTML = t.map((x) => `
    <a class="panel wk2-trade ${x.beoordeeld === 0 ? "open" : ""}" href="/trade?id=${x.id}">
      ${x.chart ? `<img src="${x.chart}" loading="lazy" alt="chart">` : `<div class="wk2-geen">geen chart</div>`}
      <div class="wk2-trade-kop"><b>${x.richting === "long" ? "▲" : "▼"} ${kort(x.datum)} ${esc(x.tijd || "")}</b>
        <span class="grade-mini g-${x.grade}">${x.beoordeeld === 0 ? "?" : x.grade}</span></div>
      <div class="wk2-trade-feit"><b class="${cls(x.netto)}">${eur(x.netto)}</b> <span class="${cls(x.r)}">${r2(x.r)}</span>
        ${x.proces_score != null ? `<span class="hint">proces ${x.proces_score}%</span>` : ""}</div>
      <div class="hint">${esc(x.sessie || "")}${x.emotie ? " · " + (EMO[x.emotie] || x.emotie) : ""}${x.schoon === 1 ? " · ✓ regels" : x.schoon === 0 ? " · ✗ regel gebroken" : ""}</div>
      ${x.beoordeeld === 0 ? `<div class="h2-open" style="margin-top:6px;display:inline-block">nog loggen</div>` : ""}
      ${!x.sl_bekend ? `<div class="neg" style="font-size:11px;margin-top:4px">SL/TP onbekend</div>` : ""}
      ${x.les ? `<div class="wk2-les">“${esc(x.les)}”</div>` : ""}
    </a>`).join("") || `<p class="hint">Geen trades.</p>`;
}
function renderLessen() {
  const l = W.lessen || [], a = W.auto_fouten || [];
  document.getElementById("lessen").innerHTML = `<div class="h2-blok-titel">Je lessen</div>` + (l.length
    ? `<ul class="wk2-lijst">${l.map((x) => `<li><a href="/trade?id=${x.id}">#${x.id}</a> ${esc(x.les)}</li>`).join("")}</ul>`
    : `<p class="hint">Nog geen lessen. Vul bij het loggen één zin in — dat is de goedkoopste les die je krijgt.</p>`);
  document.getElementById("auto").innerHTML = `<div class="h2-blok-titel">Automatisch gevonden</div>` + (a.length
    ? a.map((x) => `<div class="h2-fout" style="margin-bottom:8px"><div class="h2-fout-kop"><b>${esc(x.label)}</b><span class="neg">${x.aantal}× · ${x.pct}%</span></div><div class="hint">${esc(x.correctie || "")}</div></div>`).join("")
    : `<p class="hint pos">Geen automatische fouten deze week.</p>`);
}
document.getElementById("vorige").onclick = () => laad(W.vorige_maandag);
document.getElementById("volgende").onclick = () => laad(W.volgende_maandag);
document.addEventListener("DOMContentLoaded", () => laad(datumParam()));
