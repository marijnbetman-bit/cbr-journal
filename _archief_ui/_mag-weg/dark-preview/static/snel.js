// Snelinvoer voor de telefoon — richting, checklist, RR, resultaat, foto. Klaar.
window.EIGEN_TOETSEN = true;   // dit scherm heeft eigen lettertoetsen

let CONFIG = null;
let richting = "";
const crits = { f2_bias: "maybe", f2_dxy: "maybe", f2_expansie: "maybe",
                f2_sweep: "maybe", f2_shift: "maybe", f2_entry: "maybe",
                f2_sl: "maybe", f2_tp: "maybe" };
const beoordeeld = new Set();
const na = { sl_nabijheid: "", tp_verloop: "" };
let bestand = null;
const emoties = new Set();

const KORT = { f2_bias: "1H-bias gevolgd", f2_dxy: "DXY invers",
               f2_expansie: "20+ min expansie", f2_sweep: "Sweep 1e uur",
               f2_shift: "Shift in biasrichting", f2_entry: "Entry op 50%",
               f2_sl: "SL op shift-extreme", f2_tp: "TP ≥ 1,5R" };

async function boot() {
  CONFIG = await api("/api/config");
  const d = qs("datum") || todayISO();
  document.getElementById("snelDatum").value = d;
  toonDatum();
  document.getElementById("snelDatum").addEventListener("change", toonDatum);

  renderChecklist();
  duo("snelRichting", (v) => { richting = v; }, () => richting);
  trio("snelSL", "sl_nabijheid");
  trio("snelTP", "tp_verloop");

  document.getElementById("snelFile").addEventListener("change", (e) => {
    bestand = e.target.files[0] || null;
    const p = document.getElementById("snelPreview");
    if (bestand) {
      document.getElementById("snelShotTekst").textContent = "📷 Andere foto kiezen";
      p.innerHTML = `<img src="${URL.createObjectURL(bestand)}" class="snel-preview" alt="" />`;
    } else { p.innerHTML = ""; }
  });

  renderEmoties();
  maakSpraakKnop("snelLes");
  document.getElementById("snelSave").addEventListener("click", opslaan);
  updateGradeUI();
}

function renderEmoties() {
  const box = document.getElementById("snelEmoties");
  if (!box || !CONFIG.emoties) return;
  box.innerHTML = "";
  CONFIG.emoties.forEach((e) => {
    const chip = document.createElement("div");
    chip.className = "chip emotie" + (e.goed ? " goed" : " let-op") + (emoties.has(e.key) ? " on" : "");
    chip.textContent = e.label;
    chip.addEventListener("click", () => {
      if (emoties.has(e.key)) emoties.delete(e.key); else emoties.add(e.key);
      renderEmoties();
    });
    box.appendChild(chip);
  });
}

function toonDatum() {
  const iso = document.getElementById("snelDatum").value;
  const d = new Date(iso + "T12:00:00");
  document.getElementById("snelDatumTekst").textContent =
    d.toLocaleDateString("nl-NL", { weekday: "long", day: "numeric", month: "long" });
}

function duo(id, set, get) {
  document.querySelectorAll(`#${id} button`).forEach((b) => {
    b.addEventListener("click", () => {
      set(get() === b.dataset.v ? "" : b.dataset.v);
      document.querySelectorAll(`#${id} button`).forEach((x) =>
        x.classList.toggle("on", x.dataset.v === get()));
    });
  });
}

function trio(id, veld) {
  document.querySelectorAll(`#${id} button`).forEach((b) => {
    b.addEventListener("click", () => {
      na[veld] = na[veld] === b.dataset.v ? "" : b.dataset.v;
      document.querySelectorAll(`#${id} button`).forEach((x) =>
        x.classList.toggle("on", x.dataset.v === na[veld]));
    });
  });
}

function renderChecklist() {
  const box = document.getElementById("snelChecklist");
  box.innerHTML = "";
  CONFIG.criteria.forEach((c) => {
    const row = document.createElement("div");
    row.className = "snel-crit" + (c.critical ? " kritisch" : "");
    row.innerHTML = `
      <div class="snel-crit-naam"><b>${c.num}.</b> ${KORT[c.key]}
        ${c.critical ? '<span class="k">kritisch</span>' : ""}</div>
      <div class="snel-trio" data-key="${c.key}">
        <button type="button" data-v="yes">✓</button>
        <button type="button" data-v="maybe">?</button>
        <button type="button" data-v="no">✗</button>
      </div>`;
    box.appendChild(row);
    row.querySelectorAll("button").forEach((b) => {
      b.addEventListener("click", () => {
        crits[c.key] = b.dataset.v;
        beoordeeld.add(c.key);
        row.querySelectorAll("button").forEach((x) => {
          x.className = "";
          if (x.dataset.v === crits[c.key]) x.classList.add("on-" + crits[c.key]);
        });
        updateGradeUI();
      });
    });
  });
}

function updateGradeUI() {
  const g = computeGrade(crits);
  const badge = document.getElementById("snelGrade");
  badge.textContent = g;
  badge.className = "grade big grade-" + g;
  const klaar = beoordeeld.size >= ALL_CRITS.length;
  document.getElementById("snelSlot").style.display = klaar ? "none" : "block";
  document.getElementById("snelUitkomst").style.display = klaar ? "" : "none";
}

async function opslaan() {
  const datum = document.getElementById("snelDatum").value;
  if (!datum) { toast("Datum ontbreekt", true); return; }
  const data = {
    datum, tijd_entry: document.getElementById("snelTijd").value || "",
    instrument: "XAUUSD", sessie: "2e uur Londen", richting,
    ...crits,
    rr: parseFloat(document.getElementById("snelRR").value) || null,
    risk_eur: parseFloat(document.getElementById("snelRisk").value) || null,
    resultaat_eur: parseFloat(document.getElementById("snelRes").value) || null,
    charges: -0.06,
    sl_nabijheid: na.sl_nabijheid, tp_verloop: na.tp_verloop,
    les: document.getElementById("snelLes").value || "",
    mentale_staat: [...emoties].join(", "),
    status: "genomen",
  };
  try {
    const res = await api("/api/trade", { method: "POST", body: JSON.stringify(data) });
    if (bestand) {
      const fd = new FormData();
      fd.append("file", bestand); fd.append("datum", datum);
      fd.append("trade_id", res.id); fd.append("type", "entry");
      await fetch("/api/screenshot", { method: "POST", body: fd });
    }
    location.href = "/?datum=" + encodeURIComponent(datum);
  } catch (e) { toast("Opslaan mislukt: " + e.message, true); }
}

boot();
