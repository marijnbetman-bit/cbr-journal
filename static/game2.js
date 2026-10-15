/* =====================================================================
   CBR Journal · GAME MODE, deel 2 (journal v2, 15 okt 2026): de voorstellen 1-10
     1 wat als je niets had aangeraakt          2 exit-simulator           3 gemiste kansen + afgeblazen orders
     4 tweede mening (modelkans, ook in ONTLEED) 5 live cockpit in de HUD   6 kosten en spread in R
     7 nieuws-impact                             8 zwevend verloop (equity) 9 telefoonweergave (gamepagina.css)
    10 quests, bossfight, 8-bit geluid, level-up
   Plus: wat het journal uit CBR Station haalt (dagrapport, lessen, doelen).
   Haakt in op game.js (NA_TEKENEN, DIM, cockpitHtml, extraBoot). Alleen lezen.
   ===================================================================== */
"use strict";
let SIM = null, GEMIST = null, ACCOUNT = null, NIEUWS = [], MARKT = null, RAPPORT = null, DOELEN = null;
const KLANK = { aan: (() => { try { return localStorage.getItem("cbr_geluid") === "aan"; } catch (e) { return false; } })() };

async function extraBoot() {
  const van = ALLE.length ? ALLE[0].datum : vandaagISO();
  const morgen = (() => { const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().slice(0, 10); })();
  haal("/api/game/simulatie").then((d) => { SIM = d; voegSimDimToe(); tekenAlles(); }).catch(() => {});
  haal("/api/game/gemist?dagen=30").then((d) => { GEMIST = d; tekenGemist(); }).catch(() => {});
  haal("/api/game/account?dagen=30").then((d) => { ACCOUNT = d; tekenZwevend(gefilterd()); }).catch(() => {});
  haal(`/api/game/station/nieuws?van=${van}&tot=${morgen}`).then((d) => {
    NIEUWS = ((d && d.nieuws) || []).filter((n) => n.land === "USD" && /high/i.test(n.impact || "")); tekenAlles(); }).catch(() => {});
  haal("/api/game/station/rapporten").then((d) => { RAPPORT = d && !d.error ? d : null; tekenStation(); }).catch(() => {});
  haal("/api/game/station/doelen").then((d) => { DOELEN = d && !d.error ? d.doelen : null; tekenStation(); }).catch(() => {});
  cockpitLus();
  levelUpCheck(); nieuweTpCheck();
  document.getElementById("g-boss-instel").onclick = bossInstellen;
  document.getElementById("g-hud").addEventListener("click", (ev) => {
    if (ev.target.closest("[data-geluid]")) { KLANK.aan = !KLANK.aan; try { localStorage.setItem("cbr_geluid", KLANK.aan ? "aan" : "uit"); } catch (e) {}
      if (KLANK.aan) piep("munt"); tekenHud(); }
  });
}

/* ------------------------------------------------------------------ 4, 6, 7: extra dimensies in ONTLEED */
const kansVan = (t) => { const b = BOTS[t.v3_sleutel]; const x = b && (b.uitdager || b.kampioen); return x && x.kans != null ? x.kans : null; };
const rondNieuws = (t) => { if (!t.tijd || !NIEUWS.length) return null; const ts = new Date(t.datum + "T" + t.tijd + ":00").getTime() / 1000;
  return NIEUWS.find((n) => Math.abs(n.ts - ts) <= 15 * 60) || null; };
DIM.modelkans = { naam: "MODELKANS (TWEEDE MENING)", f: (t) => { const k = kansVan(t); return k == null ? "geen modelkans" : k < .3 ? "model: < 30%" : k < .5 ? "model: 30-50%" : "model: ≥ 50%"; },
  volgorde: ["model: < 30%", "model: 30-50%", "model: ≥ 50%", "geen modelkans"] };
DIM.nieuws = { naam: "ROND HIGH-IMPACT NIEUWS", f: (t) => NIEUWS.length ? (rondNieuws(t) ? "binnen 15 min van nieuws" : "geen nieuws") : "nog geen nieuwsdata" };
DIM.kosten = { naam: "KOSTEN + SPREAD (R)", f: (t) => { const k = (t.kosten_r || 0) + (t.spread_r || 0); return t.kosten_r == null && t.spread_r == null ? "?" : k < .05 ? "< 0,05R" : k < .1 ? "0,05-0,10R" : k < .2 ? "0,10-0,20R" : "> 0,20R"; },
  volgorde: ["< 0,05R", "0,05-0,10R", "0,10-0,20R", "> 0,20R", "?"] };
function voegSimDimToe() {
  const per = Object.fromEntries((SIM.trades || []).map((x) => [x.id, x]));
  DIM.watals = { naam: "BEHEER T.O.V. NIETS AANRAKEN", f: (t) => { const x = per[t.id]; return !x ? "geen candles" : x.delta > .05 ? "beheer leverde op" : x.delta < -.05 ? "beheer kostte" : "maakte niet uit"; } };
  const g = document.getElementById("g-groep"); if (g && !g.querySelector('option[value="watals"]')) g.insertAdjacentHTML("beforeend", `<option value="watals">${DIM.watals.naam}</option>`);
}

/* ------------------------------------------------------------------ 1. wat als je niets had aangeraakt */
function simVan(T) { const ids = new Set(T.map((t) => t.id)); return (SIM && SIM.trades || []).filter((x) => ids.has(x.id)); }
NA_TEKENEN.push(function tekenWatals(T) {
  const el = document.getElementById("g-watals"); if (!el) return;
  if (!SIM) { el.innerHTML = `<div class="g-uitleg">Rekenen op de candles...</div>`; return; }
  const S = simVan(T); if (!S.length) { el.innerHTML = `<div class="g-uitleg">Geen trades met candles in deze selectie.</div>`; return; }
  const echt = S.reduce((s, x) => s + x.r, 0), plan = S.reduce((s, x) => s + x.plan_r, 0), d = echt - plan, max = Math.max(1, Math.abs(echt), Math.abs(plan));
  const op = S.filter((x) => x.delta > .05).sort((a, b) => b.delta - a.delta), af = S.filter((x) => x.delta < -.05).sort((a, b) => a.delta - b.delta);
  const lijst = (xs) => xs.slice(0, 5).map((x) => `<tr class="klik" data-id="${x.id}"><td>#${x.id} ${kort(x.datum)} ${x.tijd}</td><td class="n">${plusR(x.r)}</td>
    <td class="n g-dim">${plusR(x.plan_r)} (${x.plan_uitkomst})</td><td class="n ${x.delta >= 0 ? "g-pos" : "g-neg"}">${plusR(x.delta)}</td></tr>`).join("");
  el.innerHTML = `<div class="g-balk"><span>wat je echt haalde</span><i style="width:${45 * Math.abs(echt) / max}%;background:${echt >= 0 ? K.hi : K.red}"></i><b>${plusR(echt)}</b></div>
    <div class="g-balk"><span>niets aangeraakt</span><i style="width:${45 * Math.abs(plan) / max}%;background:${K.cyan}"></i><b>${plusR(plan)}</b></div>
    <p style="font-size:22px;margin:6px 0">Je beheer ${d >= 0 ? "leverde" : "kostte"} <b class="${d >= 0 ? "g-pos" : "g-neg"}">${plusR(Math.abs(d)).replace("+", "")}</b> over ${S.length} trades
      <span class="g-dim">(${op.length}× hielp het, ${af.length}× kostte het)</span></p>
    <table class="g-t"><tr><th>KOSTTE HET MEEST</th><th class="n">JIJ</th><th class="n">PLAN</th><th class="n">VERSCHIL</th></tr>${lijst(af) || '<tr><td colspan="4" class="g-dim">-</td></tr>'}</table>
    <table class="g-t" style="margin-top:6px"><tr><th>HIELP HET MEEST</th><th class="n">JIJ</th><th class="n">PLAN</th><th class="n">VERSCHIL</th></tr>${lijst(op) || '<tr><td colspan="4" class="g-dim">-</td></tr>'}</table>
    <div class="g-uitleg">${esc(SIM.regel)}</div>`;
  el.onclick = (ev) => { const r = ev.target.closest("tr[data-id]"); if (r) replay(+r.dataset.id); };
});

/* ------------------------------------------------------------------ 2. exit-simulator */
NA_TEKENEN.push(function tekenExits(T) {
  if (!SIM) return;
  const S = simVan(T); if (!S.length) return;
  const namen = ["1R", "1,5R", "2R", "3R", "BE na 1R, TP 3R", "50% expansie"];
  const rij = [["JIJ (ECHT)", S.reduce((s, x) => s + x.r, 0), S.length, S.filter((x) => x.r > 0).length, K.ink],
               ["NIETS AANRAKEN", S.reduce((s, x) => s + x.plan_r, 0), S.length, S.filter((x) => x.plan_r > 0).length, K.cyan]]
    .concat(namen.map((n) => { const v = S.map((x) => x.var[n]).filter((x) => x != null); return [n.toUpperCase(), v.reduce((a, b) => a + b, 0), v.length, v.filter((x) => x > 0).length, K.gold]; }))
    .filter((r) => r[2]);
  maak("c-exits", { type: "bar", data: { labels: rij.map((r) => r[0]), datasets: [{ data: rij.map((r) => +r[1].toFixed(2)), backgroundColor: rij.map((r) => r[1] >= 0 ? r[4] : K.red) }] },
    options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => { const r = rij[x.dataIndex];
        return [`${plusR(r[1])} over ${r[2]} trades`, `winrate ${Math.round(100 * r[3] / r[2])}% · ${plusR(r[1] / r[2])} per trade`]; } } } },
      scales: { x: { grid: { color: "rgba(18,74,38,.5)" } }, y: { grid: { display: false }, ticks: { autoSkip: false } } } } });
  const beste = rij.slice(2).sort((a, b) => b[1] - a[1])[0];
  document.getElementById("g-exits-tekst").innerHTML = beste ? `Beste vaste regel in deze selectie: <b class="g-gold">${beste[0]}</b> (${plusR(beste[1])}). ` +
    `Let op: achteraf gekozen en op weinig trades; zie het als inzicht, niet als nieuwe regel. 50% expansie alleen bij trades met een vastgelegd expansie-begin.` : "";
});

/* ------------------------------------------------------------------ 3. gemiste kansen en afgeblazen orders */
function tekenGemist() {
  const el = document.getElementById("g-gemist"), eo = document.getElementById("g-orders"); if (!el || !GEMIST) return;
  const G = GEMIST.gemist || [], gev = G.filter((g) => g.r != null), som = gev.reduce((s, g) => s + g.r, 0);
  document.getElementById("g-gemist-status").textContent = `laatste ${GEMIST.dagen} dagen · venster ${GEMIST.venster.join("-")}` + (GEMIST.station ? "" : " · station niet bereikbaar");
  el.innerHTML = `<div class="g-lbl">SETUPS IN JE VENSTER DIE JE NIET NAM</div>` + (GEMIST.station ? `
    <p style="font-size:20px;margin:4px 0"><b class="g-gold">${G.length}</b> setups · ${gev.length} zouden gevuld zijn · op papier (1:1) <b class="${som >= 0 ? "g-pos" : "g-neg"}">${plusR(som)}</b></p>
    ${[["model ≥ 50%", (g) => g.kans != null && g.kans >= .5], ["model 30-50%", (g) => g.kans != null && g.kans >= .3 && g.kans < .5], ["model < 30%", (g) => g.kans != null && g.kans < .3]].map(([n, f]) => {
      const xs = gev.filter(f), r = xs.reduce((s, g) => s + g.r, 0), w = xs.filter((g) => g.r > 0).length;
      return xs.length ? `<div class="g-balk"><span>${n} (${xs.length})</span><i style="width:${Math.min(45, 3 * Math.abs(r))}%;background:${r >= 0 ? K.hi : K.red}"></i><b>${plusR(r)} · winrate ${Math.round(100 * w / xs.length)}%</b></div>` : ""; }).join("")}
    <div class="g-tabelvak" style="max-height:200px"><table class="g-t"><tr><th>WANNEER</th><th>RICHTING</th><th class="n">KANS</th><th>BOTS</th><th class="n">PAPIER</th></tr>
    ${G.slice().reverse().map((g) => `<tr><td>${kort(g.datum)} ${g.tijd}</td><td>${g.richting === "long" ? "▲" : "▼"}</td><td class="n g-cyan">${g.kans == null ? "-" : Math.round(100 * g.kans) + "%"}</td>
      <td class="g-dim">${esc(Object.values(g.bots).join("/"))}</td><td class="n ${g.r == null ? "g-dim" : g.r >= 0 ? "g-pos" : "g-neg"}">${g.r == null ? esc(g.uitkomst) : plusR(g.r)}</td></tr>`).join("")}</table></div>`
    : `<div class="g-uitleg">Komt zodra CBR Station bereikbaar is.</div>`) +
    `<div class="g-lbl" style="margin-top:8px">TRADES ZONDER SETUP (sinds de setup-koppeling)</div>` +
    `<p style="margin:2px 0">${GEMIST.zonder_setup.length} trades · ${plusR(GEMIST.zonder_setup.reduce((s, t) => s + t.r, 0))}</p>`;
  const O = GEMIST.orders || [], weg = O.filter((o) => o.gevolgd_door);
  const dv = weg.filter((o) => o.gevolgd_door.verschil_points != null);
  eo.innerHTML = `<div class="g-lbl">LIMIETORDERS DIE NOOIT GEVULD WERDEN (MT5)</div>` + (O.length ? `
    <p style="font-size:20px;margin:4px 0"><b class="g-gold">${O.length}</b> orders · gemiddeld na ${nl(O.reduce((s, o) => s + (o.duur_min || 0), 0) / O.length, 1)} min weggehaald</p>
    ${weg.length ? `<p class="g-neg" style="margin:2px 0">${weg.length}× limiet weggehaald en binnen 3 min tóch ingestapt${dv.length ? `, gemiddeld ${nl(dv.reduce((s, o) => s + o.gevolgd_door.verschil_points, 0) / dv.length, 1)} points slechter dan je limiet` : ""}
      → samen ${plusR(weg.reduce((s, o) => s + (o.gevolgd_door.r || 0), 0))}</p>` : ""}
    <div class="g-tabelvak" style="max-height:200px"><table class="g-t"><tr><th>GEPLAATST</th><th>SOORT</th><th class="n">PRIJS</th><th>STATUS</th><th class="n">NA</th><th>DAARNA</th></tr>
    ${O.slice().reverse().map((o) => `<tr><td>${esc((o.geplaatst || "").slice(5))}</td><td>${esc(o.soort)}</td><td class="n">${nl(o.prijs)}</td><td>${esc(o.status)}</td>
      <td class="n">${o.duur_min == null ? "-" : nl(o.duur_min, 1) + "m"}</td><td>${o.gevolgd_door ? (() => { const v = o.gevolgd_door.verschil_points;
        return `<span class="${v == null ? "g-gold" : v > 0 ? "g-neg" : "g-pos"}">#${o.gevolgd_door.id} markt${v == null ? "" : " " + nl(Math.abs(v), 1) + " pts " + (v > 0 ? "slechter" : "beter")}</span>`; })() : ""}</td></tr>`).join("")}</table></div>`
    : `<div class="g-uitleg">Nog geen niet-gevulde orders bekend. De MT5-koppeling haalt ze vanaf nu elke ronde op.</div>`);
}

/* ------------------------------------------------------------------ 8. zwevend + 6/7 kosten, spread, nieuws */
function tekenZwevend(T) {
  if (ACCOUNT && ACCOUNT.punten && ACCOUNT.punten.length) {
    const p = ACCOUNT.punten;
    maak("c-equity", { type: "line", data: { labels: p.map((x) => x[0].slice(5, 16).replace("T", " ")), datasets: [
        { label: "balans", data: p.map((x) => x[1]), borderColor: K.muted, borderWidth: 1.5, pointRadius: 0, stepped: true },
        { label: "equity", data: p.map((x) => x[2]), borderColor: K.cyan, borderWidth: 2, pointRadius: 0, fill: { target: 0, above: "rgba(61,255,138,.15)", below: "rgba(255,90,79,.25)" } }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, labels: { boxWidth: 10 } } }, scales: { x: { ticks: { maxTicksLimit: 6 }, grid: { display: false } }, y: { grid: { color: "rgba(18,74,38,.5)" } } } } });
  }
  const diep = T.filter((t) => t.zwevend_min_eur != null).sort((a, b) => a.zwevend_min_eur - b.zwevend_min_eur).slice(0, 5);
  document.getElementById("g-zwevend").innerHTML = diep.length ? `<table class="g-t"><tr><th>DIEPSTE MOMENT</th><th class="n">ZWEVEND</th><th class="n">IN R</th><th class="n">EINDE</th></tr>` +
    diep.map((t) => `<tr class="klik" data-id="${t.id}"><td>#${t.id} ${kort(t.datum)} ${t.tijd}</td><td class="n g-neg">€${nl(t.zwevend_min_eur)}</td>
      <td class="n">${t.risico_eur ? plusR(t.zwevend_min_eur / t.risico_eur) : "-"}</td><td class="n ${t.r >= 0 ? "g-pos" : "g-neg"}">${plusR(t.r)}</td></tr>`).join("") + `</table>` : "";
  document.getElementById("g-zwevend").onclick = (ev) => { const r = ev.target.closest("tr[data-id]"); if (r) replay(+r.dataset.id); };
}
NA_TEKENEN.push(tekenZwevend);
NA_TEKENEN.push(function tekenKosten(T) {
  const k = T.filter((t) => t.kosten_r != null), s = T.filter((t) => t.spread_r != null);
  const gem = (xs, f) => xs.length ? xs.reduce((a, t) => a + f(t), 0) / xs.length : null;
  const bruto = T.reduce((a, t) => a + t.r, 0), kost = k.reduce((a, t) => a + t.kosten_r, 0);
  document.getElementById("g-kosten").innerHTML = `<div class="g-lbl">KOSTEN EN SPREAD</div>
    <div class="g-kpis" style="margin:4px 0 8px"><div class="g-kpi"><b>${gem(k, (t) => t.kosten_r) == null ? "-" : nl(gem(k, (t) => t.kosten_r), 3) + "R"}</b><span>KOSTEN PER TRADE</span></div>
      <div class="g-kpi"><b>${gem(s, (t) => t.spread_r) == null ? "-" : nl(gem(s, (t) => t.spread_r), 3) + "R"}</b><span>SPREAD BIJ ENTRY</span></div>
      <div class="g-kpi ${kost > 0 ? "neg" : ""}"><b>${nl(kost)}R</b><span>KOSTEN SAMEN (${k.length} TR)</span></div></div>
    <div class="g-uitleg">Kosten in R = commissie gedeeld door je risico. Bij een krappe SL wegen kosten zwaarder: ${(() => { const kl = k.filter((t) => (t.sl_points || 99) < 12), gr = k.filter((t) => (t.sl_points || 0) >= 12);
      return kl.length && gr.length ? `SL < 12 points: ${nl(gem(kl, (t) => t.kosten_r), 3)}R per trade, SL ≥ 12: ${nl(gem(gr, (t) => t.kosten_r), 3)}R.` : "te weinig trades om te splitsen."; })()}</div>`;
  const rond = T.filter((t) => rondNieuws(t)), los = T.filter((t) => !rondNieuws(t));
  document.getElementById("g-nieuws").innerHTML = `<div class="g-lbl" style="margin-top:10px">ROND HIGH-IMPACT USD-NIEUWS (± 15 MIN)</div>` + (NIEUWS.length ?
    `<div class="g-balk"><span>rond nieuws (${rond.length})</span><i style="width:${Math.min(45, 15 * Math.abs(gem(rond, (t) => t.r) || 0))}%;background:${(gem(rond, (t) => t.r) || 0) >= 0 ? K.hi : K.red}"></i><b>${rond.length ? plusR(gem(rond, (t) => t.r)) + " per trade" : "-"}</b></div>
     <div class="g-balk"><span>zonder nieuws (${los.length})</span><i style="width:${Math.min(45, 15 * Math.abs(gem(los, (t) => t.r) || 0))}%;background:${(gem(los, (t) => t.r) || 0) >= 0 ? K.hi : K.red}"></i><b>${los.length ? plusR(gem(los, (t) => t.r)) + " per trade" : "-"}</b></div>
     ${rond.slice(-4).map((t) => `<div class="g-uitleg">#${t.id} ${kort(t.datum)} ${t.tijd}: ${esc(rondNieuws(t).titel)} (${rondNieuws(t).tijd.slice(11)}) → ${plusR(t.r)}</div>`).join("")}`
    : `<div class="g-uitleg">Nieuwsagenda uit CBR Station nog niet geladen (komt na de herstart van het station).</div>`);
});

/* ------------------------------------------------------------------ uit CBR Station */
function tekenStation() {
  const a = document.getElementById("g-station-rapport"), b = document.getElementById("g-station-doelen"); if (!a) return;
  const lo = RAPPORT && RAPPORT.lopend;
  a.innerHTML = lo ? `<div class="g-lbl">${esc(lo.titel.toUpperCase())} (BEDRIJF)</div>${lo.zinnen.map((z) => `<div class="g-uitleg" style="color:var(--g-ink)">${esc(z)}</div>`).join("")}
    ${lo.lessen && lo.lessen.zinnen && lo.lessen.zinnen.length ? `<div class="g-lbl" style="margin-top:6px">WAT HET BEDRIJF LEERT</div>${lo.lessen.zinnen.map((z) => `<div class="g-uitleg">· ${esc(z)}</div>`).join("")}` : ""}`
    : `<div class="g-uitleg">Dagrapport van CBR Station niet bereikbaar.</div>`;
  b.innerHTML = DOELEN ? `<div class="g-lbl">DOELEN VAN HET BEDRIJF</div>` + DOELEN.map((d) => `<div class="g-balk"><span>${esc(d.titel)}</span><i style="width:${Math.max(1, .45 * d.pct)}%;background:${d.gehaald ? K.hi : K.gold}"></i><b>${esc(d.waarde)}/${esc(d.doel)}</b></div>`).join("") : "";
}

/* ------------------------------------------------------------------ 5. live cockpit in de HUD */
function inVenster() { const n = new Date(), hm = String(n.getHours()).padStart(2, "0") + ":" + String(n.getMinutes()).padStart(2, "0"); return VENSTER[0] && hm >= VENSTER[0] && hm < VENSTER[1] && n.getDay() >= 1 && n.getDay() <= 5; }
function cockpitHtml() {
  const vak = [], nu = new Date();
  const vd = ALLE.filter((t) => t.datum === vandaagISO()), laatste = vd[vd.length - 1];
  if (laatste && laatste.r < 0 && laatste.tijd_exit) {                                       // afkoelen na een verlies
    const eind = new Date(vandaagISO() + "T" + laatste.tijd_exit + ":00").getTime() + 10 * 60000, rest = eind - nu.getTime();
    if (rest > 0) vak.push(`<span class="vak" style="color:var(--g-amber);border-color:var(--g-amber)">AFKOELEN <b>${Math.floor(rest / 60000)}:${String(Math.floor(rest / 1000) % 60).padStart(2, "0")}</b></span>`);
  }
  const komend = NIEUWS.filter((n) => n.ts * 1000 > nu.getTime() && n.ts * 1000 - nu.getTime() < 90 * 60000)[0];
  if (komend) { const m = Math.round((komend.ts * 1000 - nu.getTime()) / 60000);
    vak.push(`<span class="vak" style="${m <= 15 ? "color:var(--g-red);border-color:var(--g-red)" : ""}">NIEUWS <b>${esc(komend.titel.slice(0, 22))}</b> OVER ${m} MIN</span>`); }
  const st = MARKT && MARKT.structuur;
  if (st && inVenster()) {
    const exp = (st.lopend || [])[0];                                                  // expansie die nu loopt (nog geen sweep)
    if (exp) vak.push(`<span class="vak">EXPANSIE <b>${esc(exp.richting.toUpperCase())} ${exp.atr_x != null ? nl(exp.atr_x, 1) + "x ATR" : ""}</b></span>`);
    const k = (st.kandidaten || []).filter((x) => x.bos_tijd && nu.getTime() / 1000 - x.bos_tijd < 15 * 60).pop();   // sweep + BOS in de laatste 15 min
    if (k) vak.push(`<span class="vak" style="color:var(--g-gold);border-color:var(--g-gold)">SETUP <b>${k.trade === "short" ? "▼ SHORT" : "▲ LONG"} ENTRY ${nl(k.entry)} SL ${nl(k.sl)}</b></span>`);
  }
  vak.push(`<span class="vak knop" data-geluid="1" style="cursor:pointer" title="8-bit geluid bij TP, badge en level-up">${KLANK.aan ? "♪ AAN" : "♪ UIT"}</span>`);
  return vak.join("");
}
async function cockpitLus() {
  if (inVenster()) { try { const d = await haal("/api/game/station/markt"); if (!d.error) MARKT = d; } catch (e) {} }
  tekenHud(); setTimeout(cockpitLus, inVenster() ? 30000 : 120000);
}
setInterval(() => { if (document.getElementById("g-hud")) tekenHud(); }, 1000);      // aftelklokken lopen door

/* ------------------------------------------------------------------ 10. quests, bossfight, geluid, level-up */
NA_TEKENEN.push(function tekenQuests() {
  const vd = ALLE.filter((t) => t.datum === vandaagISO());
  let revenge = false; for (let i = 1; i < vd.length; i++) { const v = vd[i - 1]; if (v.r < 0 && v.tijd_exit) { const a = new Date("2000-01-01T" + v.tijd_exit), b = new Date("2000-01-01T" + vd[i].tijd); if ((b - a) / 60000 < 10) revenge = true; } }
  const dicht = !inVenster() && new Date().getHours() >= 15;
  const Q = [[`Maximaal ${MAXDAG} trades`, vd.length > MAXDAG ? "mislukt" : dicht ? "gehaald" : "bezig", `${vd.length}/${MAXDAG}`],
    ["SL niet verruimen", vd.some((t) => t.sl_verruimd > 0) ? "mislukt" : vd.length ? (dicht ? "gehaald" : "bezig") : "bezig", `${vd.filter((t) => t.sl_verruimd > 0).length}× verruimd`],
    ["10 min afkoelen na een verlies", revenge ? "mislukt" : dicht && vd.length ? "gehaald" : "bezig", revenge ? "te snel weer ingestapt" : "ok"],
    ["Alles loggen", vd.length && vd.every((t) => t.beoordeeld === 1) ? "gehaald" : vd.length ? "bezig" : "bezig", `${vd.filter((t) => t.beoordeeld === 1).length}/${vd.length}`]];
  const kl = { gehaald: K.hi, mislukt: K.red, bezig: K.muted }, tek = { gehaald: "✓", mislukt: "✗", bezig: "·" };
  document.getElementById("g-quests").innerHTML = Q.map(([n, s, x]) => `<div class="g-balk"><span style="color:${kl[s]}">${tek[s]} ${n}</span><b class="g-dim">${x}</b>
    <b style="margin-left:auto;color:${kl[s]}">${s === "gehaald" ? "+25 XP" : s.toUpperCase()}</b></div>`).join("");
  document.getElementById("g-quest-xp").textContent = `${Q.filter((q) => q[1] === "gehaald").length}/${Q.length} gehaald`;
});
function bossCfg() { try { return Object.assign({ doel: 10, budget: 6 }, JSON.parse(localStorage.getItem("cbr_boss") || "{}")); } catch (e) { return { doel: 10, budget: 6 }; } }
function bossInstellen() {
  const c = bossCfg(), d = prompt("Maanddoel in R (= HP van de boss)", c.doel), b = d == null ? null : prompt("Je verliesbudget in R voor deze maand (= jouw HP)", c.budget);
  if (d == null || b == null) return; try { localStorage.setItem("cbr_boss", JSON.stringify({ doel: Math.max(1, +d || 10), budget: Math.max(1, +b || 6) })); } catch (e) {}
  tekenAlles();
}
let bossT = 0;
NA_TEKENEN.push(function tekenBoss() {
  const c = bossCfg(), m = vandaagISO().slice(0, 7), T = ALLE.filter((t) => t.maand === m);
  const schade = T.filter((t) => t.r > 0).reduce((s, t) => s + t.r, 0), geraakt = -T.filter((t) => t.r < 0).reduce((s, t) => s + t.r, 0);
  const bossHp = Math.max(0, c.doel - schade), jijHp = Math.max(0, c.budget - geraakt);
  document.getElementById("g-boss-titel").textContent = `BOSSFIGHT ${new Date().toLocaleDateString("nl-NL", { month: "long" }).toUpperCase()}`;
  document.getElementById("g-boss-tekst").innerHTML = bossHp <= 0 && jijHp <= 0
    ? `<b class="g-gold">DUBBELE KO.</b> Maanddoel van ${c.doel}R gehaald (+${nl(schade, 1)}R winst), maar ook je verliesbudget van ${c.budget}R is op (-${nl(geraakt, 1)}R). Netto ${plusR(schade - geraakt)}.`
    : bossHp <= 0 ? `<b class="g-gold">BOSS VERSLAGEN!</b> Maanddoel van ${c.doel}R gehaald.` : jijHp <= 0
    ? `<b class="g-neg">GAME OVER voor deze maand:</b> je verliesbudget van ${c.budget}R is op. Rust, review, volgende maand nieuwe kansen.`
    : `Elke R winst raakt de boss (nog ${nl(bossHp, 1)}R), elke R verlies raakt jou (nog ${nl(jijHp, 1)}R van je budget). ⚙ = doel en budget aanpassen.`;
  const cv = document.getElementById("g-boss"), g = cv.getContext("2d"); g.imageSmoothingEnabled = false;
  const teken = () => { bossT++;
    g.fillStyle = "#02120a"; g.fillRect(0, 0, cv.width, cv.height);
    const hp = (x, y, w, f, kl, n) => { g.fillStyle = "#0b2414"; g.fillRect(x, y, w, 8); g.fillStyle = kl; g.fillRect(x, y, Math.round(w * Math.max(0, Math.min(1, f))), 8);
      g.strokeStyle = "#d8ffe6"; g.strokeRect(x + .5, y + .5, w - 1, 7); g.fillStyle = "#6fae86"; g.font = "13px VT323"; g.fillText(n, x, y - 2); };
    hp(10, 14, 150, jijHp / c.budget, K.hi, `JIJ ${nl(jijHp, 1)}/${c.budget}R`); hp(260, 14, 150, bossHp / c.doel, K.red, `BOSS ${nl(bossHp, 1)}/${c.doel}R`);
    tekenPoppetje(g, 40, 40 - (Math.floor(bossT / 8) % 2), "#ffffff", Math.floor(bossT / 8), 3);
    const b = Math.floor(bossT / 10) % 2, bx = 300, by = 34 + b;                                       // de boss: een groot pixelmonster
    g.fillStyle = bossHp <= 0 ? "#2b6b43" : "#ff5a4f"; g.fillRect(bx, by, 60, 44); g.fillRect(bx - 6, by + 10, 6, 20); g.fillRect(bx + 60, by + 10, 6, 20);
    g.fillStyle = "#02120a"; g.fillRect(bx + 12, by + 12, 8, 8); g.fillRect(bx + 40, by + 12, 8, 8); g.fillRect(bx + 16, by + 30, 28, 4);
    g.fillStyle = "#ffd36b"; g.fillRect(bx + 14, by + 14, 3, 3); g.fillRect(bx + 42, by + 14, 3, 3);
    if (bossT % 60 < 14 && schade > 0 && bossHp > 0) { g.fillStyle = "#ffd36b"; const s = bossT % 60; g.fillRect(70 + s * 16, 56, 8, 4); }   // schot naar de boss
    if (bossT < 400) requestAnimationFrame(teken); };
  bossT = 0; teken();
});
function piep(soort) {
  if (!KLANK.aan) return;
  try { const A = new (window.AudioContext || window.webkitAudioContext)(), o = A.createOscillator(), v = A.createGain(); o.type = "square"; o.connect(v); v.connect(A.destination);
    const seq = soort === "level" ? [523, 659, 784, 1046] : soort === "badge" ? [784, 988, 1175] : [988, 1319];
    seq.forEach((f, i) => o.frequency.setValueAtTime(f, A.currentTime + i * .09)); v.gain.setValueAtTime(.08, A.currentTime); v.gain.exponentialRampToValueAtTime(.001, A.currentTime + seq.length * .09 + .15);
    o.start(); o.stop(A.currentTime + seq.length * .09 + .2); } catch (e) {}
}
function levelUpCheck() {
  const x = xp(); let oud = 0; try { oud = +localStorage.getItem("cbr_level") || 0; } catch (e) {}
  try { localStorage.setItem("cbr_level", x.lvl); } catch (e) {}
  if (oud && x.lvl > oud) toonBanner(`LEVEL UP! LEVEL ${x.lvl}`, "level");
  const nieuweBadge = document.querySelector(".g-badge.nieuw b"); if (nieuweBadge) setTimeout(() => toonBanner("BADGE: " + nieuweBadge.textContent, "badge"), oud && x.lvl > oud ? 2600 : 0);
}
function nieuweTpCheck() {
  const maxId = Math.max(0, ...ALLE.map((t) => t.id)); let oud = 0; try { oud = +localStorage.getItem("cbr_laatste_trade") || 0; } catch (e) {}
  try { localStorage.setItem("cbr_laatste_trade", maxId); } catch (e) {}
  const nieuw = ALLE.filter((t) => t.id > oud && oud), tp = nieuw.filter((t) => t.r > 0);
  if (tp.length) { toonBanner(`${tp.length} WINNENDE TRADE${tp.length > 1 ? "S" : ""} SINDS JE VORIGE BEZOEK · ${plusR(tp.reduce((s, t) => s + t.r, 0))}`, "munt");
    for (let i = 0; i < 80; i++) munten.push({ x: 40 + Math.random() * 560, y: -Math.random() * 80, v: .6 + Math.random() * 1.4 }); }
}
function toonBanner(tekst, soort) {
  const b = document.createElement("div"); b.className = "g-banner"; b.textContent = tekst; document.body.appendChild(b); piep(soort);
  setTimeout(() => b.remove(), 2600);
}
