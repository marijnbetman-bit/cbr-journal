// Simpele trade-toevoeger: alles op één scherm, niets op slot.
window.EIGEN_TOETSEN = true;

let CONFIG = null;
let richting = "";
let bestanden = [];          // nog niet geüpload
const crits = {
  f2_bias: "maybe", f2_dxy: "maybe", f2_expansie: "maybe", f2_sweep: "maybe",
  f2_shift: "maybe", f2_entry: "maybe", f2_sl: "maybe", f2_tp: "maybe",
};

async function boot() {
  CONFIG = await api("/api/config");
  const d = qs("datum") || todayISO();
  document.getElementById("nwDatum").value = d;
  const uitgebreid = document.getElementById("uitgebreid");
  if (uitgebreid) uitgebreid.href = "/trade?datum=" + d;

  renderRegels();
  duoRichting();
  setupDrop();
  maakSpraakKnop("nwLes");

  ["nwResultaat", "nwKosten"].forEach((id) =>
    document.getElementById(id).addEventListener("input", toonNetto));
  toonNetto();

  // Slimme defaults van je vorige trade: kosten, risk, richting.
  try {
    const l = await api("/api/laatste_trade");
    if (l.gevonden) {
      const w = l.waarden;
      if (w.charges != null) document.getElementById("nwKosten").value = w.charges;
      if (w.risk_eur != null) document.getElementById("nwRisk").value = w.risk_eur;
      toonNetto();
    }
  } catch (e) {}

  document.getElementById("nwSave").addEventListener("click", opslaan);
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); opslaan(); }
  });
  updateGrade();
}

// ---------- de vijf regels ----------
function renderRegels() {
  const box = document.getElementById("nwRegels");
  box.innerHTML = "";
  CONFIG.criteria.forEach((c) => {
    const rij = document.createElement("div");
    rij.className = "nw-regel" + (c.critical ? " kritisch" : "");
    rij.innerHTML = `
      <div class="nr-num">${c.num}</div>
      <div class="nr-info">
        <div class="nr-titel">${c.title}
          ${c.critical ? '<span class="crit-badge-kritisch">kritisch</span>' : ""}</div>
        <div class="nr-help">${c.help}</div>
      </div>
      <div class="nr-keuze" data-key="${c.key}">
        <button type="button" data-v="yes"><b>✓</b><span>goed</span></button>
        <button type="button" data-v="maybe"><b>?</b><span>twijfel</span></button>
        <button type="button" data-v="no"><b>✗</b><span>niet</span></button>
      </div>`;
    box.appendChild(rij);
    rij.querySelectorAll(".nr-keuze button").forEach((b) => {
      b.addEventListener("click", () => {
        crits[c.key] = b.dataset.v;
        verfRegel(c.key);
        updateGrade();
      });
    });
    verfRegel(c.key);
  });
}

function verfRegel(key) {
  const vak = document.querySelector(`.nr-keuze[data-key="${key}"]`);
  vak.querySelectorAll("button").forEach((b) => {
    b.className = b.dataset.v === crits[key] ? "on-" + crits[key] : "";
  });
  vak.closest(".nw-regel").className =
    "nw-regel " + (CONFIG.criteria.find((c) => c.key === key).critical ? "kritisch " : "") + crits[key];
}

function updateGrade() {
  const g = computeGrade(crits);
  const badge = document.getElementById("nwGrade");
  badge.textContent = g;
  badge.className = "grade big grade-" + g;
  document.getElementById("nwGradeTekst").textContent = GRADE_DESC[g];
  document.getElementById("nwGradeTekst").className = "sub" + (g === "C" ? " waarschuwing-tekst" : "");
}

function duoRichting() {
  document.querySelectorAll("#nwRichting button").forEach((b) => {
    b.addEventListener("click", () => {
      richting = richting === b.dataset.v ? "" : b.dataset.v;
      document.querySelectorAll("#nwRichting button").forEach((x) => {
        x.className = richting === x.dataset.v ? "on-" + x.dataset.v : "";
      });
    });
  });
}

function toonNetto() {
  const r = parseFloat(document.getElementById("nwResultaat").value);
  const k = parseFloat(document.getElementById("nwKosten").value) || 0;
  const box = document.getElementById("nwNetto");
  if (isNaN(r)) { box.innerHTML = ""; return; }
  const netto = r + k;
  box.innerHTML = `<span class="nn-l">Netto na kosten</span>
    <b class="${netto >= 0 ? "pos" : "neg"}">${fmtEur(netto)}</b>`;
}

// ---------- screenshots ----------
function setupDrop() {
  const zone = document.getElementById("nwDrop");
  ["dragenter", "dragover"].forEach((ev) =>
    zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) =>
    zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("over"); }));
  zone.addEventListener("drop", (e) => {
    [...(e.dataTransfer.files || [])]
      .filter((f) => f.type.startsWith("image/"))
      .forEach((f) => bestanden.push(f));
    renderShots();
  });
}

function renderShots() {
  const box = document.getElementById("nwShots");
  box.innerHTML = bestanden.map((f, i) => `
    <figure class="nw-shot">
      <img src="${URL.createObjectURL(f)}" alt="" />
      <figcaption>${f.name}</figcaption>
      <button type="button" class="nw-weg" data-i="${i}" title="Weghalen">✕</button>
    </figure>`).join("");
  box.querySelectorAll(".nw-weg").forEach((b) => {
    b.addEventListener("click", () => {
      bestanden.splice(parseInt(b.dataset.i, 10), 1);
      renderShots();
    });
  });
}

// ---------- opslaan ----------
async function opslaan() {
  const datum = document.getElementById("nwDatum").value;
  if (!datum) { toast("Vul een datum in", true); return; }
  const knop = document.getElementById("nwSave");
  knop.disabled = true;
  document.getElementById("nwHint").textContent = "Bezig met opslaan…";

  const data = {
    datum,
    tijd_entry: document.getElementById("nwTijd").value || "",
    instrument: "XAUUSD",
    sessie: "2e uur Londen",
    richting,
    ...crits,
    rr: parseFloat(document.getElementById("nwRR").value) || null,
    risk_eur: parseFloat(document.getElementById("nwRisk").value) || null,
    resultaat_eur: parseFloat(document.getElementById("nwResultaat").value) || null,
    charges: parseFloat(document.getElementById("nwKosten").value) || 0,
    les: document.getElementById("nwLes").value.trim(),
    tags: document.getElementById("nwTags").value.trim(),
    status: "genomen",
    bron: "live",
  };

  try {
    const res = await api("/api/trade", { method: "POST", body: JSON.stringify(data) });
    for (const f of bestanden) {
      const fd = new FormData();
      fd.append("file", f); fd.append("datum", datum);
      fd.append("trade_id", res.id); fd.append("type", "entry");
      fd.append("beschrijving", document.getElementById("nwLes").value.trim().slice(0, 120));
      await fetch("/api/screenshot", { method: "POST", body: fd });
    }
    // Punt 9 -- eerst het muntje, dan pas doornavigeren.
    await maybeCelebrate({ result: data.resultaat_eur, grade: res.grade });
    location.href = "/log?datum=" + encodeURIComponent(datum);
  } catch (e) {
    knop.disabled = false;
    document.getElementById("nwHint").textContent = "";
    toast("Opslaan mislukt: " + e.message, true);
  }
}

boot();
