// Signalen & jouw oordeel (1 okt 2026): elk 'klaar'-signaal met chart, oordeel en opmerkingen.

const OORDEEL_VOLGORDE = ["genomen", "niet", "gemist_wel", "gemist_niet"];
const OORDEEL_KNOP = {
  genomen: "✅ Genomen",
  niet: "❌ Niet genomen",
  gemist_wel: "⏱ Gemist: wel",
  gemist_niet: "⏱ Gemist: niet",
};
const OORDEEL_FILTER = {
  alle: "Alle", geen: "Zonder oordeel", genomen: "Genomen", niet: "Niet genomen",
  gemist_wel: "Gemist: wel", gemist_niet: "Gemist: niet",
};
const UITKOMST_TEKST = {
  tp: "TP geraakt", sl: "SL geraakt", onbeslist: "Onbeslist", nooit_gevuld: "Nooit gevuld",
  bezig: "Loopt nog", wacht: "Wacht op entry", vervallen: "Vervallen",
};
const PAGINA = 30;

let periode = 30;
let filter = "alle";
let toon = PAGINA;
let DATA = { signalen: [], statistiek: [] };

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function nl(n, d = 1) { return Number(n).toFixed(d).replace(".", ","); }
function vanDatum(dagen) {
  if (!dagen) return null;
  const d = new Date(Date.now() - dagen * 86400000);
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}
function datumLabel(iso) {
  try {
    return new Date(iso + "T12:00:00").toLocaleDateString("nl-NL", { weekday: "short", day: "numeric", month: "short" });
  } catch (e) { return iso; }
}
function tijdLabel(ts) {
  return String(ts || "").slice(5, 16).replace("T", " ");
}
function sleutelVan(r) { return r.oordeel || "geen"; }

function boot() {
  document.querySelectorAll("#periodeTabs button").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#periodeTabs button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      periode = parseInt(b.dataset.p, 10);
      toon = PAGINA;
      laad();
    });
  });
  laad();
}

async function laad() {
  const van = vanDatum(periode);
  const q = van ? "?van=" + van : "";
  document.getElementById("csvLink").href = "/export/signalen.csv" + q;
  document.getElementById("csvV3Link").href = "/export/v3_signalen.csv" + q;
  laadV3(q);
  try {
    DATA = await api("/api/signalen/dataset" + q);
  } catch (e) {
    document.getElementById("sgLijst").innerHTML = `<div class="empty">Kon de signalen niet laden: ${esc(e.message)}</div>`;
    return;
  }
  renderKop();
  renderStat();
  renderFilter();
  renderLijst();
}

// v3-signalen (8 okt 2026): jouw oordeel uit de getrapte Telegram-knoppen (ja + grade / nee + redenen / niet gezien).
async function laadV3(q) {
  const box = document.getElementById("v3Blok");
  let V;
  try { V = await api("/api/v3/signalen" + q); }
  catch (e) { box.innerHTML = ""; return; }                     // journal zonder v3: blok weglaten
  const t = V.telling || {};
  const rij = (r) => {
    const opm = (r.opmerkingen || []).map((o) => `<div class="sg-opm-regel"><span class="ts">${esc(tijdLabel(o.ts))}</span>${esc(o.tekst)}</div>`).join("");
    const oordeel = r.oordeel ? esc(r.samenvatting) + (r.afgerond ? "" : ' <span class="sg-sub">(nog niet klaar)</span>') : '<span class="sg-sub">open</span>';
    return `<tr><td>${esc(datumLabel(r.datum))} ${esc(r.tijd || "")}</td><td>${esc((r.trade || "").toUpperCase())}${r.orders > 1 ? ` <span class="sg-sub">(${r.orders} orders)</span>` : ""}</td>
      <td class="num">${r.entry == null ? "–" : nl(r.entry, 2)}</td><td class="num">${r.sl == null ? "–" : nl(r.sl, 2)}</td>
      <td>${oordeel}</td><td>${r.grade ? esc(r.grade) : "–"}</td><td>${(r.redenen || []).concat(r.pluspunten || []).length ? esc((r.redenen || []).concat(r.pluspunten || []).join(", ")) : "–"}</td><td>${opm || "–"}</td></tr>`;
  };
  box.innerHTML = `
    <div class="panel">
      <h2>v3-signalen &amp; jouw labels</h2>
      <p class="sub">Uit Telegram: eerst ✅ ja / ❌ nee / 👀 niet gezien, dan bij ja de grade (A/B/C) en bij nee de reden(en).
        Eén label per sweep. Antwoord op een v3-bericht = opmerking.</p>
      <div class="mt-bar">
        <div class="mt-cell accent"><div class="k">v3-signalen</div><div class="val">${t.signalen || 0}</div></div>
        <div class="mt-cell"><div class="k">Ja (A / B / C)</div><div class="val">${t.ja || 0} <span class="sg-sub">(${t.A || 0} / ${t.B || 0} / ${t.C || 0})</span></div></div>
        <div class="mt-cell"><div class="k">Nee</div><div class="val">${t.nee || 0}</div></div>
        <div class="mt-cell"><div class="k">Niet gezien</div><div class="val">${t.niet_gezien || 0}</div></div>
        <div class="mt-cell"><div class="k">Nog open</div><div class="val ${t.open ? "neg" : ""}">${t.open || 0}</div></div>
      </div>
      <div class="sg-wrap"><table class="sg-stat">
        <thead><tr><th>Wanneer</th><th>Richting</th><th class="num">Entry</th><th class="num">SL</th><th>Oordeel</th><th>Grade</th><th>Redenen / pluspunten</th><th>Opmerkingen</th></tr></thead>
        <tbody>${(V.signalen || []).slice(0, 200).map(rij).join("") || '<tr><td colspan="8" class="sg-sub">Nog geen v3-signalen in deze periode.</td></tr>'}</tbody>
      </table></div>
    </div>`;
}

function renderKop() {
  const r = DATA.signalen;
  const tel = (f) => r.filter(f).length;
  const tp = tel((x) => x.uitkomst === "tp"), sl = tel((x) => x.uitkomst === "sl");
  const win = tp + sl ? Math.round((100 * tp) / (tp + sl)) : null;
  document.getElementById("sgKop").innerHTML = `
    <div class="mt-bar">
      <div class="mt-cell accent"><div class="k">Klaar-signalen</div><div class="val">${r.length}</div></div>
      <div class="mt-cell"><div class="k">Genomen</div><div class="val">${tel((x) => x.oordeel === "genomen")}</div></div>
      <div class="mt-cell"><div class="k">Gemist (gezien achteraf)</div><div class="val">${tel((x) => x.oordeel === "gemist_wel" || x.oordeel === "gemist_niet")}</div></div>
      <div class="mt-cell"><div class="k">Nog zonder oordeel</div><div class="val ${tel((x) => !x.oordeel && x.uitkomst !== "nooit_gevuld") ? "neg" : ""}">${tel((x) => !x.oordeel)}</div></div>
      <div class="mt-cell"><div class="k">Win% van alle signalen</div><div class="val">${win === null ? "–" : win + "%"}</div></div>
    </div>`;
}

function renderStat() {
  const st = DATA.statistiek || [];
  const box = document.getElementById("sgStat");
  if (!st.length) { box.innerHTML = ""; return; }
  const naam = (k) => (k === "geen" ? "Nog geen oordeel" : (OORDEEL_KNOP[k] || k));
  box.innerHTML = `
    <div class="panel">
      <h2>Jouw oordeel tegenover wat er gebeurde</h2>
      <p class="sub">Voegt je oordeel iets toe? Vergelijk het win% van “Gemist: wel” met “Gemist: niet”.</p>
      <div class="sg-wrap"><table class="sg-stat">
        <thead><tr><th>Oordeel</th><th class="num">Signalen</th><th class="num">TP</th><th class="num">SL</th>
          <th class="num">Nooit gevuld</th><th class="num">Win%</th><th class="num">Som R</th></tr></thead>
        <tbody>${st.map((g) => `<tr>
          <td>${esc(naam(g.oordeel))}</td><td class="num">${g.n}</td><td class="num">${g.tp}</td><td class="num">${g.sl}</td>
          <td class="num">${g.nooit_gevuld}</td><td class="num">${g.winrate === null ? "–" : g.winrate + "%"}</td>
          <td class="num ${g.hyp_r > 0 ? "pos" : g.hyp_r < 0 ? "neg" : ""}">${g.hyp_r > 0 ? "+" : ""}${nl(g.hyp_r, 1)}</td></tr>`).join("")}
        </tbody></table></div>
      <p class="sg-uitleg">Win% = TP / (TP + SL), hypothetisch: alsof je precies op de entry was ingestapt. “Nooit gevuld”
        (prijs kwam niet terug naar de entry) telt niet mee. Som R telt +1R per TP en −1R per SL.</p>
    </div>`;
}

function renderFilter() {
  const r = DATA.signalen;
  const tel = (k) => (k === "alle" ? r.length : r.filter((x) => sleutelVan(x) === k).length);
  document.getElementById("sgFilter").innerHTML = Object.keys(OORDEEL_FILTER).map((k) =>
    `<span class="chip ${filter === k ? "on" : ""}" data-f="${k}">${OORDEEL_FILTER[k]}<span class="sg-n">${tel(k)}</span></span>`).join("");
  document.querySelectorAll("#sgFilter .chip").forEach((c) => c.addEventListener("click", () => {
    filter = c.dataset.f;
    toon = PAGINA;
    renderFilter();
    renderLijst();
  }));
}

function zichtbaar() {
  return DATA.signalen.filter((x) => filter === "alle" || sleutelVan(x) === filter);
}

function uitkomstChip(r) {
  let t = UITKOMST_TEKST[r.uitkomst] || r.uitkomst;
  if (r.uitkomst === "tp" && r.hyp_r != null) t += " (+" + nl(r.hyp_r, 1) + "R)";
  if (r.uitkomst === "sl") t += " (−1R)";
  return `<span class="sg-uitkomst ${esc(r.uitkomst)}">${esc(t)}</span>`;
}

function kaartHtml(r) {
  const richting = (r.trade || "").toUpperCase();
  const sub = [];
  if (r.risico_points != null) sub.push("risico " + Math.round(r.risico_points) + " pts");
  if (r.impuls_pts != null) sub.push("impuls " + r.impuls_pts + " pts");
  if (r.in_venster === 0) sub.push("buiten venster");
  if (r.genomen_trade_id) sub.push("trade #" + r.genomen_trade_id + (r.genomen_r != null ? " (" + (r.genomen_r > 0 ? "+" : "") + nl(r.genomen_r, 2) + "R)" : ""));
  const knoppen = OORDEEL_VOLGORDE.map((k) =>
    `<button type="button" class="sg-knop ${r.oordeel === k ? "on" : ""}" data-o="${k}">${OORDEEL_KNOP[k]}</button>`).join("");
  const opm = (r.opmerkingen || []).map((o) =>
    `<div class="sg-opm-regel"><span class="ts">${esc(tijdLabel(o.ts))}</span>${esc(o.tekst)}</div>`).join("");
  const chart = r.chart_url
    ? `<img loading="lazy" alt="Chart van signaal ${r.id}" src="${r.chart_url}">`
    : `<div class="sg-geen">Geen chart voor dit signaal.</div>`;
  return `
    <div class="sg-kaart" data-id="${r.id}">
      <div class="sg-kaart-kop">
        <span class="sg-titel">${esc(datumLabel(r.datum))} · ${esc(r.tijd_klaar || "")} · ${esc(richting)}</span>
        ${uitkomstChip(r)}
        <span class="sg-sub">${esc(sub.join(" · "))}</span>
        <span class="spacer"></span>
        <span class="sg-sub mono">#${r.id}</span>
      </div>
      <div class="sg-chart">${chart}</div>
      <div class="sg-onder">
        <div class="sg-oordeel"><span class="lbl">Jouw oordeel</span>${knoppen}</div>
        <div class="sg-opm">
          ${opm}
          <form autocomplete="off"><input type="text" maxlength="600" placeholder="Opmerking, bijv. waarom wel of niet…" aria-label="Opmerking bij signaal ${r.id}">
            <button class="btn" type="submit">Opslaan</button></form>
        </div>
      </div>
    </div>`;
}

function renderLijst() {
  const box = document.getElementById("sgLijst");
  const rijen = zichtbaar();
  if (!rijen.length) {
    box.innerHTML = `<div class="empty">${DATA.signalen.length
      ? "Geen signalen met dit filter."
      : "Nog geen klaar-signalen in deze periode. Zodra de wachter een setup klaar heeft staan (entry, SL en TP), verschijnt hij hier met een chart."}</div>`;
    return;
  }
  const deel = rijen.slice(0, toon);
  box.innerHTML = deel.map(kaartHtml).join("") +
    (rijen.length > toon ? `<p style="text-align:center"><button class="btn" id="sgMeer">Toon meer (${rijen.length - toon})</button></p>` : "");
  const meer = document.getElementById("sgMeer");
  if (meer) meer.addEventListener("click", () => { toon += PAGINA; renderLijst(); });
  box.querySelectorAll(".sg-kaart").forEach(koppelKaart);
}

function koppelKaart(el) {
  const id = parseInt(el.dataset.id, 10);
  const r = DATA.signalen.find((x) => x.id === id);
  el.querySelectorAll(".sg-knop").forEach((b) => b.addEventListener("click", async () => {
    try {
      await api(`/api/signalen/${id}/oordeel`, { method: "POST", body: JSON.stringify({ oordeel: b.dataset.o }) });
      r.oordeel = b.dataset.o;
      r.oordeel_ts = new Date().toISOString();
      renderKop(); renderFilter();
      // statistiek komt van de server: even verversen zonder de lijst te herladen
      const van = vanDatum(periode);
      api("/api/signalen/dataset" + (van ? "?van=" + van : "")).then((d) => { DATA.statistiek = d.statistiek; renderStat(); });
      el.querySelectorAll(".sg-knop").forEach((x) => x.classList.toggle("on", x === b));
      const img = el.querySelector(".sg-chart img");
      if (img) img.src = r.chart_url + "?t=" + Date.now();      // chart toont je oordeel
      toast("Oordeel opgeslagen");
    } catch (e) { toast("Opslaan mislukt: " + e.message, true); }
  }));
  koppelOpmerkingForm(el, id, r);
}

function koppelOpmerkingForm(el, id, r) {
  const form = el.querySelector(".sg-opm form");
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const inp = form.querySelector("input");
    const tekst = inp.value.trim();
    if (!tekst) return;
    try {
      const d = await api(`/api/signalen/${id}/opmerking`, { method: "POST", body: JSON.stringify({ tekst }) });
      r.opmerkingen = d.opmerkingen;
      const regel = document.createElement("div");
      regel.className = "sg-opm-regel";
      regel.innerHTML = `<span class="ts">${esc(tijdLabel(d.opmerkingen[d.opmerkingen.length - 1].ts))}</span>${esc(tekst)}`;
      form.parentNode.insertBefore(regel, form);
      inp.value = "";
      toast("Opmerking opgeslagen");
    } catch (e) { toast("Opslaan mislukt: " + e.message, true); }
  });
}

document.addEventListener("DOMContentLoaded", boot);
