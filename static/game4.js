/* =====================================================================
   CBR Journal · GAME MODE, deel 4 (15 okt 2026, ronde 3: meten hoe je het doet)
     1 processcore per trade (0-100) en de lijn door de tijd
     2 proces tegen uitkomst (vier vakken: verdiend, pech, geluk, verdiend verlies)
     3 lopend gemiddelde R per trade (laatste 20) met 95%-band
     4 onzekerheid in ONTLEED: foutbalken + '?' bij weinig trades
     5 de volgende 50 trades (bootstrap uit je eigen uitkomsten, je echte risico's tegen het plan-%)
     6 instap tegen het plan-niveau (de limiet van de bots op dezelfde setup), in R
     7 hoeveel van de beweging je pakt (MFE tegen resultaat)
     8 tilt-meter (trade-nummer van de dag, na winst/verlies)
     9 klopt je inschatting (grade, uitvoering, opnieuw nemen tegen de uitkomst)
    10 weekscore laatste 12 weken (vijf mini-grafieken)
    11 jij en de bots op dezelfde setup naast elkaar (in 6)
   Alleen lezen. Gebruikt game.js (ALLE, BOTS, K, maak, ...) en game3.js (PLAN, weekMeting).
   ===================================================================== */
"use strict";
const PUNT = 0.10;                                                         // jouw point op XAUUSD
const gem = (a) => a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0;
const sd = (a) => { if (a.length < 2) return 0; const m = gem(a); return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1)); };
const band = (a) => { const m = gem(a), h = a.length > 1 ? 1.96 * sd(a) / Math.sqrt(a.length) : 0; return [m - h, m, m + h]; };
const wilson = (w, n) => { if (!n) return [0, 0]; const p = w / n, z = 1.96, d = 1 + z * z / n, c = p + z * z / (2 * n), s = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return [100 * (c - s) / d, 100 * (c + s) / d]; };
const ROOSTER = { grid: { color: "rgba(18,74,38,.5)" } };

/* ------------------------------------------------------------------ 1. processcore */
function dagNummers() {                                                    // het hoeveelste van de dag + de trade ervoor
  const per = {}, uit = {};
  for (const t of ALLE) (per[t.datum] = per[t.datum] || []).push(t);
  for (const dag of Object.values(per)) dag.forEach((t, i) => uit[t.id] = { nr: i + 1, vorige: dag[i - 1] || null, twee: dag[i - 2] || null });
  return uit;
}
function procesDelen(t, nrs) {
  const plan = (typeof PLAN !== "undefined" ? PLAN.pct : 1), d = [];
  if (t.schoon != null) d.push(["regels gevolgd", t.schoon === 1]);
  if (t.order_soort) d.push(["limiet, geen marktorder", t.order_soort !== "markt"]);
  if (t.sl_verruimd != null) d.push(["SL niet verruimd", !(t.sl_verruimd > 0)]);
  if (t.risico_pct != null) d.push(["risico volgens plan", t.risico_pct >= plan * .5 && t.risico_pct <= plan * 1.5]);
  if (VENSTER[0] && t.tijd) d.push(["in je venster", t.tijd >= VENSTER[0] && t.tijd < VENSTER[1]]);
  if (nrs[t.id]) d.push(["onder je dagmax", nrs[t.id].nr <= MAXDAG]);
  d.push(["gelogd", t.beoordeeld === 1]);
  return d;
}
function procesScore(t, nrs) { const d = procesDelen(t, nrs); return d.length ? Math.round(100 * d.filter((x) => x[1]).length / d.length) : null; }

NA_TEKENEN.push(function tekenProces(T) {
  const nrs = dagNummers(), P = T.map((t) => ({ t, s: procesScore(t, nrs) })).filter((x) => x.s != null);
  if (!P.length) return;
  const lopend = P.map((_, i) => +gem(P.slice(Math.max(0, i - 9), i + 1).map((x) => x.s)).toFixed(0));
  maak("c-proces", { type: "bar", data: { labels: P.map((x) => kort(x.t.datum) + " " + x.t.tijd), datasets: [
      { type: "line", data: lopend, borderColor: K.gold, borderWidth: 2, pointRadius: 0, label: "gemiddeld (10)" },
      { data: P.map((x) => x.s), backgroundColor: P.map((x) => x.t.r > 0 ? "rgba(61,255,138,.55)" : x.t.r < 0 ? "rgba(255,90,79,.55)" : "rgba(111,174,134,.5)"), label: "score" }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => { const p = P[x.dataIndex];
        return x.datasetIndex ? [`#${p.t.id}: score ${p.s} · ${plusR(p.t.r)}`, ...procesDelen(p.t, nrs).filter((d) => !d[1]).map((d) => "✗ " + d[0])] : "gemiddeld " + x.parsed.y; } } } },
      onClick: (e, el) => { const x = el.find((y) => y.datasetIndex === 1); if (x) replay(P[x.index].t.id); },
      scales: { x: { display: false }, y: { min: 0, max: 100, ...ROOSTER } } } });
  const delen = {}; for (const x of P) for (const [n, ok] of procesDelen(x.t, nrs)) { const d = delen[n] = delen[n] || { n: 0, ok: 0 }; d.n++; d.ok += ok; }
  const eerste = gem(P.slice(0, Math.ceil(P.length / 2)).map((x) => x.s)), tweede = gem(P.slice(Math.ceil(P.length / 2)).map((x) => x.s));
  document.getElementById("g-proces-stand").textContent = `nu ${lopend[lopend.length - 1]} · ${tweede >= eerste ? "▲" : "▼"} t.o.v. eerste helft`;
  document.getElementById("g-proces").innerHTML = Object.entries(delen).sort((a, b) => a[1].ok / a[1].n - b[1].ok / b[1].n).map(([n, d]) => { const p = Math.round(100 * d.ok / d.n);
    return `<div class="g-balk"><span>${esc(n)}</span><i style="width:${p * .45}%;background:${p >= 80 ? K.hi : p >= 50 ? K.gold : K.red}"></i><b>${p}%</b><b class="g-dim">(${d.ok}/${d.n})</b></div>`; }).join("");

  /* 2. proces tegen uitkomst */
  const vak = { vg: [], vp: [], vk: [], vv: [] };
  for (const x of P) vak[(x.s >= 70 ? "v" : "v") + (x.s >= 70 ? (x.t.r > 0 ? "g" : "p") : (x.t.r > 0 ? "k" : "v"))].push(x);
  const blok = (k, titel, uitleg, kl) => { const a = vak[k], r = a.reduce((s, x) => s + x.t.r, 0);
    return `<div class="g-vak" style="border-color:${kl}"><div class="g-kop"><b style="color:${kl}">${titel}</b><span>${a.length} · ${plusR(r)}</span></div><div class="g-uitleg">${uitleg}</div>
      <div class="g-vakpunten">${a.map((x) => `<button class="g-chip" data-rp="${x.t.id}" title="score ${x.s} · ${plusR(x.t.r)}">#${x.t.id}</button>`).join("")}</div></div>`; };
  const box = document.getElementById("g-kwadrant");
  box.innerHTML = blok("vg", "GOED PROCES · WINST", "verdiend: zo vaker", K.hi) + blok("vp", "GOED PROCES · VERLIES", "pech: hoort erbij, niets aan doen", K.cyan)
    + blok("vk", "SLECHT PROCES · WINST", "geluk: de gevaarlijkste, dit leert je verkeerde dingen", K.gold) + blok("vv", "SLECHT PROCES · VERLIES", "verdiend verlies: hier zit je winst", K.red);
  box.onclick = (ev) => { const b = ev.target.closest("[data-rp]"); if (b) replay(+b.dataset.rp); };
});

/* ------------------------------------------------------------------ 3. is je voordeel echt */
NA_TEKENEN.push(function tekenRollend(T) {
  const N = 20, rs = T.map((t) => t.r); if (rs.length < 5) { document.getElementById("g-rollend").innerHTML = `<div class="g-uitleg">Te weinig trades.</div>`; return; }
  const b = rs.map((_, i) => band(rs.slice(Math.max(0, i - N + 1), i + 1)));
  maak("c-rollend", { type: "line", data: { labels: T.map((t) => kort(t.datum)), datasets: [
      { data: b.map((x) => +x[2].toFixed(2)), borderColor: "transparent", backgroundColor: "rgba(255,211,107,.15)", fill: "+1", pointRadius: 0, label: "boven" },
      { data: b.map((x) => +x[0].toFixed(2)), borderColor: "transparent", pointRadius: 0, label: "onder" },
      { data: b.map((x) => +x[1].toFixed(2)), borderColor: K.gold, borderWidth: 2, pointRadius: 0, label: "R/trade (20)" },
      { data: rs.map(() => 0), borderColor: K.muted, borderWidth: 1, borderDash: [4, 4], pointRadius: 0, label: "0" }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { filter: (x) => x.datasetIndex === 2,
        callbacks: { label: (x) => { const y = b[x.dataIndex]; return [`${plusR(y[1])} per trade`, `95%: ${plusR(y[0])} tot ${plusR(y[2])}`]; } } } },
      scales: { x: { ticks: { maxTicksLimit: 8 }, grid: { display: false } }, y: ROOSTER } } });
  const heel = band(rs), laatste = b[b.length - 1];
  const oordeel = heel[0] > 0 ? `<b class="g-pos">aangetoond</b>: ook de onderkant van de band ligt boven 0` : heel[2] < 0 ? `<b class="g-neg">negatief</b>: de hele band ligt onder 0`
    : `<b class="g-gold">nog niet aangetoond</b>: de band loopt van ${plusR(heel[0])} tot ${plusR(heel[2])}, 0 zit er nog tussen`;
  const nodig = heel[1] > 0 ? Math.ceil((1.96 * sd(rs) / heel[1]) ** 2) : null;
  document.getElementById("g-rollend").innerHTML = `<div class="g-uitleg">Over alle ${rs.length} trades: ${plusR(heel[1])} per trade, voordeel ${oordeel}.
    ${nodig && nodig > rs.length ? `Bij dit gemiddelde en deze spreiding heb je ongeveer <b class="g-ink">${nodig} trades</b> nodig om het zeker te weten.` : ""}
    Laatste 20: ${plusR(laatste[1])} per trade.</div>`;
});

/* ------------------------------------------------------------------ 4. onzekerheid in ONTLEED */
Chart.register({ id: "foutbalk", afterDatasetsDraw(ch) {
  if (ch.canvas.id !== "c-ontleed" || !["r_gem", "winrate", "r_som"].includes(W.metriek)) return;
  const d = DIM[W.groep], gr = {};
  for (const t of gefilterd()) { const k = d.f(t); (gr[k] = gr[k] || []).push(t); }
  const g = ch.ctx, meta = ch.getDatasetMeta(0), ys = ch.scales.y;
  ch.data.labels.forEach((k, i) => { const a = gr[k] || [], bar = meta.data[i]; if (!bar || !a.length) return;
    let lo, hi;
    if (W.metriek === "winrate") [lo, hi] = wilson(a.filter((t) => t.r > 0).length, a.length);
    else { const b = band(a.map((t) => t.r)), f = W.metriek === "r_som" ? a.length : 1; lo = b[0] * f; hi = b[2] * f; }
    g.save(); g.strokeStyle = "#d8ffe6"; g.lineWidth = 1; const x = bar.x, y1 = ys.getPixelForValue(lo), y2 = ys.getPixelForValue(hi);
    g.beginPath(); g.moveTo(x, y1); g.lineTo(x, y2); g.moveTo(x - 4, y1); g.lineTo(x + 4, y1); g.moveTo(x - 4, y2); g.lineTo(x + 4, y2); g.stroke();
    if (a.length < 10) { g.fillStyle = K.gold; g.font = "14px VT323"; g.fillText("?", x - 3, Math.min(y1, y2) - 4); }
    g.restore(); });
} });

/* ------------------------------------------------------------------ 5. de volgende 50 trades */
let MC_SOORT = "beide";
NA_TEKENEN.push(function tekenMc(T) {
  const seg = document.getElementById("g-mc-soort");
  if (!seg.children.length) { seg.innerHTML = [["beide", "BEIDE"], ["echt", "JOUW RISICO"], ["plan", "PLAN-%"]].map(([k, l]) => `<button data-k="${k}" class="${k === MC_SOORT ? "aan" : ""}">${l}</button>`).join("");
    seg.onclick = (ev) => { const b = ev.target.closest("button"); if (!b) return; MC_SOORT = b.dataset.k; seg.querySelectorAll("button").forEach((x) => x.classList.toggle("aan", x === b)); tekenMc(gefilterd()); }; }
  const bron = T.filter((t) => t.risico_pct != null); if (bron.length < 10) { document.getElementById("g-mc").innerHTML = `<div class="g-uitleg">Minder dan 10 trades met een bekend risico.</div>`; return; }
  const laatste = ALLE[ALLE.length - 1], start = laatste ? laatste.saldo_voor + laatste.netto : START, plan = typeof PLAN !== "undefined" ? PLAN.pct : 1, N = 50, RUNS = 1000;
  let zaad = 12345; const rnd = () => (zaad = (zaad * 1103515245 + 12345) % 2147483648) / 2147483648;     // vast zaad: zelfde plaatje bij elke herteken
  const sim = (soort) => { const paden = [], diep = [];
    for (let r = 0; r < RUNS; r++) { let s = start, piek = start, dd = 0; const pad = [s];
      for (let i = 0; i < N; i++) { const t = bron[Math.floor(rnd() * bron.length)], pct = soort === "echt" ? t.risico_pct : plan;
        s = Math.max(0, s + t.r * pct / 100 * s); piek = Math.max(piek, s); dd = Math.min(dd, s / piek - 1); pad.push(s); }
      paden.push(pad); diep.push(dd); }
    const pc = (q) => Array.from({ length: N + 1 }, (_, i) => { const v = paden.map((p) => p[i]).sort((a, b) => a - b); return +v[Math.floor(q * (RUNS - 1))].toFixed(2); });
    return { p: [.05, .25, .5, .75, .95].map(pc), dd20: diep.filter((d) => d <= -.2).length / RUNS, dd40: diep.filter((d) => d <= -.4).length / RUNS,
      verlies: paden.filter((p) => p[N] < start).length / RUNS }; };
  const E = sim("echt"), Pl = sim("plan"), sets = [];
  const lijnen = (x, kl, naam) => x.p.forEach((d, i) => sets.push({ label: naam + " " + ["5%", "25%", "midden", "75%", "95%"][i], data: d, borderColor: kl,
    borderWidth: i === 2 ? 2.5 : 1, borderDash: i === 2 ? [] : i % 4 === 0 ? [2, 3] : [6, 3], pointRadius: 0 }));
  if (MC_SOORT !== "plan") lijnen(E, K.red, "jouw risico");
  if (MC_SOORT !== "echt") lijnen(Pl, K.cyan, `${nl(plan, 1)}%`);
  maak("c-mc", { type: "line", data: { labels: Array.from({ length: N + 1 }, (_, i) => i), datasets: sets },
    options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } },
      scales: { x: { title: { display: true, text: "trades vanaf nu" }, ticks: { maxTicksLimit: 6 } }, y: { title: { display: true, text: "saldo €" }, ...ROOSTER } } } });
  const rij = (n, x, kl) => `<tr><td style="color:${kl}">${n}</td><td class="n">€${nl(x.p[2][N])}</td><td class="n">€${nl(x.p[0][N])}</td><td class="n">${Math.round(100 * x.dd20)}%</td><td class="n">${Math.round(100 * x.dd40)}%</td><td class="n">${Math.round(100 * x.verlies)}%</td></tr>`;
  document.getElementById("g-mc").innerHTML = `<table class="g-t"><tr><th>NA 50 TRADES (START €${nl(start)})</th><th class="n">MIDDEN</th><th class="n">SLECHT 5%</th><th class="n">KANS -20%</th><th class="n">KANS -40%</th><th class="n">KANS VERLIES</th></tr>
    ${rij("jouw risico's (zoals je ze nam)", E, K.red)}${rij(`elke trade ${nl(plan, 1)}%`, Pl, K.cyan)}</table>
    <div class="g-uitleg">Getrokken uit ${bron.length} trades in je huidige filter. Geen voorspelling: zo wisselvallig zijn jouw eigen uitkomsten.</div>`;
});

/* ------------------------------------------------------------------ 6 + 11. instap tegen het plan, jij en de bots naast elkaar */
function botVan(t) { const b = BOTS[t.v3_sleutel]; if (!b) return null; const x = [b.kampioen, b.uitdager].find((y) => y && y.entry); return x ? { ...x, team: x === b.kampioen ? "kampioen" : "uitdager" } : null; }
NA_TEKENEN.push(function tekenPlanInstap(T) {
  const rij = T.filter((t) => t.v3_sleutel && t.entry && t.sl && botVan(t)).map((t) => { const b = botVan(t), stop = b.sl ? Math.abs(b.entry - b.sl) : Math.abs(t.entry - t.sl);   // R van de plan-stop
    const slechter = t.richting === "long" ? t.entry - b.entry : b.entry - t.entry;
    return { t, b, pts: slechter / PUNT, r: stop ? slechter / stop : 0 }; });
  if (!rij.length) { document.getElementById("g-planinstap").innerHTML = `<div class="g-uitleg">Nog geen trades op een setup waar de bots ook een limiet voor hadden.</div>`; maak("c-planinstap", { type: "bar", data: { labels: [], datasets: [] } }); return; }
  maak("c-planinstap", { type: "bar", data: { labels: rij.map((x) => "#" + x.t.id), datasets: [{ data: rij.map((x) => +x.r.toFixed(2)),
      backgroundColor: rij.map((x) => x.r > .05 ? K.red : x.r < -.05 ? K.hi : K.muted) }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => { const y = rij[x.dataIndex];
        return [`jij ${nl(y.t.entry)} · plan ${nl(y.b.entry)} (${y.b.team})`, `${y.pts >= 0 ? "+" : ""}${nl(y.pts, 1)} points = ${plusR(y.r)} ${y.r > 0 ? "slechter" : "beter"}`, `${esc(y.t.order_soort || "?")}`]; } } } },
      onClick: (e, el) => { if (el.length) replay(rij[el[0].index].t.id); },
      scales: { x: { grid: { display: false } }, y: { title: { display: true, text: "R slechter dan plan" }, ...ROOSTER } } } });
  const markt = rij.filter((x) => x.t.order_soort === "markt"), mnd = new Set(T.map((t) => t.maand)).size || 1, perMnd = T.filter((t) => t.order_soort === "markt").length / mnd;
  const mp = gem(markt.map((x) => x.pts)), mr = gem(markt.map((x) => x.r)), slechter = markt.filter((x) => x.pts > .5).length;
  document.getElementById("g-planinstap").innerHTML = `<div class="g-uitleg">${markt.length ? `Bij je marktorders stapte je gemiddeld <b class="g-ink">${nl(Math.abs(mp), 1)} points ${mp >= 0 ? "slechter" : "beter"}</b>
      in dan het plan (${nl(Math.abs(mr), 2)}R van de plan-stop; ${slechter} van ${markt.length} keer slechter).
      ${mr > 0 ? `Bij ${nl(perMnd, 0)} marktorders per maand kost dat ongeveer <b class="g-neg">${nl(mr * perMnd, 1)}R per maand</b>.` : ""}` : ""}
    Alleen trades met een setup waarop de bots een limiet hadden (${rij.length}).</div>
    <div class="g-tabelvak" style="max-height:200px"><table class="g-t"><tr><th>TRADE</th><th class="n">JIJ IN</th><th class="n">BOT IN</th><th class="n">JIJ SL</th><th class="n">BOT SL</th><th class="n">JIJ</th><th class="n">BOT</th></tr>
    ${rij.slice().reverse().map((x) => `<tr data-rp="${x.t.id}" style="cursor:pointer"><td>#${x.t.id} ${kort(x.t.datum)} ${x.t.richting === "long" ? "▲" : "▼"}</td><td class="n">${nl(x.t.entry)}</td><td class="n">${nl(x.b.entry)}</td>
      <td class="n">${nl(x.t.sl)}</td><td class="n">${nl(x.b.sl)}</td><td class="n ${x.t.r >= 0 ? "g-pos" : "g-neg"}">${plusR(x.t.r)}</td>
      <td class="n">${x.b.r != null ? plusR(x.b.r) : esc(x.b.status)}</td></tr>`).join("")}</table></div>`;
  document.getElementById("g-planinstap").onclick = (ev) => { const r = ev.target.closest("[data-rp]"); if (r) replay(+r.dataset.rp); };
});

/* ------------------------------------------------------------------ 7. hoeveel van de beweging pak je */
NA_TEKENEN.push(function tekenEfficientie(T) {
  const P = T.filter((t) => t.mfe_r != null);
  if (!P.length) { document.getElementById("g-efficientie").innerHTML = `<div class="g-uitleg">Geen MFE-data in deze selectie.</div>`; return; }
  const aangepast = (t) => (t.sl_moves || 0) + (t.tp_moves || 0) > 0, max = Math.max(1, ...P.map((t) => t.mfe_r));
  maak("c-efficientie", { type: "scatter", data: { datasets: [
      { data: P.map((t) => ({ x: t.mfe_r, y: t.r })), backgroundColor: P.map((t) => aangepast(t) ? K.amber : t.r >= 0 ? K.hi : K.red), pointRadius: 4, pointStyle: "rect" },
      { type: "line", data: [{ x: 0, y: 0 }, { x: max, y: max }], borderColor: K.muted, borderDash: [4, 4], borderWidth: 1, pointRadius: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { filter: (x) => x.datasetIndex === 0, callbacks: { label: (x) => { const t = P[x.dataIndex];
        return [`#${t.id}: ging tot ${plusR(t.mfe_r)}, hield ${plusR(t.r)}`, aangepast(t) ? `SL ${t.sl_moves || 0}x, TP ${t.tp_moves || 0}x aangepast` : "niets aangepast"]; } } } },
      onClick: (e, el) => { const x = el.find((y) => y.datasetIndex === 0); if (x) replay(P[x.index].id); },
      scales: { x: { title: { display: true, text: "max in je voordeel (R)" }, min: 0, ...ROOSTER }, y: { title: { display: true, text: "resultaat (R)" }, ...ROOSTER } } } });
  const eff = (a) => { const b = a.filter((t) => t.mfe_r >= .5); return b.length ? Math.round(100 * gem(b.map((t) => Math.max(-1, t.r) / t.mfe_r))) : null; };
  const met = P.filter(aangepast), zonder = P.filter((t) => !aangepast(t) && t.sl_moves != null), terug = P.filter((t) => t.mfe_r >= 1 && t.r <= 0);
  document.getElementById("g-efficientie").innerHTML = `<table class="g-t"><tr><th></th><th class="n">TRADES</th><th class="n">GEPAKT VAN DE BEWEGING</th></tr>
    <tr><td>alle (MFE ≥ 0,5R)</td><td class="n">${P.length}</td><td class="n">${eff(P) ?? "-"}%</td></tr>
    <tr><td class="g-amber">SL/TP aangepast</td><td class="n">${met.length}</td><td class="n">${eff(met) ?? "-"}%</td></tr>
    <tr><td>niets aangepast (MT5)</td><td class="n">${zonder.length}</td><td class="n">${eff(zonder) ?? "-"}%</td></tr></table>
    <div class="g-uitleg">${terug.length ? `<b class="g-neg">${terug.length} trade(s)</b> stonden 1R of meer in de plus en eindigden op 0 of minder.` : "Geen trades die 1R in de plus stonden en toch verloren."}</div>`;
});

/* ------------------------------------------------------------------ 8. tilt-meter */
NA_TEKENEN.push(function tekenTilt(T) {
  const nrs = dagNummers(), groep = {}, zet = (k, t) => (groep[k] = groep[k] || []).push(t);
  for (const t of T) { const n = nrs[t.id]; if (!n) continue; zet(n.nr === 1 ? "1e van de dag" : n.nr === 2 ? "2e van de dag" : "3e of later", t);
    if (!n.vorige) continue; zet(n.vorige.r > 0 ? "na een winst" : "na een verlies", t); if (n.twee && n.vorige.r < 0 && n.twee.r < 0) zet("na 2 verliezen", t); }
  const L = ["1e van de dag", "2e van de dag", "3e of later", "na een winst", "na een verlies", "na 2 verliezen"].filter((k) => groep[k]);
  maak("c-tilt", { type: "bar", data: { labels: L, datasets: [{ data: L.map((k) => +gem(groep[k].map((t) => t.r)).toFixed(2)),
      backgroundColor: L.map((k, i) => (gem(groep[k].map((t) => t.r)) >= 0 ? K.hi : K.red)), borderColor: L.map((k) => k.startsWith("na") ? K.gold : "transparent"), borderWidth: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => { const a = groep[L[x.dataIndex]];
        return [`${plusR(x.parsed.y)} per trade over ${a.length}`, `winrate ${Math.round(100 * a.filter((t) => t.r > 0).length / a.length)}%`]; } } } },
      scales: { x: { grid: { display: false } }, y: { title: { display: true, text: "R per trade" }, ...ROOSTER } } } });
  const e = groep["1e van de dag"], l = groep["2e van de dag"], v = groep["na een verlies"];
  document.getElementById("g-tilt").innerHTML = `<div class="g-uitleg">${e && l ? `Je eerste trade van de dag: ${plusR(gem(e.map((t) => t.r)))} per trade; je tweede: ${plusR(gem(l.map((t) => t.r)))}. ` : ""}
    ${v && v.length >= 3 ? `Na een verlies: ${plusR(gem(v.map((t) => t.r)))} per trade over ${v.length} trades. ` : ""}${L.some((k) => groep[k].length < 10) ? "Groepen onder 10 trades: voorzichtig met conclusies." : ""}</div>`;
});

/* ------------------------------------------------------------------ 9. klopt je inschatting */
NA_TEKENEN.push(function tekenKalibratie(T) {
  const per = (f, volg) => { const g = {}; for (const t of T) { const k = f(t); if (k == null) continue; (g[k] = g[k] || []).push(t); }
    return (volg || Object.keys(g).sort()).filter((k) => g[k]).map((k) => ({ k, a: g[k], r: gem(g[k].map((t) => t.r)), w: Math.round(100 * g[k].filter((t) => t.r > 0).length / g[k].length) })); };
  const gr = per((t) => t.grade && t.grade !== "?" ? t.grade : null), ui = per((t) => t.uitvoering || null, ["1", "2", "3", "4", "5"]),
    op = per((t) => t.opnieuw === 1 ? "ja" : t.opnieuw === 0 ? "nee" : null, ["ja", "nee"]);
  const alle = [...gr.map((x) => ({ ...x, l: "grade " + x.k, kl: K.gold })), ...ui.map((x) => ({ ...x, l: "uitvoering " + x.k, kl: K.cyan })), ...op.map((x) => ({ ...x, l: "opnieuw: " + x.k, kl: K.amber }))];
  maak("c-kalibratie", { type: "bar", data: { labels: alle.map((x) => x.l), datasets: [{ data: alle.map((x) => +x.r.toFixed(2)), backgroundColor: alle.map((x) => x.kl) }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => { const y = alle[x.dataIndex]; return [`${plusR(y.r)} per trade`, `${y.a.length} trades · winrate ${y.w}%`]; } } } },
      scales: { x: { grid: { display: false } }, y: { title: { display: true, text: "R per trade" }, ...ROOSTER } } } });
  const oplopend = (a) => a.length >= 2 && a.every((x, i) => !i || x.r >= a[i - 1].r);
  const gs = gr.filter((x) => x.a.length >= 3), beste = gs.slice().sort((a, b) => b.r - a.r)[0];
  document.getElementById("g-kalibratie").innerHTML = `<div class="g-uitleg">
    ${gs.length >= 2 ? (gs[0].k === beste.k ? `Je grade klopt: <b class="g-pos">${esc(gs[0].k)}</b> doet het het best.` : `Je grade klopt niet: <b class="g-neg">${esc(beste.k)}</b> doet het beter dan ${esc(gs[0].k)}. Kijk wat je bij ${esc(beste.k)} anders beoordeelt.`) : "Te weinig trades per grade."}
    ${ui.length >= 2 ? (oplopend(ui.filter((x) => x.a.length >= 2)) ? " Hogere uitvoering = beter resultaat: je ziet goed hoe je het deed." : " Je cijfer voor uitvoering hangt nog niet samen met je resultaat.") : ""}
    ${op.length === 2 ? ` 'Opnieuw nemen: ja' ${plusR(op[0].r)} tegen 'nee' ${plusR(op[1].r)} per trade.` : ""}</div>`;
});

/* ------------------------------------------------------------------ 10. weekscore laatste 12 weken */
NA_TEKENEN.push(function tekenWeekscore() {
  const box = document.getElementById("g-weekscore"), nrs = dagNummers();
  const weken = [...new Set(ALLE.map((t) => isoWeek(t.datum)))].sort().slice(-12);
  const M = [["processcore", (a) => gem(a.map((t) => procesScore(t, nrs)).filter((x) => x != null)), (v) => Math.round(v), true],
    ["R per trade", (a) => gem(a.map((t) => t.r)), plusR, true],
    ["% limiet", (a) => { const b = a.filter((t) => t.order_soort); return b.length ? 100 * b.filter((t) => t.order_soort !== "markt").length / b.length : null; }, (v) => Math.round(v) + "%", true],
    ["risico-spreiding", (a) => { const p = a.map((t) => t.risico_pct).filter((x) => x != null); return p.length > 1 ? Math.max(...p) / Math.max(.01, Math.min(...p)) : null; }, (v) => "x" + nl(v, 1), false],
    ["% gelogd", (a) => 100 * a.filter((t) => t.beoordeeld === 1).length / a.length, (v) => Math.round(v) + "%", true]];
  if (!box.children.length) box.innerHTML = M.map((m, i) => `<div class="g-ws"><div class="g-kop"><span class="g-lbl">${m[0].toUpperCase()}</span><b id="g-ws-v${i}"></b></div><div style="height:90px"><canvas id="c-ws-${i}"></canvas></div></div>`).join("");
  M.forEach(([naam, f, fmt, hoogGoed], i) => {
    const v = weken.map((w) => { const a = ALLE.filter((t) => isoWeek(t.datum) === w); return a.length ? f(a) : null; }).map((x) => x == null ? null : +x.toFixed(2));
    const echt = v.filter((x) => x != null), nu = echt[echt.length - 1], ervoor = echt.length > 1 ? gem(echt.slice(0, -1)) : null;
    const beter = ervoor == null ? null : hoogGoed ? nu >= ervoor : nu <= ervoor;
    const el = document.getElementById("g-ws-v" + i); el.textContent = nu == null ? "-" : fmt(nu) + (beter == null ? "" : beter ? " ▲" : " ▼"); el.className = beter == null ? "" : beter ? "g-pos" : "g-neg";
    maak("c-ws-" + i, { type: "line", data: { labels: weken.map((w) => "wk " + w.slice(-2)), datasets: [{ data: v, borderColor: K.gold, borderWidth: 2, pointRadius: 2, spanGaps: true, pointStyle: "rect" }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => fmt(x.parsed.y) } } },
        scales: { x: { display: false }, y: { ticks: { maxTicksLimit: 3, font: { size: 10 } }, ...ROOSTER } } } });
  });
});
