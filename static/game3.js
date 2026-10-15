/* =====================================================================
   CBR Journal · GAME MODE, deel 3 (15 okt 2026, ronde 2 van de voorstellen)
     1 risico per trade (€ en % van je saldo, plan instelbaar, 'wat als elke trade X%')
     2 hoe je instapt: minuten na de BOS, marktorder of limiet, slippage (uit MT5)
     4 weekfocus: voorstel uit je eigen data, opslaan als week-review, voortgang deze week tegen vorige week
     5 loggen in game mode (zelfde vragen als klassiek, met XP)
     7 filters bewaren en twee filtersets vergelijken
     8 jij tegen de bots op één grafiek
     9 meer beweging: agents in je scène, koers in de HUD, vuurwerk bij een weekrecord
    10 week- en maandrapport (afdrukken = pdf)
    12 datakwaliteit: wat ontbreekt, met een link om het zelf aan te vullen
   Haakt in op game.js / game2.js. Schrijft alleen via de bestaande journal-API's (loggen, week-review).
   ===================================================================== */
"use strict";
const nuISO = () => vandaagISO();
const maandagVan = (d) => { const t = new Date(d + "T12:00"); t.setDate(t.getDate() - ((t.getDay() + 6) % 7)); return t.toISOString().slice(0, 10); };
const plusDagen = (d, n) => { const t = new Date(d + "T12:00"); t.setDate(t.getDate() + n); return t.toISOString().slice(0, 10); };
async function stuurJson(pad, methode, body) {
  const r = await fetch(pad, { method: methode, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error("fout " + r.status); return r.json();
}

/* ------------------------------------------------------------------ 1. risico per trade */
const PLAN = { pct: (() => { try { return +localStorage.getItem("cbr_plan_risico") || 1; } catch (e) { return 1; } })() };
function bouwPlanKnoppen() {
  const el = document.getElementById("g-plan-risico"); if (!el || el.children.length) return;
  el.innerHTML = [0.5, 1, 1.5, 2].map((p) => `<button data-p="${p}" class="${PLAN.pct === p ? "aan" : ""}">${nl(p, p % 1 ? 1 : 0)}%</button>`).join("");
  el.onclick = (ev) => { const b = ev.target.closest("button"); if (!b) return; PLAN.pct = +b.dataset.p; try { localStorage.setItem("cbr_plan_risico", PLAN.pct); } catch (e) {}
    el.querySelectorAll("button").forEach((x) => x.classList.toggle("aan", x === b)); tekenAlles(); };
}
NA_TEKENEN.push(function tekenRisico(T) {
  bouwPlanKnoppen();
  const R = T.filter((t) => t.risico_pct != null);
  if (!R.length) { document.getElementById("g-risico").innerHTML = `<div class="g-uitleg">Geen trades met een gemeten risico in deze selectie.</div>`; return; }
  const lo = PLAN.pct * .5, hi = PLAN.pct * 1.5;
  const klasse = (t) => t.risico_pct < lo ? "te klein" : t.risico_pct > hi ? "te groot" : "volgens plan";
  maak("c-risico", { type: "bar", data: { labels: R.map((t) => kort(t.datum) + " " + t.tijd), datasets: [
      { type: "line", data: R.map(() => PLAN.pct), borderColor: K.gold, borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0, label: "plan" },
      { data: R.map((t) => t.risico_pct), backgroundColor: R.map((t) => klasse(t) === "te groot" ? K.red : klasse(t) === "te klein" ? K.cyan : K.hi), label: "risico %" }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => { const t = R[x.dataIndex];
        return x.datasetIndex ? [`#${t.id}: ${nl(t.risico_pct)}% (€${nl(t.risico_eur)} van €${nl(t.saldo_voor)})`, `${klasse(t)} · ${plusR(t.r)} · ${eur(t.netto)}`] : `plan ${PLAN.pct}%`; } } } },
      onClick: (e, el) => { const x = el.find((y) => y.datasetIndex === 1); if (x) replay(R[x.index].id); },
      scales: { x: { display: false }, y: { title: { display: true, text: "% van je saldo" }, grid: { color: "rgba(18,74,38,.5)" } } } } });
  const groep = (n) => R.filter((t) => klasse(t) === n), som = (a, k) => a.reduce((s, t) => s + t[k], 0);
  const rij = (n, kl) => { const a = groep(n); return `<tr><td style="color:${kl}">${n}</td><td class="n">${a.length}</td><td class="n">${plusR(som(a, "r"))}</td><td class="n">${eur(som(a, "netto"))}</td></tr>`; };
  const ps = R.map((t) => t.risico_pct).sort((a, b) => a - b);
  document.getElementById("g-risico").innerHTML = `<table class="g-t"><tr><th>RISICO T.O.V. PLAN ${nl(PLAN.pct, 1)}% (±50%)</th><th class="n">TRADES</th><th class="n">R</th><th class="n">€</th></tr>
    ${rij("te klein", K.cyan)}${rij("volgens plan", K.hi)}${rij("te groot", K.red)}</table>
    <div class="g-uitleg">Je risico liep van ${nl(ps[0])}% tot ${nl(ps[ps.length - 1])}% van je saldo (factor ${nl(ps[ps.length - 1] / Math.max(.01, ps[0]), 0)}).
      ${som(R, "r") > 0 && som(R, "netto") < som(R, "r") * (som(R, "risico_eur") / R.length) * .5 ? "Je R komt maar voor een deel terug in euro's: je winst viel vaker op kleine posities." : ""}</div>`;
  // wat als elke trade precies het plan-% van je saldo had geriskeerd
  let echt = 0, wat = 0; const pe = [], pw = [];
  for (const t of R) { echt += t.netto; wat += t.r * PLAN.pct / 100 * t.saldo_voor + (t.kosten || 0); pe.push(+echt.toFixed(2)); pw.push(+wat.toFixed(2)); }
  maak("c-risico-wat", { type: "line", data: { labels: R.map((t) => kort(t.datum)), datasets: [
      { label: "echt (€)", data: pe, borderColor: K.ink, borderWidth: 2, pointRadius: 0 },
      { label: `elke trade ${nl(PLAN.pct, 1)}% (€)`, data: pw, borderColor: K.gold, borderWidth: 2, pointRadius: 0, borderDash: [5, 3] }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, labels: { boxWidth: 10 } } },
      scales: { x: { ticks: { maxTicksLimit: 8 }, grid: { display: false } }, y: { grid: { color: "rgba(18,74,38,.5)" } } } } });
});

/* ------------------------------------------------------------------ 2. hoe je instapt */
const instapBak = (t) => t.instap_na_bos_min == null ? "geen setup gekoppeld" : t.instap_na_bos_min < 0 ? "vóór de BOS dicht" :
  t.instap_na_bos_min < 1 ? "0-1 min" : t.instap_na_bos_min < 2 ? "1-2 min" : t.instap_na_bos_min < 5 ? "2-5 min" : "> 5 min";
const INSTAP_VOLG = ["vóór de BOS dicht", "0-1 min", "1-2 min", "2-5 min", "> 5 min", "geen setup gekoppeld"];
DIM.instap = { naam: "INSTAP NA DE BOS", f: instapBak, volgorde: INSTAP_VOLG };
DIM.ordersoort = { naam: "MARKTORDER OF LIMIET", f: (t) => t.order_soort || "onbekend" };
NA_TEKENEN.push(function tekenInstap(T) {
  const g = {}; for (const t of T) { const k = instapBak(t); (g[k] = g[k] || []).push(t); }
  const labels = INSTAP_VOLG.filter((k) => g[k] && k !== "geen setup gekoppeld");
  maak("c-instap", { type: "bar", data: { labels, datasets: [{ data: labels.map((k) => +g[k].reduce((s, t) => s + t.r, 0).toFixed(2)),
      backgroundColor: labels.map((k) => g[k].reduce((s, t) => s + t.r, 0) >= 0 ? K.hi : K.red) }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => { const a = g[labels[x.dataIndex]];
        return [`${plusR(x.parsed.y)} over ${a.length} trades`, `winrate ${Math.round(100 * a.filter((t) => t.r > 0).length / a.length)}%`]; } } } },
      scales: { x: { grid: { display: false } }, y: { title: { display: true, text: "R totaal" }, grid: { color: "rgba(18,74,38,.5)" } } } } });
  const ord = {}; for (const t of T) if (t.order_soort) (ord[t.order_soort] = ord[t.order_soort] || []).push(t);
  const slip = T.filter((t) => t.slippage_points != null && t.order_soort === "markt");
  const bos = T.filter((t) => t.instap_na_bos_min != null && t.instap_na_bos_min >= 0);
  document.getElementById("g-instap").innerHTML = `<table class="g-t"><tr><th>ORDER</th><th class="n">TRADES</th><th class="n">R</th><th class="n">R/TRADE</th><th class="n">WIN%</th></tr>
    ${Object.entries(ord).map(([k, a]) => { const r = a.reduce((s, t) => s + t.r, 0); return `<tr><td>${esc(k.toUpperCase())}</td><td class="n">${a.length}</td><td class="n ${r >= 0 ? "g-pos" : "g-neg"}">${plusR(r)}</td>
      <td class="n">${plusR(r / a.length)}</td><td class="n">${Math.round(100 * a.filter((t) => t.r > 0).length / a.length)}%</td></tr>`; }).join("")}</table>
    <div class="g-uitleg">${bos.length ? `Je stapt gemiddeld <b class="g-ink">${nl(bos.reduce((s, t) => s + t.instap_na_bos_min, 0) / bos.length, 1)} min</b> na de BOS in (${bos.length} trades met een gekoppelde setup). ` : ""}
      ${slip.length ? `Slippage op marktorders: gemiddeld ${nl(slip.reduce((s, t) => s + t.slippage_points, 0) / slip.length, 1)} points (max ${nl(Math.max(...slip.map((t) => t.slippage_points)), 1)}): de vulling is het probleem niet, het moment wel.` : ""}</div>`;
});

/* ------------------------------------------------------------------ 4. weekfocus */
function weekMeting(van, tot) {
  const W = ALLE.filter((t) => t.datum >= van && t.datum <= tot);
  const per = {}; W.forEach((t) => (per[t.datum] = per[t.datum] || []).push(t));
  let revenge = 0;
  for (const dag of Object.values(per)) for (let i = 1; i < dag.length; i++) { const v = dag[i - 1];
    if (v.r < 0 && v.tijd_exit && dag[i].tijd) { const m = (new Date("2000-01-01T" + dag[i].tijd) - new Date("2000-01-01T" + v.tijd_exit.slice(0, 5))) / 60000; if (m >= 0 && m < 10) revenge++; } }
  const metOrder = W.filter((t) => t.order_soort), rp = W.filter((t) => t.risico_pct != null).map((t) => t.risico_pct);
  const afg = ((typeof GEMIST !== "undefined" && GEMIST && GEMIST.orders) || []).filter((o) => o.gevolgd_door && o.geplaatst && o.geplaatst.slice(0, 10) >= van && o.geplaatst.slice(0, 10) <= tot).length;
  return { trades: W.length, verruimd: W.filter((t) => t.sl_verruimd > 0).length, markt: metOrder.filter((t) => t.order_soort === "markt").length, met_order: metOrder.length,
    afgeblazen: afg, revenge, dagmax: Object.values(per).filter((d) => d.length > MAXDAG).length,
    risico: rp.length > 1 ? Math.max(...rp) / Math.max(.01, Math.min(...rp)) : 1, ongelogd: W.filter((t) => t.beoordeeld === 0).length };
}
const FOCUSSEN = [
  { key: "verruimd", tekst: "SL vast: nooit je stop verder weg zetten", waarde: (m) => m.verruimd, ernst: (m) => m.verruimd * 2, uitleg: (m) => `${m.verruimd}× SL verruimd` },
  { key: "markt", tekst: "Limiet op 50% zetten en laten liggen, niet zelf in de markt springen", waarde: (m) => m.markt, ernst: (m) => m.met_order ? 4 * m.markt / m.met_order : 0, uitleg: (m) => `${m.markt} van ${m.met_order} trades met een marktorder` },
  { key: "afgeblazen", tekst: "Een limiet die je zet, laat je staan", waarde: (m) => m.afgeblazen, ernst: (m) => m.afgeblazen * 1.5, uitleg: (m) => `${m.afgeblazen}× limiet weggehaald en toch ingestapt` },
  { key: "revenge", tekst: "10 minuten afkoelen na een verlies", waarde: (m) => m.revenge, ernst: (m) => m.revenge * 2.5, uitleg: (m) => `${m.revenge}× binnen 10 min na een verlies weer in een trade` },
  { key: "dagmax", tekst: `Maximaal ${MAXDAG} trades per dag`, waarde: (m) => m.dagmax, ernst: (m) => m.dagmax * 2, uitleg: (m) => `${m.dagmax} dag(en) boven je dagmaximum` },
  { key: "risico", tekst: "Elke trade hetzelfde risico (zelfde % van je saldo)", waarde: (m) => +m.risico.toFixed(1), ernst: (m) => m.risico >= 3 ? m.risico / 2 : 0, uitleg: (m) => `risico wisselde met een factor ${nl(m.risico, 1)}` },
  { key: "ongelogd", tekst: "Elke trade dezelfde dag loggen", waarde: (m) => m.ongelogd, ernst: (m) => m.ongelogd, uitleg: (m) => `${m.ongelogd} trade(s) niet gelogd` },
];
let REVIEW = null;
async function laadFocus() { try { REVIEW = await haal("/api/review/week/" + maandagVan(nuISO())); } catch (e) { REVIEW = null; } tekenFocus(); }
function tekenFocus() {
  const el = document.getElementById("g-focus"); if (!el) return;
  const ma = maandagVan(nuISO()), deze = weekMeting(ma, plusDagen(ma, 6)), vorige = weekMeting(plusDagen(ma, -7), plusDagen(ma, -1)), laatste7 = weekMeting(plusDagen(nuISO(), -6), nuISO());
  document.getElementById("g-focus-week").textContent = `week van ${kort(ma)}`;
  const huidig = REVIEW && REVIEW.focus ? REVIEW.focus : "";
  const tag = (huidig.match(/\[meet:(\w+)\]/) || [])[1], f = FOCUSSEN.find((x) => x.key === tag);
  let h = "";
  if (huidig) {
    h += `<div class="g-lbl">JE FOCUS DEZE WEEK</div><p style="font-size:22px;margin:2px 0" class="g-gold">${esc(huidig.replace(/\s*\[meet:\w+\]/, ""))}</p>`;
    if (f) { const a = f.waarde(deze), b = f.waarde(vorige), beter = a < b || (a === 0 && b === 0);
      h += `<div class="g-balk"><span>deze week</span><i style="width:${Math.min(45, 6 * a + 1)}%;background:${a ? K.red : K.hi}"></i><b>${f.uitleg(deze)}</b></div>
        <div class="g-balk"><span>vorige week</span><i style="width:${Math.min(45, 6 * b + 1)}%;background:${K.muted}"></i><b>${f.uitleg(vorige)}</b></div>
        <p class="${beter ? "g-pos" : "g-neg"}">${a === 0 ? "Tot nu toe 0× deze week. Zo doorgaan." : beter ? "Beter dan vorige week." : "Nog niet beter dan vorige week."}</p>`; }
  }
  const kand = FOCUSSEN.map((x) => ({ ...x, e: x.ernst(laatste7) })).filter((x) => x.e > 0).sort((a, b) => b.e - a.e).slice(0, 3);
  h += `<div class="g-lbl" style="margin-top:8px">VOORSTEL UIT JE LAATSTE 7 DAGEN</div>` + (kand.length ? kand.map((x, i) => `<div class="g-balk"><span${i ? "" : ' class="g-gold"'}>${esc(x.tekst)}</span>
      <b class="g-dim">${esc(x.uitleg(laatste7))}</b><button class="g-knop" style="margin-left:auto" data-focus="${x.key}">${tag === x.key ? "✓ JE FOCUS" : "MAAK MIJN FOCUS"}</button></div>`).join("")
    : `<div class="g-uitleg">Niets dat eruit springt in de laatste 7 dagen. Mooi.</div>`);
  el.innerHTML = h;
  el.onclick = async (ev) => { const b = ev.target.closest("[data-focus]"); if (!b) return; const x = FOCUSSEN.find((y) => y.key === b.dataset.focus);
    b.textContent = "OPSLAAN...";
    try { REVIEW = await stuurJson("/api/review/week/" + ma, "PUT", { goed: (REVIEW && REVIEW.goed) || "", beter: (REVIEW && REVIEW.beter) || "", focus: x.tekst + " [meet:" + x.key + "]" });
      if (typeof toonBanner === "function") toonBanner("NIEUWE WEEKFOCUS", "badge"); } catch (e) { b.textContent = "MISLUKT"; }
    tekenFocus(); };
}
NA_TEKENEN.push(() => tekenFocus());

/* ------------------------------------------------------------------ 12. datakwaliteit */
async function laadKwaliteit() {
  let d; try { d = await haal("/api/game/kwaliteit"); } catch (e) { return; }
  document.getElementById("g-kwal-stand").textContent = `${d.trades - d.met_punten} van ${d.trades} trades compleet`;
  document.getElementById("g-kwal").innerHTML = (d.punten.length ? `<div class="g-tabelvak" style="max-height:220px"><table class="g-t"><tr><th>TRADE</th><th>WAT ONTBREEKT</th><th></th></tr>` +
    d.punten.slice().reverse().map((p) => `<tr><td>#${p.id} ${kort(p.datum)} ${esc(p.tijd || "--:--")}</td><td class="g-dim">${p.punten.map(esc).join(" · ")}</td>
      <td><a href="/trade?id=${p.id}">aanvullen →</a></td></tr>`).join("") + `</table></div>` : `<div class="g-uitleg g-pos">Alles compleet.</div>`) +
    `<div class="g-uitleg" style="margin-top:6px">Sessies: je gebruikte ${d.sessies.varianten.length} namen (${d.sessies.varianten.map(esc).join(", ")}); in game mode samengevoegd tot ${d.sessies.groepen.map(esc).join(", ")}. Er wordt niets in je data veranderd.</div>`;
}

/* ------------------------------------------------------------------ 5. loggen in game mode */
function tekenLogKaarten() {
  const box = document.getElementById("g-teloggen"), L = LOGDATA || {}, open = L.open || [];
  if (!open.length) { box.innerHTML = ""; return; }
  const seg = (k, w, isCheck) => { const ja = isCheck ? w === 1 : w === "yes", nee = isCheck ? w === 0 : w === "no";
    return `<span class="g-seg" data-sleutel="${k}"><button data-w="1" class="${ja ? "aan" : ""}">JA</button><button data-w="0" class="${nee ? "aan nee" : ""}">NEE</button></span>`; };
  box.innerHTML = `<section class="g-paneel g-teloggen"><div class="g-kop"><h3>! NOG TE LOGGEN: ${open.length}</h3><span class="g-uitleg">elk antwoord = XP</span></div>` +
    open.map((t) => { const netto = (t.resultaat || 0) + (t.charges || 0);
      return `<div class="g-logkaart" data-id="${t.id}"><div class="g-kop"><b style="font-size:22px">${t.richting === "long" ? "▲ LONG" : "▼ SHORT"} #${t.id} · ${kort(t.datum)} ${esc(t.tijd || "")}</b>
        <span><b class="${netto >= 0 ? "g-pos" : "g-neg"}">${eur(netto)}</b> ${t.r != null ? plusR(t.r) : ""} · ${esc(t.exit_reden || "")} · grade <b class="g-gold" data-rol="grade">${esc(t.grade || "?")}</b></span></div>
        <div class="g-grid2"><div><div class="g-lbl">SETUP</div>${(L.criteria || []).map(([k, l]) => `<div class="g-balk"><span title="${esc(l)}">${esc(l)}</span>${seg(k, t.criteria[k], false)}</div>`).join("")}</div>
          <div><div class="g-lbl">DISCIPLINE</div>${(L.checks || []).map(([k, l]) => `<div class="g-balk"><span>${esc(l)}</span>${seg(k, t.checks[k], true)}</div>`).join("")}
            <div class="g-lbl">EMOTIE VOORAF</div><div class="g-frij" data-veld="emotie_voor">${(L.emoties || []).map(([k, l]) => `<button class="g-chip ${t.emotie_voor === k ? "aan" : ""}" data-w="${k}">${esc(l)}</button>`).join("")}</div>
            <div class="g-lbl">UITVOERING</div><div class="g-frij" data-veld="uitvoering">${[1, 2, 3, 4, 5].map((n) => `<button class="g-chip ${t.uitvoering === n ? "aan" : ""}" data-w="${n}">${n}</button>`).join("")}</div>
            <div class="g-lbl">OPNIEUW NEMEN?</div><div class="g-frij" data-veld="opnieuw"><button class="g-chip ${t.opnieuw === 1 ? "aan" : ""}" data-w="1">JA, PRECIES ZO</button><button class="g-chip ${t.opnieuw === 0 ? "aan" : ""}" data-w="0">NEE</button></div></div></div>
        <div class="g-lbl">WAT GING ER MIS (OPTIONEEL)</div><div class="g-frij multi" data-veld="foutcodes">${(L.fouttags || []).map((f) => `<button class="g-chip ${(t.foutcodes || []).includes(f) ? "aan" : ""}" data-w="${esc(f)}">${esc(f)}</button>`).join("")}</div>
        <textarea class="g-les" rows="2" placeholder="Les in één zin">${esc(t.les || "")}</textarea>
        <div class="g-kop"><span class="g-uitleg" data-rol="status">${t.beoordeeld === 1 ? "GELOGD" : "nog niet compleet"}</span><a href="/trade?id=${t.id}">volledige trade →</a>
          <button class="g-knop" data-rol="klaar" ${t.beoordeeld === 1 ? "" : "hidden"}>✓ KLAAR (+50 XP)</button></div></div>`; }).join("") + `</section>`;
  box.querySelectorAll(".g-logkaart").forEach((k) => {
    const id = +k.dataset.id;
    const bijwerken = (t) => { k.querySelector('[data-rol="grade"]').textContent = t.grade || "?"; k.querySelector('[data-rol="status"]').textContent = t.beoordeeld === 1 ? "GELOGD" : "nog niet compleet";
      k.querySelector('[data-rol="klaar"]').hidden = t.beoordeeld !== 1; };
    const xp = (ev) => { const s = document.createElement("span"); s.className = "g-xp-pop"; s.textContent = "+5 XP"; s.style.left = ev.clientX + "px"; s.style.top = ev.clientY + "px";
      document.body.appendChild(s); setTimeout(() => s.remove(), 900); };
    k.querySelectorAll(".g-seg[data-sleutel]").forEach((seg) => seg.onclick = async (ev) => { const b = ev.target.closest("button"); if (!b) return;
      const was = b.classList.contains("aan"); seg.querySelectorAll("button").forEach((x) => x.classList.remove("aan", "nee")); if (!was) b.classList.add("aan", ...(b.dataset.w === "0" ? ["nee"] : []));
      xp(ev); bijwerken(await stuurJson(`/api/beoordeel/${id}`, "POST", { sleutel: seg.dataset.sleutel, waarde: was ? "" : b.dataset.w })); });
    k.querySelectorAll(".g-frij[data-veld]").forEach((gr) => gr.onclick = async (ev) => { const b = ev.target.closest("button"); if (!b) return; let w;
      if (gr.classList.contains("multi")) { b.classList.toggle("aan"); w = [...gr.querySelectorAll(".aan")].map((x) => x.dataset.w); }
      else { const was = b.classList.contains("aan"); gr.querySelectorAll("button").forEach((x) => x.classList.remove("aan")); if (!was) b.classList.add("aan"); w = was ? "" : b.dataset.w; }
      xp(ev); bijwerken(await stuurJson(`/api/beoordeel/${id}`, "POST", { veld: gr.dataset.veld, waarde: w })); });
    const les = k.querySelector(".g-les"); les.onchange = async () => bijwerken(await stuurJson(`/api/beoordeel/${id}`, "POST", { veld: "les", waarde: les.value }));
    k.querySelector('[data-rol="klaar"]').onclick = async () => { if (les.value) await stuurJson(`/api/beoordeel/${id}`, "POST", { veld: "les", waarde: les.value });
      k.classList.add("g-weg"); if (typeof toonBanner === "function") toonBanner("+50 XP · TRADE GELOGD", "munt");
      setTimeout(async () => { LOGDATA = await haal("/api/beoordelen"); OPEN = LOGDATA.open || []; const d = await haal("/api/game/trades"); ALLE = d.trades || ALLE; tekenLogKaarten(); tekenAlles(); }, 600); };
  });
}

/* ------------------------------------------------------------------ 7. filters bewaren en vergelijken */
function presets() { try { return JSON.parse(localStorage.getItem("cbr_filters") || "{}"); } catch (e) { return {}; } }
function filterMet(Fx, lijst) {
  const grens = Fx.periode === "alles" ? null : (() => { const d = new Date(); d.setDate(d.getDate() - +Fx.periode); return d.toISOString().slice(0, 10); })();
  const ok = (k, v) => !(Fx[k] || []).length || Fx[k].includes(v);
  return lijst.filter((t) => (!grens || t.datum >= grens) && ok("richting", t.richting) && ok("sessie", t.sessie) && ok("grade", t.grade) && ok("emotie", t.emotie)
    && ok("regels", String(t.schoon)) && ok("exit", t.exit) && ok("tp_type", t.tp_type) && ok("weekdag", t.weekdag) && ok("uur", String(t.uur)));
}
function tekenPresets() {
  const host = document.getElementById("g-filters"); if (!host) return;
  let rij = document.getElementById("g-presets");
  if (!rij) { rij = document.createElement("div"); rij.className = "g-frij"; rij.id = "g-presets"; host.appendChild(rij); }
  const P = presets(), namen = Object.keys(P);
  rij.innerHTML = `<span class="g-lbl">MIJN FILTERS</span>${namen.map((n) => `<button class="g-chip" data-preset="${esc(n)}">${esc(n)}</button>`).join("")}
    <button class="g-chip" data-bewaar="1">+ BEWAAR HUIDIGE</button>${namen.length ? `<button class="g-chip" data-wis="1">WIS…</button>` : ""}
    ${namen.length >= 1 ? `<span class="g-lbl" style="margin-left:auto">VERGELIJK</span><select id="g-va"><option value="__nu">huidige filter</option>${namen.map((n) => `<option>${esc(n)}</option>`).join("")}</select>
      <select id="g-vb"><option value="__alles">alles</option>${namen.map((n) => `<option>${esc(n)}</option>`).join("")}</select><button class="g-chip" data-vergelijk="1">VERGELIJK ▶</button>` : ""}`;
  rij.onclick = (ev) => { const b = ev.target.closest("button"); if (!b) return; ev.stopPropagation();
    if (b.dataset.preset) { const p = P[b.dataset.preset]; Object.keys(F).forEach((k) => { if (k !== "extra") F[k] = Array.isArray(F[k]) ? [...(p[k] || [])] : (p[k] || "alles"); }); F.extra = null; tekenAlles(); }
    else if (b.dataset.bewaar) { const n = prompt("Naam voor deze filter (bv. 'A-setups Londen')"); if (!n) return; const kopie = {}; Object.keys(F).forEach((k) => { if (k !== "extra") kopie[k] = F[k]; });
      P[n.slice(0, 30)] = kopie; try { localStorage.setItem("cbr_filters", JSON.stringify(P)); } catch (e) {} tekenPresets(); }
    else if (b.dataset.wis) { const n = prompt("Welke filter wissen? (" + namen.join(", ") + ")"); if (n && P[n]) { delete P[n]; try { localStorage.setItem("cbr_filters", JSON.stringify(P)); } catch (e) {} tekenPresets(); } }
    else if (b.dataset.vergelijk) vergelijk(document.getElementById("g-va").value, document.getElementById("g-vb").value);
  };
}
function vergelijk(a, b) {
  const P = presets(), set = (n) => n === "__nu" ? gefilterd() : n === "__alles" ? ALLE : filterMet(P[n], ALLE), naam = (n) => n === "__nu" ? "huidige filter" : n === "__alles" ? "alles" : n;
  const A = set(a), B = set(b), sa = stats(A), sb = stats(B);
  const paneel = document.getElementById("g-vergelijk-paneel"); paneel.hidden = false;
  document.getElementById("g-vergelijk-titel").textContent = `VERGELIJK: ${naam(a).toUpperCase()} TEGEN ${naam(b).toUpperCase()}`;
  const r = (l, x, y, f) => `<tr><td>${l}</td><td class="n g-gold">${f(x)}</td><td class="n g-cyan">${f(y)}</td></tr>`;
  document.getElementById("g-vergelijk").innerHTML = `<table class="g-t"><tr><th></th><th class="n g-gold">${esc(naam(a))}</th><th class="n g-cyan">${esc(naam(b))}</th></tr>
    ${r("trades", sa.n, sb.n, String)}${r("winrate", sa.winrate, sb.winrate, (v) => v + "%")}${r("R totaal", sa.r, sb.r, plusR)}${r("R per trade", sa.exp, sb.exp, plusR)}
    ${r("netto", sa.netto, sb.netto, eur)}${r("max drawdown", sa.dd, sb.dd, plusR)}</table>
    <div class="g-uitleg">${sa.n < 10 || sb.n < 10 ? "Let op: minder dan 10 trades in een van beide; verschillen zijn dan vooral toeval." : ""}</div>`;
  const cum = (X) => { let c = 0; return X.map((t) => +(c += t.r).toFixed(2)); };
  const n = Math.max(A.length, B.length);
  maak("c-vergelijk", { type: "line", data: { labels: Array.from({ length: n }, (_, i) => "#" + (i + 1)), datasets: [
      { label: naam(a), data: cum(A), borderColor: K.gold, borderWidth: 2, pointRadius: 0 }, { label: naam(b), data: cum(B), borderColor: K.cyan, borderWidth: 2, pointRadius: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, labels: { boxWidth: 10 } } },
      scales: { x: { title: { display: true, text: "trade nr" }, ticks: { maxTicksLimit: 8 } }, y: { title: { display: true, text: "opgeteld R" } } } } });
  paneel.scrollIntoView({ behavior: "smooth" });
}
document.addEventListener("click", (ev) => { if (ev.target.id === "g-vergelijk-dicht") document.getElementById("g-vergelijk-paneel").hidden = true; });
NA_TEKENEN.push(() => tekenPresets());

/* ------------------------------------------------------------------ 8. jij tegen de bots op één grafiek */
NA_TEKENEN.push(function tekenBotCurve(T) {
  if (!Object.keys(BOTS).length) return;
  const bot = { kampioen: {}, uitdager: {} };
  for (const s of Object.values(BOTS)) for (const tm of ["kampioen", "uitdager"]) { const x = s[tm];
    if (x && x.r != null && x.besloten) { const d = x.besloten.slice(0, 10); bot[tm][d] = (bot[tm][d] || 0) + x.r; } }
  const dagen = [...new Set([...Object.keys(bot.kampioen), ...Object.keys(bot.uitdager)])].sort();
  if (!dagen.length) return;
  const van = dagen[0], jij = {}; T.filter((t) => t.datum >= van).forEach((t) => jij[t.datum] = (jij[t.datum] || 0) + t.r);
  const alle = [...new Set([...dagen, ...Object.keys(jij)])].sort();
  const cum = (m) => { let c = 0; return alle.map((d) => +(c += m[d] || 0).toFixed(2)); };
  maak("c-botcurve", { type: "line", data: { labels: alle.map(kort), datasets: [
      { label: "jij", data: cum(jij), borderColor: K.ink, borderWidth: 2.5, pointRadius: 2, pointStyle: "rect" },
      { label: "Kampioen", data: cum(bot.kampioen), borderColor: K.gold, borderWidth: 2, pointRadius: 0 },
      { label: "Uitdager", data: cum(bot.uitdager), borderColor: K.cyan, borderWidth: 2, pointRadius: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, labels: { boxWidth: 10 } } },
      scales: { x: { grid: { display: false } }, y: { title: { display: true, text: "opgeteld R" }, grid: { color: "rgba(18,74,38,.5)" } } } } });
});

/* ------------------------------------------------------------------ 9. beweging: agents, koers, vuurwerk */
const AGENTS = [["VECTOR", "#ffb454", 0], ["NOVA", "#b6ff5c", 90], ["ORACLE", "#5cffd0", 180], ["JUDGE", "#ffd36b", 270]];
let vuurwerk = [];
const _origScene = tekenScene;
tekenScene = function () {                                                 // eslint-disable-line no-global-assign
  _origScene();
  const cv = document.getElementById("g-scene"); if (!cv) return; const g = cv.getContext("2d");
  for (const [n, kl, fase] of AGENTS) {                                    // agents lopen heen en weer door de kamer
    const baan = 240, p = (sceneT * 1.2 + fase) % (2 * baan), x = 280 + (p < baan ? p : 2 * baan - p), y = 66 + (fase % 3) * 5;
    tekenPoppetje(g, x, y, kl, Math.floor(sceneT / 4), 1);
    g.fillStyle = kl; g.font = "10px VT323"; g.fillText(n, x - 4, y - 2);
  }
  if (vuurwerk.length) { vuurwerk = vuurwerk.filter((d) => (d.t -= 1) > 0);
    for (const d of vuurwerk) { d.x += d.vx; d.y += d.vy; d.vy += .04; g.fillStyle = d.kl; g.fillRect(d.x, d.y, 2, 2); } }
};
function weekRecordCheck() {
  const wk = {}; ALLE.forEach((t) => wk[isoWeek(t.datum)] = (wk[isoWeek(t.datum)] || 0) + t.r);
  const nu = isoWeek(nuISO()), vorige = Object.entries(wk).filter(([k]) => k !== nu).map(([, v]) => v);
  if (!(nu in wk) || !vorige.length || wk[nu] <= Math.max(...vorige)) return;
  let gezien = ""; try { gezien = localStorage.getItem("cbr_weekrecord") || ""; } catch (e) {}
  if (gezien === nu + ":" + wk[nu].toFixed(2)) return;
  try { localStorage.setItem("cbr_weekrecord", nu + ":" + wk[nu].toFixed(2)); } catch (e) {}
  const kl = [K.gold, K.hi, K.cyan, "#ff8f8a", "#ffffff"];
  for (let s = 0; s < 4; s++) { const cx = 120 + s * 140, cy = 30 + (s % 2) * 15;
    for (let i = 0; i < 40; i++) { const a = Math.random() * 6.28, v = .6 + Math.random() * 1.6; vuurwerk.push({ x: cx, y: cy, vx: Math.cos(a) * v, vy: Math.sin(a) * v - .5, t: 60 + Math.random() * 40, kl: kl[(i + s) % kl.length] }); } }
  if (typeof toonBanner === "function") toonBanner(`WEEKRECORD! ${plusR(wk[nu])}`, "level");
}
let KOERS = null;
async function koersLus() {
  try { const d = await haal("/api/game/station/markt"); if (!d.error && d.candles && d.candles.length) { const c = d.candles, eerste = c[0][1], laatste = c[c.length - 1][4];
    KOERS = { prijs: laatste, delta: laatste - c[Math.max(0, c.length - 16)][4], tijd: d.tijd }; if (typeof MARKT !== "undefined" && !MARKT) MARKT = d; } } catch (e) {}
  setTimeout(koersLus, 60000);
}
const _origCockpit = typeof cockpitHtml === "function" ? cockpitHtml : () => "";
cockpitHtml = function () {                                                // eslint-disable-line no-global-assign
  const k = KOERS ? `<span class="vak" title="XAUUSD, verandering laatste 15 min">GOUD <b>${nl(KOERS.prijs)}</b> <b class="${KOERS.delta >= 0 ? "g-pos" : "g-neg"}">${KOERS.delta >= 0 ? "▲" : "▼"}${nl(Math.abs(KOERS.delta))}</b></span>` : "";
  return k + _origCockpit() + `<span class="vak knop" data-rapport="1" style="cursor:pointer;color:var(--g-gold);border-color:var(--g-gold)">RAPPORT</span>`;
};

/* ------------------------------------------------------------------ 10. week- en maandrapport */
const RAP = { soort: "week", ankers: nuISO() };
function rapportBereik() {
  if (RAP.soort === "week") { const ma = maandagVan(RAP.anker || nuISO()); return [ma, plusDagen(ma, 6), `WEEK ${isoWeek(ma).slice(-2)} · ${kort(ma)} t/m ${kort(plusDagen(ma, 6))}`]; }
  const d = (RAP.anker || nuISO()).slice(0, 7), eind = new Date(+d.slice(0, 4), +d.slice(5, 7), 0).getDate();
  return [d + "-01", d + "-" + String(eind).padStart(2, "0"), new Date(d + "-15").toLocaleDateString("nl-NL", { month: "long", year: "numeric" }).toUpperCase()];
}
async function openRapport() {
  RAP.anker = RAP.anker || nuISO();
  const m = document.getElementById("g-rapport"); m.hidden = false;
  const seg = document.getElementById("g-rapport-soort");
  seg.innerHTML = [["week", "WEEK"], ["maand", "MAAND"]].map(([k, l]) => `<button data-s="${k}" class="${RAP.soort === k ? "aan" : ""}">${l}</button>`).join("");
  seg.onclick = (ev) => { const b = ev.target.closest("button"); if (b) { RAP.soort = b.dataset.s; openRapport(); } };
  const [van, tot, titel] = rapportBereik();
  document.getElementById("g-rapport-titel").textContent = "RAPPORT · " + titel;
  const T = ALLE.filter((t) => t.datum >= van && t.datum <= tot), s = stats(T), m_ = weekMeting(van, tot);
  const beste = T.slice().sort((a, b) => b.r - a.r)[0], slechtste = T.slice().sort((a, b) => a.r - b.r)[0];
  let review = null; if (RAP.soort === "week") { try { review = await haal("/api/review/week/" + van); } catch (e) {} }
  let bedrijf = null, dagen = [];
  try { const lijst = (await haal("/api/game/station/rapporten")).lijst || [], per = RAP.soort === "week" ? isoWeek(van) : van.slice(0, 7);
    const r = lijst.find((x) => x.soort === RAP.soort && x.periode === per); if (r) bedrijf = await haal("/api/game/station/rapport?id=" + r.id);
    dagen = lijst.filter((x) => x.soort === "dag" && x.periode >= van && x.periode <= tot).sort((a, b) => a.periode.localeCompare(b.periode)); } catch (e) {}
  if ((!bedrijf || bedrijf.error) && dagen.length) bedrijf = { titel: "dagrapporten", zinnen: dagen.map((x) => kort(x.periode) + ": " + x.samenvatting) };
  const lessen = T.filter((t) => t.les).map((t) => `<div class="g-uitleg">· #${t.id} ${kort(t.datum)}: ${esc(t.les)}</div>`).join("");
  document.getElementById("g-rapport-inhoud").innerHTML = T.length ? `
    <div class="g-kpis">${[["TRADES", s.n], ["WINRATE", s.winrate + "%"], ["R", plusR(s.r)], ["R/TRADE", plusR(s.exp)], ["NETTO", eur(s.netto)], ["MAX DD", plusR(s.dd)]]
      .map(([l, v]) => `<div class="g-kpi"><b>${v}</b><span>${l}</span></div>`).join("")}</div>
    <div class="g-grid2"><div class="g-chart" style="height:200px"><canvas id="c-rapport"></canvas></div>
      <div><div class="g-lbl">DISCIPLINE</div>${[["SL verruimd", m_.verruimd], ["marktorders", m_.markt + "/" + m_.met_order], ["limiet weggehaald, toch ingestapt", m_.afgeblazen],
        ["binnen 10 min na verlies", m_.revenge], [`dagen boven ${MAXDAG} trades`, m_.dagmax], ["risico-spreiding (factor)", nl(m_.risico, 1)], ["niet gelogd", m_.ongelogd]]
        .map(([l, v]) => `<div class="g-balk"><span>${l}</span><b>${v}</b></div>`).join("")}</div></div>
    <div class="g-grid2"><div><div class="g-lbl">BESTE / SLECHTSTE</div><div class="g-uitleg">beste: #${beste.id} ${kort(beste.datum)} ${beste.tijd} ${plusR(beste.r)} · slechtste: #${slechtste.id} ${kort(slechtste.datum)} ${slechtste.tijd} ${plusR(slechtste.r)}</div>
        ${review && review.focus ? `<div class="g-lbl" style="margin-top:6px">WEEKFOCUS</div><div class="g-uitleg g-gold">${esc(review.focus.replace(/\s*\[meet:\w+\]/, ""))}</div>` : ""}
        ${lessen ? `<div class="g-lbl" style="margin-top:6px">JOUW LESSEN</div>${lessen}` : ""}</div>
      <div>${bedrijf && !bedrijf.error ? `<div class="g-lbl">CBR STATION (${esc(bedrijf.titel)})</div>${(bedrijf.zinnen || []).map((z) => `<div class="g-uitleg">${esc(z)}</div>`).join("")}` : `<div class="g-uitleg">Geen bedrijfsrapport van CBR Station voor deze periode.</div>`}</div></div>`
    : `<div class="g-uitleg">Geen trades in deze periode.</div>`;
  if (T.length) { const per = {}; T.forEach((t) => per[t.datum] = (per[t.datum] || 0) + t.r); const d = Object.keys(per).sort();
    maak("c-rapport", { type: "bar", data: { labels: d.map(kort), datasets: [{ data: d.map((x) => +per[x].toFixed(2)), backgroundColor: d.map((x) => per[x] >= 0 ? K.hi : K.red) }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } }, scales: { y: { title: { display: true, text: "R per dag" } } } } }); }
}
document.addEventListener("click", (ev) => {
  if (ev.target.closest("[data-rapport]")) { RAP.anker = nuISO(); openRapport(); }
  if (ev.target.id === "g-rapport-dicht" || ev.target.id === "g-rapport") document.getElementById("g-rapport").hidden = true;
  if (ev.target.id === "g-rapport-print") window.print();
  if (ev.target.id === "g-rapport-vorige" || ev.target.id === "g-rapport-volgende") { const s = ev.target.id.endsWith("vorige") ? -1 : 1;
    if (RAP.soort === "week") RAP.anker = plusDagen(maandagVan(RAP.anker), 7 * s);
    else { const [j, mm] = RAP.anker.slice(0, 7).split("-").map(Number), d = new Date(j, mm - 1 + s, 15); RAP.anker = d.toISOString().slice(0, 10); }
    openRapport(); }
});

/* ------------------------------------------------------------------ start */
const _origExtraBoot = extraBoot;
extraBoot = async function () {                                            // eslint-disable-line no-global-assign
  await _origExtraBoot();
  laadFocus(); laadKwaliteit(); koersLus(); tekenLogKaarten(); weekRecordCheck(); tekenPresets();
};
