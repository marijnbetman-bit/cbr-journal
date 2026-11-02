/* FTMO-account (2 nov 2026): alleen lezen, gegevens uit /api/ftmo (ftmo_journal.py). */

const eur = (v) => (v == null ? "–" : "€" + Number(v).toLocaleString("nl-NL", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const rr = (v) => (v == null ? "–" : (v > 0 ? "+" : "") + Number(v).toFixed(2) + "R");
const kl = (v) => (v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function meter(pct) {
  const p = Math.max(0, Math.min(100, pct || 0));
  const soort = p >= 80 ? "gevaar" : p >= 50 ? "let" : "";
  return `<div class="ftmo-meter"><div class="${soort}" style="width:${p}%"></div></div>`;
}

function renderKpi(d) {
  const s = d.stand || {};
  const t = d.totaal || {};
  const a = d.per_bron.alles;
  const cellen = [
    { k: "Saldo", v: eur(s.balans) },
    { k: "Equity (met open)", v: eur(s.equity) },
    { k: "Winst sinds start", v: t.winst == null ? "–" : eur(t.winst) + " (" + t.winst_pct + "%)", cls: kl(t.winst) },
    { k: "Trades", v: String(a.n) },
    { k: "Som R", v: rr(a.r_som), cls: kl(a.r_som) },
    { k: "Open posities", v: String(s.open_n ?? "–") },
  ];
  document.getElementById("kpi").innerHTML =
    `<div class="mt-bar">${cellen.map((c) => `
      <div class="mt-cell"><div class="k">${c.k}</div><div class="val ${c.cls || ""}">${c.v}</div></div>`).join("")}</div>`;
}

function renderGrenzen(d) {
  const v = d.vandaag;
  document.getElementById("dagGrens").innerHTML = v
    ? `<h2>Vandaag: max dagverlies 3%</h2>
       <p class="sub">Stand om 00:00: ${eur(v.start)} · grens ${eur(v.grens)} verlies (open posities tellen mee)</p>
       ${meter(v.pct)}
       <div>Verlies nu <b class="${v.verlies > 0 ? "neg" : ""}">${eur(v.verlies)}</b> · nog <b>${eur(v.ruimte)}</b> ruimte ·
         ${v.trades.n} trade(s) vandaag (${rr(v.trades.r_som)})</div>`
    : `<h2>Vandaag</h2><p class="sub">Nog geen stand van vandaag.</p>`;
  const t = d.totaal;
  const start = d.account.startkapitaal;
  document.getElementById("maxGrens").innerHTML = t
    ? `<h2>Max verlies 10%</h2>
       <p class="sub">Equity mag niet onder ${eur(t.vloer)} komen</p>
       ${meter(100 * Math.max(0, start - (t.vloer + t.ruimte)) / (start - t.vloer))}
       <div>Nog <b>${eur(t.ruimte)}</b> boven de grens</div>`
    : `<h2>Max verlies 10%</h2><p class="sub">Nog geen stand.</p>`;
}

function renderPerBron(d) {
  const rij = (naam, x) => `<tr><td>${naam}</td><td>${x.n}</td><td>${x.winst_pct == null ? "–" : x.winst_pct + "%"}</td>
    <td class="${kl(x.r_som)}">${rr(x.r_som)}</td><td class="${kl(x.r_gem)}">${rr(x.r_gem)}${x.marge != null ? " ± " + x.marge.toFixed(2) : ""}</td>
    <td class="${kl(x.netto)}">${eur(x.netto)}</td></tr>`;
  const b = d.per_bron;
  const weinig = b.alles.n < 10 ? `<p class="hint" style="margin:10px 0 0;">Nog maar ${b.alles.n} trade(s): de gemiddelden zeggen nog weinig (± = foutmarge).</p>` : "";
  document.getElementById("perBron").innerHTML = `<table class="mt"><thead><tr><th>Wie</th><th>Trades</th><th>Winst</th><th>Som R</th>
    <th>Gem. R</th><th>Netto</th></tr></thead><tbody>${rij("Bot (CBR Station)", b.bot)}${rij("Zelf", b.zelf)}${rij("Samen", b.alles)}</tbody></table>${weinig}`;
}

function renderTrades(d) {
  if (!d.trades.length) {
    document.getElementById("trades").innerHTML = `<div class="empty wachtend"><b>Nog geen gesloten FTMO-trades.</b>
      <span>Zodra jij of de bot een trade sluit, staat hij hier binnen een minuut.</span></div>`;
    return;
  }
  document.getElementById("trades").innerHTML = `<table class="mt"><thead><tr><th>Datum</th><th>Tijd</th><th>Wie</th><th>Richting</th>
    <th>Lot</th><th>Entry</th><th>SL</th><th>Exit</th><th>Reden</th><th>R</th><th>Netto</th></tr></thead><tbody>
    ${d.trades.map((t) => `<tr style="cursor:default"><td>${esc(t.datum)}</td><td>${esc(t.tijd)}</td>
      <td><span class="ftmo-tag ${t.bron}">${t.bron === "bot" ? "bot" : t.bron === "zelf" ? "zelf" : esc(t.bron)}</span></td>
      <td>${esc(t.richting)}</td><td>${t.lot}</td><td>${t.entry?.toFixed(2) ?? "–"}</td><td>${t.sl?.toFixed(2) ?? "–"}</td>
      <td>${t.exit?.toFixed(2) ?? "–"}</td><td>${esc(t.reden)}</td><td class="${kl(t.r)}">${rr(t.r)}</td>
      <td class="${kl(t.netto)}">${eur(t.netto)}</td></tr>`).join("")}</tbody></table>`;
}

async function laad() {
  let d;
  try { d = await api("/api/ftmo"); }
  catch (e) {
    document.getElementById("kpi").innerHTML = `<div class="panel"><b>Kon niet laden.</b> ${esc(e.message)}</div>`;
    return;
  }
  const st = d.status || {};
  document.getElementById("ftmoStatus").textContent = st.fout ? "⚠ " + st.fout : st.laatste ? "bijgewerkt " + st.laatste + (d.stand ? " · stand " + d.stand.ts : "") : "wacht op de eerste uitlezing…";
  renderKpi(d);
  renderGrenzen(d);
  renderPerBron(d);
  renderTrades(d);
}

laad();
setInterval(laad, 60000);
