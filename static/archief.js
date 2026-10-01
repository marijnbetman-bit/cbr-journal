/* =====================================================================
   Fase 1 -- archief. Alleen lezen.

   Bewust een eigen scherm met een eigen renderer: de fase-1-trades zijn
   met de oude vijf criteria beoordeeld, en die komen uit /api/archief mee.
   Zo blijft het overzicht van fase 2 schoon zonder dat hier iets verdwijnt.
   ===================================================================== */

let CRITS = [];

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function eur(v) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  return (n > 0 ? "+" : "") + n.toFixed(2).replace(".", ",");
}

function kleurBedrag(v) {
  if (v === null || v === undefined) return "var(--muted)";
  return Number(v) > 0 ? "var(--green)" : Number(v) < 0 ? "var(--red)" : "var(--muted)";
}

function critRegel(t) {
  if (!CRITS.length) return "";
  return `<div class="arch-crits">${CRITS.map((c) => {
    const v = t[c.key];
    const kl = v === "yes" ? "yes" : v === "no" ? "no" : "";
    const sym = v === "yes" ? "✓" : v === "no" ? "✗" : "?";
    return `<span class="${kl}" title="${esc(c.title)}">${sym} ${esc(c.title)}</span>`;
  }).join("")}</div>`;
}

function shots(lijst) {
  if (!lijst || !lijst.length) return "";
  return `<div class="arch-shots">${lijst.map((s) =>
    `<a href="/${esc(s.pad)}" target="_blank" title="${esc(s.beschrijving || "")}">
       <img src="/${esc(s.pad)}" alt="${esc(s.beschrijving || "screenshot")}" loading="lazy" />
     </a>`).join("")}</div>`;
}

function tradeKaart(t) {
  const res = t.status === "genomen"
    ? `<span class="res" style="color:${kleurBedrag(t.resultaat_eur)}">${eur(t.resultaat_eur)}</span>`
    : `<span class="res" style="color:var(--muted)">niet genomen</span>`;
  const status = t.status !== "genomen"
    ? `<span class="st">${esc(t.status)}${t.skip_reden ? " · " + esc(t.skip_reden) : ""}</span>` : "";
  return `<div class="arch-rij">
    <div class="arch-hd">
      <span class="id">#${t.id}</span>
      <span class="g ${esc(t.grade)}">${esc(t.grade)}</span>
      ${t.richting ? `<span class="ri">${esc(t.richting)}</span>` : ""}
      ${status}
      ${res}
    </div>
    ${critRegel(t)}
    <div class="arch-tekst">
      ${t.notities ? `<div>${esc(t.notities)}</div>` : ""}
      ${t.les ? `<div class="les"><b>Les:</b> ${esc(t.les)}</div>` : ""}
      ${t.foutcodes ? `<div style="margin-top:5px;color:var(--red);font-size:12.5px">Foutcodes: ${esc(t.foutcodes)}</div>` : ""}
    </div>
    ${shots(t.screenshots)}
  </div>`;
}

function noTradeKaart(n) {
  return `<div class="arch-rij">
    <div class="arch-hd">
      <span class="id">${esc(n.datum)}${n.tijd ? " · " + esc(n.tijd) : ""}</span>
    </div>
    <div class="arch-tekst">
      ${n.reden ? `<div><b>${esc(n.reden)}</b></div>` : ""}
      ${n.wat_zag_ik ? `<div style="margin-top:5px">${esc(n.wat_zag_ik)}</div>` : ""}
    </div>
    ${shots(n.screenshots)}
  </div>`;
}

async function boot() {
  const d = await api("/api/archief");
  CRITS = d.criteria || [];
  const s = d.samenvatting;

  document.getElementById("kpi").innerHTML = [
    ["Trades genomen", s.aantal],
    ["Winrate", s.winrate + "%"],
    ["Netto", eur(s.netto)],
    ["Bewust overgeslagen", s.overgeslagen],
    ["No-trades", s.no_trades],
    ["Periode", (s.van || "").slice(5) + " → " + (s.tot || "").slice(5)],
  ].map(([k, v]) =>
    `<div class="cel"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");

  const perDag = {};
  (d.trades || []).forEach((t) => { (perDag[t.datum] = perDag[t.datum] || []).push(t); });
  const dagen = Object.keys(perDag).sort();
  document.getElementById("inhoud").innerHTML = dagen.length
    ? dagen.map((dag) =>
        `<div class="arch-dag">${dag}</div>` + perDag[dag].map(tradeKaart).join("")).join("")
    : `<div class="arch-leeg">Geen trades in het archief.</div>`;

  document.getElementById("notrades").innerHTML = (d.no_trades || []).length
    ? d.no_trades.map(noTradeKaart).join("")
    : `<div class="arch-leeg">Geen no-trades in het archief.</div>`;
}

boot();
