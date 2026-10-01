// Trade toevoegen / bewerken — met LIVE meeveranderende grade.
window.EIGEN_TOETSEN = true;   // dit scherm heeft eigen lettertoetsen

let CONFIG = null;
let tradeId = qs("id");                 // aanwezig = bewerken
const selectedFouten = new Set();
let richting = "";
let bron = "live";
let actiefCrit = 0;              // fase 9.2 -- welk criterium de sneltoetsen raken
const emoties = new Set();       // fase 9.3
const naAfloop = {
  sl_nabijheid: "", tp_verloop: "",
  // Ronde 2
  shift_kwaliteit: "", volume_hoog: "", overextensie_kwaliteit: "", sl_dan_tp: "",
  luck_flag: "",
};
const planMode = qs("plan") === "1";
let zekerheid = null;
let status = planMode ? "gepland" : "genomen";
const beoordeeld = new Set();   // welke criteria je bewust hebt aangeraakt
let existingShots = [];                 // van de server (bij bewerken)
let pendingShots = [];                  // nieuw gesleept, nog niet geupload
const SHOT_TYPES = ["pre-entry", "entry", "post-exit"];

// Huidige checklist-waarden
const crits = {
  f2_bias: "maybe",
  f2_dxy: "maybe",
  f2_expansie: "maybe",
  f2_sweep: "maybe",
  f2_shift: "maybe",
  f2_entry: "maybe",
  f2_sl: "maybe",
  f2_tp: "maybe",
};

async function boot() {
  // Knoppen eerst koppelen: gaat verderop iets mis, dan werken opslaan en
  // verwijderen toch (dat was de oorzaak dat 'Verwijderen' niets deed).
  document.getElementById("saveBtn").addEventListener("click", save);
  document.getElementById("deleteBtn").addEventListener("click", remove);
  CONFIG = await api("/api/config");
  renderChecklist();
  renderFoutcodes();

  if (tradeId) {
    document.getElementById("formTitle").textContent = "Trade bewerken";
    document.getElementById("deleteBtn").style.display = "inline-flex";
    await loadTrade(tradeId);
  } else {
    document.getElementById("datum").value = qs("datum") || todayISO();
    await vulDefaults();
  }

  if (planMode) {
    document.getElementById("formTitle").textContent = "Trade plannen";
    document.getElementById("saveBtn").textContent = "Plan opslaan";
    document.querySelectorAll("[data-na-afloop]").forEach((el) => el.remove());
    document.getElementById("geenTradeBanner").remove();
  }

  updateGrade();
  updateSlot();
  setupRichting();
  setupZekerheid();
  setupNaAfloop();
  ["sweep_overshoot_points", "sl_afstand_points"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", toonSlMarge);
  });
  const minEl = document.getElementById("minuten_in_hourly");
  if (minEl) minEl.addEventListener("input", toonMinutenHint);
  ["notities", "les", "exit_reden"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", toonTwijfelBanner);
  });
  document.querySelectorAll("#shift_kwaliteit button").forEach((b2) =>
    b2.addEventListener("click", () => setTimeout(toonTwijfelBanner, 0)));
  const tEl = document.getElementById("tijd_entry");
  if (tEl) tEl.addEventListener("input", toonVensterHint);
  const dEl = document.getElementById("datum");
  if (dEl) dEl.addEventListener("change", checkDagmaximum);
  try {
    const cfg = await api("/api/settings");
    VENSTER = { van: cfg.venster_van || "10:00", tot: cfg.venster_tot || "11:00" };
    try { if (cfg.venster) VENSTER.blokken = JSON.parse(cfg.venster); } catch (e2) { /* 1 blok */ }
    MAX_TRADES_DAG = parseInt(cfg.max_trades_dag, 10) || 0;
  } catch (e) { /* standaardwaarden blijven staan */ }
  toonSlMarge(); toonMinutenHint(); toonTwijfelBanner();
  toonVensterHint(); checkDagmaximum();
  setupScreenshots();
  renderShots();
  renderEmoties();
  laadTagSuggesties();
  maakSpraakKnop("les");
  maakSpraakKnop("notities");
  setupSneltoetsen();
  setupKopieer();
  document.getElementById("datum").addEventListener("change", checkDagregels);
  checkDagregels();
}

// ---------- 9.1 Slimme defaults ----------
let LAATSTE = null;

async function vulDefaults() {
  try { LAATSTE = await api("/api/laatste_trade"); } catch (e) { return; }
  if (!LAATSTE || !LAATSTE.gevonden) { toonKopieer(false); return; }
  const w = LAATSTE.waarden;
  // Alleen wat vrijwel altijd hetzelfde is -- nooit de uitkomst.
  if (w.instrument) document.getElementById("instrument").value = w.instrument;
  if (w.sessie) document.getElementById("sessie").value = w.sessie;
  if (w.charges !== null && w.charges !== undefined) document.getElementById("charges").value = w.charges;
  if (w.risk_eur !== null && w.risk_eur !== undefined) document.getElementById("risk_eur").value = w.risk_eur;
  bron = w.bron || "live";
  paintBron();
  toonKopieer(true);
}

function toonKopieer(aan) {
  const k = document.getElementById("kopieerVorige");
  if (k) k.style.display = aan ? "" : "none";
}

function setupKopieer() {
  const k = document.getElementById("kopieerVorige");
  if (!k) return;
  if (tradeId) { k.style.display = "none"; return; }
  k.addEventListener("click", () => {
    if (!LAATSTE || !LAATSTE.gevonden) return;
    const w = LAATSTE.waarden;
    richting = w.richting || "";
    paintRichting();
    zekerheid = w.zekerheid || null;
    paintZekerheid();
    if (w.tijd_entry) document.getElementById("tijd_entry").value = w.tijd_entry;
    emoties.clear();
    (w.mentale_staat || "").split(",").map((x) => x.trim()).filter(Boolean)
      .forEach((x) => emoties.add(x));
    renderEmoties();
    toast("Overgenomen van je trade van " + LAATSTE.datum);
  });
}

// ---------- 12.4 Tags ----------
async function laadTagSuggesties() {
  const box = document.getElementById("tagSuggesties");
  if (!box) return;
  let d;
  try { d = await api("/api/tags"); } catch (e) { return; }
  if (!d.lijst.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<span class="tag-hint">eerder gebruikt:</span>` +
    d.lijst.slice(0, 12).map((t) =>
      `<span class="chip tag-sug" data-t="${t.tag}">${t.tag} <i>${t.aantal}</i></span>`).join("");
  box.querySelectorAll(".tag-sug").forEach((el) => {
    el.addEventListener("click", () => {
      const veld = document.getElementById("tags");
      const huidig = veld.value.split(",").map((x) => x.trim()).filter(Boolean);
      const i = huidig.indexOf(el.dataset.t);
      if (i >= 0) huidig.splice(i, 1); else huidig.push(el.dataset.t);
      veld.value = huidig.join(", ");
      verfTagSuggesties();
    });
  });
  verfTagSuggesties();
}

function verfTagSuggesties() {
  const veld = document.getElementById("tags");
  if (!veld) return;
  const gekozen = veld.value.split(",").map((x) => x.trim().toLowerCase()).filter(Boolean);
  document.querySelectorAll(".tag-sug").forEach((el) => {
    el.classList.toggle("on", gekozen.includes(el.dataset.t.toLowerCase()));
  });
}

// ---------- 9.4 Dagregels: de vangrail ----------
async function checkDagregels() {
  const box = document.getElementById("dagregelBanner");
  if (!box || tradeId) return;                 // alleen bij een nieuwe trade
  const d = document.getElementById("datum").value;
  if (!d) { box.innerHTML = ""; return; }
  let dag;
  try { dag = await api("/api/day/" + d); } catch (e) { return; }
  const r = dag.dagregels || {};
  if (!r.boodschap) { box.innerHTML = ""; return; }
  const hard = r.over_limiet || r.na_stop;
  const codes = r.over_limiet ? "P2 (overtrading)" : r.na_stop ? "P1 (revenge)" : "";
  box.innerHTML = `<div class="dagregel-banner ${hard ? "stop" : "let-op"}">
      <b>${hard ? "✋ Je eigen regels zeggen: niet meer vandaag" : "◉ Dagstand"}</b>
      <p>${r.boodschap}</p>
      ${codes ? `<p class="klein">Neem je 'm tóch, wees dan eerlijk in het foutenblok: ${codes}.</p>` : ""}
    </div>`;
}

// ---------- 9.2 Sneltoetsen ----------
const TOETS_WAARDE = { j: "yes", t: "maybe", n: "no" };

function setupSneltoetsen() {
  markeerActief();
  document.addEventListener("keydown", (e) => {
    const tag = (e.target.tagName || "").toLowerCase();
    if (e.ctrlKey && (e.key === "s" || e.key === "S")) { e.preventDefault(); save(); return; }
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    if (e.ctrlKey || e.altKey || e.metaKey) return;

    if (e.key >= "1" && e.key <= "8") {
      actiefCrit = parseInt(e.key, 10) - 1;
      markeerActief();
      e.preventDefault();
      return;
    }
    const v = TOETS_WAARDE[e.key.toLowerCase()];
    if (v) {
      const c = CONFIG.criteria[actiefCrit];
      if (!c) return;
      crits[c.key] = v;
      beoordeeld.add(c.key);
      paintSeg(c.key);
      updateGrade();
      updateSlot();
      if (actiefCrit < CONFIG.criteria.length - 1) actiefCrit += 1;
      markeerActief();
      e.preventDefault();
    }
  });
}

function markeerActief() {
  document.querySelectorAll(".crit-row").forEach((r, i) => {
    r.classList.toggle("actief", i === actiefCrit);
  });
}

// ---------- 9.3 Emotie-chips ----------
function renderEmoties() {
  const box = document.getElementById("emoties");
  if (!box || !CONFIG || !CONFIG.emoties) return;
  box.innerHTML = "";
  CONFIG.emoties.forEach((e) => {
    const chip = document.createElement("div");
    chip.className = "chip emotie" + (e.goed ? " goed" : " let-op") +
      (emoties.has(e.key) ? " on" : "");
    chip.textContent = e.label;
    chip.dataset.key = e.key;
    chip.addEventListener("click", () => {
      if (emoties.has(e.key)) emoties.delete(e.key); else emoties.add(e.key);
      renderEmoties();
    });
    box.appendChild(chip);
  });
}

// ---------- Richting (long/short) ----------
function setupRichting() {
  document.querySelectorAll("#bron button").forEach((b) => {
    b.addEventListener("click", () => { bron = b.dataset.v; paintBron(); });
  });
  paintBron();

  document.querySelectorAll("#richting button").forEach((b) => {
    b.addEventListener("click", () => {
      richting = (richting === b.dataset.v) ? "" : b.dataset.v;  // nogmaals klikken = leeg
      paintRichting();
    });
  });
  paintRichting();
}
function paintBron() {
  document.querySelectorAll("#bron button").forEach((b) => {
    b.classList.toggle("on", bron === b.dataset.v);
  });
  document.body.classList.toggle("is-backtest", bron === "backtest");
}

function paintRichting() {
  document.querySelectorAll("#richting button").forEach((b) => {
    b.classList.toggle("on-" + b.dataset.v, richting === b.dataset.v);
  });
}

// ---------- Zekerheid vooraf ----------
function setupZekerheid() {
  document.querySelectorAll("#zekerheid button").forEach((b) => {
    b.addEventListener("click", () => {
      const v = parseInt(b.dataset.v, 10);
      zekerheid = (zekerheid === v) ? null : v;
      paintZekerheid();
    });
  });
  paintZekerheid();
}
function paintZekerheid() {
  document.querySelectorAll("#zekerheid button").forEach((b) => {
    b.classList.toggle("on", zekerheid === parseInt(b.dataset.v, 10));
  });
}

// ---------- Checklist-slot: eerst beoordelen, dan het resultaat ----------
function updateSlot() {
  const panel = document.getElementById("uitkomstPanel");
  if (!panel) return;                       // bestaat niet in planmodus
  const klaar = beoordeeld.size >= ALL_CRITS.length;
  panel.classList.toggle("op-slot", !klaar);
}

// ---------- Na afloop: lichte MAE/MFE ----------
function setupNaAfloop() {
  Object.keys(naAfloop).forEach((veld) => {
    document.querySelectorAll(`#${veld} button`).forEach((b) => {
      b.addEventListener("click", () => {
        naAfloop[veld] = (naAfloop[veld] === b.dataset.v) ? "" : b.dataset.v;
        paintNaAfloop(veld);
      });
    });
    paintNaAfloop(veld);
  });
}
function paintNaAfloop(veld) {
  document.querySelectorAll(`#${veld} button`).forEach((b) => {
    b.classList.toggle("on", naAfloop[veld] === b.dataset.v);
  });
}

/* =====================================================================
   Ronde 2 -- de sweep meten.
   1 point = 0,10 in prijs. sl_marge = SL-afstand - overshoot.
   Negatief betekent: je stop lag BINNEN de sweep, en werd dus meegenomen
   door precies de beweging waar je setup op gebouwd is.
   ===================================================================== */
function toonSlMarge() {
  const doel = document.getElementById("slMarge");
  if (!doel) return;
  const sl = parseFloat(document.getElementById("sl_afstand_points")?.value);
  const ov = parseFloat(document.getElementById("sweep_overshoot_points")?.value);
  const rij = document.getElementById("slDanTpRij");

  if (isNaN(sl) || isNaN(ov)) {
    doel.className = "sl-marge";
    doel.textContent = "";
    if (rij) rij.style.display = "none";
    return;
  }
  const marge = Math.round((sl - ov) * 100) / 100;
  const binnen = marge < 0;
  doel.className = "sl-marge " + (binnen ? "slecht" : "goed");
  doel.innerHTML = binnen
    ? `<strong>SL-marge ${marge.toFixed(2)} points — je stop lag binnen de sweep.</strong>
       <span>Dit is plaatsingsdata, geen gemiste winst: je stop stond op een niveau
       waar de sweep nog niet klaar was.</span>`
    : `<strong>SL-marge +${marge.toFixed(2)} points — je stop lag buiten de sweep.</strong>
       <span>De sweep kwam ${ov.toFixed(1)} points ver, je stop stond op ${sl.toFixed(1)}.</span>`;
  if (rij) rij.style.display = binnen ? "" : "none";
}

function toonMinutenHint() {
  const el = document.getElementById("minutenHint");
  if (!el) return;
  const m = parseInt(document.getElementById("minuten_in_hourly")?.value, 10);
  if (isNaN(m)) { el.textContent = ""; el.className = "hint"; return; }
  if (m < 20) {
    el.className = "hint waarschuwing";
    el.textContent = "Vóór minuut 20 — je eigen regel zegt: pas na ~20 minuten entries zoeken.";
  } else if (m >= 30 && m <= 45) {
    el.className = "hint goed";
    el.textContent = "Binnen je venster van 30–45 minuten.";
  } else {
    el.className = "hint";
    el.textContent = m < 30 ? "Net voor je venster van 30–45." : "Na minuut 45.";
  }
}

/* =====================================================================
   Venster-bewaking en overtrading-rem (ronde 3, punt 3).

   Je edge zit in één uur. Buiten dat uur traden en na je dagmaximum doortikken
   zijn allebei stille lekken: ze voelen niet als een fout, want er is geen
   moment waarop iemand "nee" zegt. Dit zegt het wel -- zacht, en zonder te
   blokkeren, want jij beslist.
   ===================================================================== */
let VENSTER = { van: "10:00", tot: "11:00" };
let MAX_TRADES_DAG = 3;

function naarMinuten(hhmm) {
  if (!hhmm || !hhmm.includes(":")) return null;
  const [u, m] = hhmm.split(":");
  const n = parseInt(u, 10) * 60 + parseInt(m, 10);
  return isNaN(n) ? null : n;
}
function naarLonden(hhmm) {
  const t = naarMinuten(hhmm);
  if (t === null) return "";
  const l = (t - 60 + 1440) % 1440;
  return `${String(Math.floor(l / 60)).padStart(2, "0")}:${String(l % 60).padStart(2, "0")}`;
}

function toonVensterHint() {
  const el = document.getElementById("vensterHint");
  if (!el) return;
  const t = naarMinuten(val("tijd_entry"));
  if (t === null) { el.textContent = ""; el.className = "hint"; return; }
  const blokken = (VENSTER.blokken && VENSTER.blokken.length ? VENSTER.blokken : [[VENSTER.van, VENSTER.tot]])
    .map((b) => [naarMinuten(b[0]), naarMinuten(b[1])]);
  const binnen = blokken.some((b) => t >= b[0] && t < b[1]);
  const tekst = (VENSTER.blokken && VENSTER.blokken.length ? VENSTER.blokken.map((b) => b[0] + "–" + b[1]).join(" en ")
    : VENSTER.van + "–" + VENSTER.tot);
  el.className = "hint " + (binnen ? "goed" : "waarschuwing");
  el.textContent = binnen
    ? `${naarLonden(val("tijd_entry"))} Londen — binnen je venster (${tekst}).`
    : `${naarLonden(val("tijd_entry"))} Londen — buiten je venster van ${tekst}. Overweeg foutcode E4.`;
}

async function checkDagmaximum() {
  const banner = document.getElementById("dagmaxBanner");
  const datum = val("datum");
  if (!banner || !datum || tradeId) return;          // bij bewerken niet zeuren
  try {
    const dag = await api("/api/day/" + datum);
    const n = (dag.trades || []).filter((t) => t.status === "genomen").length;
    if (MAX_TRADES_DAG && n >= MAX_TRADES_DAG) {
      banner.innerHTML = `<strong>Dit wordt trade ${n + 1} van vandaag.</strong>
        <span>Je eigen dagmaximum staat op ${MAX_TRADES_DAG}. Doortikken na je limiet is
        zelden de trade die je cijfers maakt — maar jij beslist.</span>`;
      banner.classList.add("show");
    } else {
      banner.classList.remove("show");
    }
  } catch (e) { /* een vangrail mag het formulier nooit blokkeren */ }
}

/* Grade-integriteit. Staat een kritisch criterium op ✓ terwijl je er in je
   eigen woorden aan twijfelt? Dan is het feitelijk een ?. Geen blokkade --
   jij beslist -- maar wel een vraag, want de grade hoort uit de checklist te
   volgen en niet uit de uitkomst. */
function twijfelSignaal() {
  const woorden = ["soft", "niet heel duidelijk", "niet echt", "twijfel", "twijfelde",
    "onduidelijk", "niet duidelijk", "vaag", "matig", "zwak", "net aan",
    "niet overtuigend", "niet super"];
  const hooi = [val("notities"), val("les"), val("exit_reden")]
    .map((x) => (x || "").toLowerCase()).join(" ");
  const gevonden = woorden.filter((w) => hooi.includes(w));

  const verdacht = [];
  const KRITISCH = { crit1_conditie: "conditie", crit2_sweep: "sweep", crit3_shift: "shift" };
  if (gevonden.length) {
    Object.keys(KRITISCH).forEach((k) => { if (crits[k] === "yes") verdacht.push(KRITISCH[k]); });
  }
  if ((naAfloop.shift_kwaliteit === "soft" || naAfloop.shift_kwaliteit === "onduidelijk") &&
      crits.crit3_shift === "yes" && !verdacht.includes("shift")) {
    verdacht.push("shift");
  }
  return { woorden: gevonden, criteria: verdacht };
}

function toonTwijfelBanner() {
  let el = document.getElementById("twijfelBanner");
  if (!el) {
    el = document.createElement("div");
    el.id = "twijfelBanner";
    el.className = "twijfel-banner";
    const grade = document.getElementById("gradeLive");
    if (grade && grade.parentNode) grade.parentNode.insertBefore(el, grade.nextSibling);
  }
  const sig = twijfelSignaal();
  if (!sig.criteria.length) { el.classList.remove("show"); el.innerHTML = ""; return sig; }

  const reden = sig.woorden.length
    ? `je schreef &ldquo;${sig.woorden[0]}&rdquo;`
    : "je noemde de shift soft";
  el.innerHTML = `<strong>Weet je zeker dat dit een ✓ is?</strong>
    <span>Bij <em>${sig.criteria.join(" en ")}</em> staat een ✓, maar ${reden}. Twijfel telt als ?.
    Jij beslist — dit blokkeert niets.</span>`;
  el.classList.add("show");
  return sig;
}

// ---------- Screenshots ----------
function setupScreenshots() {
  const dz = document.getElementById("dropzone");
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.multiple = true;
  input.style.display = "none";
  document.body.appendChild(input);
  dz.addEventListener("click", () => input.click());
  input.addEventListener("change", () => { addFiles(input.files); input.value = ""; });
  ["dragenter", "dragover"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => {
    if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files);
  });
}

function addFiles(files) {
  Array.from(files).forEach((f) => {
    if (!f.type.startsWith("image/")) return;
    pendingShots.push({ file: f, url: URL.createObjectURL(f), beschrijving: "", type: "entry" });
  });
  renderShots();
}

function typeSelect(current, onChange) {
  const sel = document.createElement("select");
  sel.className = "typ";
  SHOT_TYPES.forEach((t) => {
    const o = document.createElement("option");
    o.value = t; o.textContent = t; if (t === current) o.selected = true;
    sel.appendChild(o);
  });
  sel.addEventListener("change", () => onChange(sel.value));
  return sel;
}

function renderShots() {
  const grid = document.getElementById("shotGrid");
  grid.innerHTML = "";
  existingShots.forEach((s) => {
    const el = document.createElement("div");
    el.className = "shot";
    el.innerHTML = `<img src="${shotUrl(s.pad)}" alt="" />
      <button class="rm" title="Verwijderen">✕</button>`;
    const cap = document.createElement("input");
    cap.className = "cap"; cap.placeholder = "beschrijving…"; cap.value = s.beschrijving || "";
    cap.addEventListener("change", async () => {
      const fd = new FormData(); fd.append("beschrijving", cap.value); fd.append("type", s.type || "entry");
      try { await fetch("/api/screenshot/" + s.id, { method: "PUT", body: fd }); } catch (e) {}
    });
    const sel = typeSelect(s.type || "entry", async (v) => {
      s.type = v;
      const fd = new FormData(); fd.append("beschrijving", cap.value); fd.append("type", v);
      try { await fetch("/api/screenshot/" + s.id, { method: "PUT", body: fd }); } catch (e) {}
    });
    el.appendChild(cap); el.appendChild(sel);
    el.querySelector(".rm").addEventListener("click", async () => {
      try { await api("/api/screenshot/" + s.id, { method: "DELETE" }); } catch (e) {}
      existingShots = existingShots.filter((x) => x.id !== s.id);
      renderShots();
    });
    grid.appendChild(el);
  });
  pendingShots.forEach((p, idx) => {
    const el = document.createElement("div");
    el.className = "shot pending";
    el.innerHTML = `<img src="${p.url}" alt="" /><button class="rm" title="Verwijderen">✕</button>`;
    const cap = document.createElement("input");
    cap.className = "cap"; cap.placeholder = "beschrijving…"; cap.value = p.beschrijving;
    cap.addEventListener("input", () => { p.beschrijving = cap.value; });
    const sel = typeSelect(p.type, (v) => { p.type = v; });
    el.appendChild(cap); el.appendChild(sel);
    el.querySelector(".rm").addEventListener("click", () => { pendingShots.splice(idx, 1); renderShots(); });
    grid.appendChild(el);
  });
}

async function uploadPending(tid, datum) {
  for (const p of pendingShots) {
    const fd = new FormData();
    fd.append("file", p.file);
    fd.append("datum", datum);
    fd.append("trade_id", tid);
    fd.append("beschrijving", p.beschrijving || "");
    fd.append("type", p.type || "entry");
    try { await fetch("/api/screenshot", { method: "POST", body: fd }); } catch (e) {}
  }
}

function renderChecklist() {
  const box = document.getElementById("checklist");
  box.innerHTML = "";
  CONFIG.criteria.forEach((c) => {
    const row = document.createElement("div");
    row.className = "crit-row" + (c.critical ? " critical" : "");
    row.innerHTML = `
      <div class="crit-num">${c.num}</div>
      <div class="crit-info">
        <div class="crit-title">${c.title}
          ${c.critical ? '<span class="crit-badge-kritisch">kritisch</span>' : ""}</div>
        <div class="crit-help">${c.help}</div>
      </div>
      <div class="seg" data-key="${c.key}">
        <button type="button" data-v="yes">✓</button>
        <button type="button" data-v="maybe">?</button>
        <button type="button" data-v="no">✗</button>
      </div>`;
    box.appendChild(row);
    row.querySelectorAll(".seg button").forEach((btn) => {
      btn.addEventListener("click", () => {
        crits[c.key] = btn.dataset.v;
        beoordeeld.add(c.key);
        paintSeg(c.key);
        updateGrade();
        updateSlot();
      });
    });
    paintSeg(c.key);
  });
}

function paintSeg(key) {
  const seg = document.querySelector(`.seg[data-key="${key}"]`);
  if (!seg) return;   // criterium van een andere fase staat niet op dit formulier
  seg.querySelectorAll("button").forEach((b) => {
    b.className = "";
    if (b.dataset.v === crits[key]) b.classList.add("on-" + crits[key]);
  });
}

function renderFoutcodes() {
  const box = document.getElementById("foutcodes");
  box.innerHTML = "";
  Object.entries(CONFIG.foutcodes).forEach(([groep, data]) => {
    const g = document.createElement("div");
    g.className = "fout-group";
    g.innerHTML = `<div class="grp-label">${groep} — ${data.label}</div>`;
    const chips = document.createElement("div");
    chips.className = "chips";
    Object.entries(data.codes).forEach(([code, desc]) => {
      const chip = document.createElement("div");
      chip.className = "chip";
      chip.textContent = code;
      chip.title = desc;
      chip.dataset.code = code;
      chip.addEventListener("click", () => {
        if (selectedFouten.has(code)) { selectedFouten.delete(code); chip.classList.remove("on"); }
        else { selectedFouten.add(code); chip.classList.add("on"); }
      });
      chips.appendChild(chip);
    });
    g.appendChild(chips);
    box.appendChild(g);
  });
}

function updateGrade() {
  const grade = computeGrade(crits);
  try { toonTwijfelBanner(); } catch (e) { /* banner is nooit blokkerend */ }
  const badge = document.getElementById("gradeBadge");
  badge.textContent = grade;
  badge.className = "grade big grade-" + grade;
  document.getElementById("gradeDesc").textContent = GRADE_DESC[grade];

  const geenTrade = grade === "C";
  const banner = document.getElementById("geenTradeBanner");
  if (banner) banner.classList.toggle("show", geenTrade);
  document.getElementById("gradeLive").classList.toggle("geen-trade", geenTrade);

  if (planMode) {
    const pv = document.getElementById("planVerdict");
    const klaar = beoordeeld.size >= ALL_CRITS.length;
    if (!klaar) {
      pv.className = "plan-verdict show";
      pv.innerHTML = `<div class="pv-kop">Loop je checklist langs</div>
        <div class="pv-sub">Nog ${ALL_CRITS.length - beoordeeld.size} van de ${ALL_CRITS.length} criteria te beoordelen.</div>`;
    } else if (geenTrade) {
      pv.className = "plan-verdict show skip";
      pv.innerHTML = `<div class="pv-kop">✕ Niet nemen</div>
        <div class="pv-sub">Een kritisch criterium is ✗ of ?. Sla 'm over — dat is een discipline-winst,
          geen gemiste kans.</div>`;
    } else {
      pv.className = "plan-verdict show neem";
      pv.innerHTML = `<div class="pv-kop">✓ Deze mag je nemen — grade ${grade}</div>
        <div class="pv-sub">${GRADE_DESC[grade]}</div>`;
    }
  }
}

function val(id) {
  const el = document.getElementById(id);
  return el.value === "" ? null : el.value;
}
function numVal(id) {
  const v = val(id);
  return v === null ? null : parseFloat(v);
}

async function loadTrade(id) {
  const t = await api("/api/trade/" + id);
  document.getElementById("datum").value = t.datum || "";
  document.getElementById("tijd_entry").value = t.tijd_entry || "";
  document.getElementById("instrument").value = t.instrument || "XAUUSD";
  document.getElementById("sessie").value = t.sessie || "";
  ["entry", "sl", "tp", "rr", "risk_eur", "charges", "resultaat_eur"].forEach((k) => {
    if (t[k] !== null && t[k] !== undefined) document.getElementById(k).value = t[k];
  });
  document.getElementById("exit_reden").value = t.exit_reden || "";
  emoties.clear();
  const rest = [];
  (t.mentale_staat || "").split(",").map((x) => x.trim()).filter(Boolean).forEach((x) => {
    if ((CONFIG.emoties || []).some((e) => e.key === x)) emoties.add(x); else rest.push(x);
  });
  renderEmoties();
  document.getElementById("mentale_staat").value = rest.join(", ");
  document.getElementById("les").value = t.les || "";
  document.getElementById("notities").value = t.notities || "";
  document.getElementById("dxy_context").value = t.dxy_context || "";
  document.getElementById("tags").value = t.tags || "";
  verfTagSuggesties();

  ALL_CRITS.forEach((k) => { crits[k] = t[k] || "maybe"; paintSeg(k); beoordeeld.add(k); });
  zekerheid = t.zekerheid || null;
  paintZekerheid();
  status = t.status || "genomen";
  updateSlot();
  richting = t.richting || "";
  paintRichting();
  bron = t.bron || "live";
  paintBron();
  naAfloop.sl_nabijheid = t.sl_nabijheid || "";
  naAfloop.tp_verloop = t.tp_verloop || "";
  ["shift_kwaliteit", "volume_hoog", "overextensie_kwaliteit", "sl_dan_tp", "luck_flag"]
    .forEach((k) => { naAfloop[k] = t[k] || ""; });
  Object.keys(naAfloop).forEach(paintNaAfloop);
  ["sweep_overshoot_points", "sl_afstand_points", "tp_afstand_points", "minuten_in_hourly"]
    .forEach((k) => {
      if (t[k] !== null && t[k] !== undefined) document.getElementById(k).value = t[k];
    });
  toonSlMarge(); toonMinutenHint();
  existingShots = t.screenshots || [];
  renderShots();

  (t.foutcodes || "").split(",").map((s) => s.trim()).filter(Boolean).forEach((code) => {
    selectedFouten.add(code);
    const chip = document.querySelector(`.chip[data-code="${code}"]`);
    if (chip) chip.classList.add("on");
  });
}

function collect() {
  return {
    datum: val("datum"),
    tijd_entry: val("tijd_entry") || "",
    instrument: val("instrument") || "XAUUSD",
    sessie: val("sessie") || "",
    richting: richting,
    crit1_conditie: crits.crit1_conditie,
    crit2_sweep: crits.crit2_sweep,
    crit3_shift: crits.crit3_shift,
    crit4_entry: crits.crit4_entry,
    crit5_tp: crits.crit5_tp,
    rr: numVal("rr"),
    status: status,
    bron: bron,
    zekerheid: zekerheid,
    entry: numVal("entry"),
    sl: numVal("sl"),
    tp: numVal("tp"),
    risk_eur: numVal("risk_eur"),
    resultaat_eur: numVal("resultaat_eur"),
    charges: numVal("charges"),
    exit_reden: val("exit_reden") || "",
    sl_nabijheid: naAfloop.sl_nabijheid,
    tp_verloop: naAfloop.tp_verloop,
    // Ronde 2 -- de sweep meten en de kwaliteit naast de checklist
    sweep_overshoot_points: numVal("sweep_overshoot_points"),
    sl_afstand_points: numVal("sl_afstand_points"),
    tp_afstand_points: numVal("tp_afstand_points"),
    sl_dan_tp: naAfloop.sl_dan_tp,
    luck_flag: naAfloop.luck_flag,
    shift_kwaliteit: naAfloop.shift_kwaliteit,
    volume_hoog: naAfloop.volume_hoog,
    overextensie_kwaliteit: naAfloop.overextensie_kwaliteit,
    minuten_in_hourly: numVal("minuten_in_hourly"),
    foutcodes: Array.from(selectedFouten).join(","),
    mentale_staat: [...emoties, ...(val("mentale_staat") || "")
      .split(",").map((x) => x.trim()).filter(Boolean)].join(", "),
    les: val("les") || "",
    notities: val("notities") || "",
    dxy_context: val("dxy_context") || "",
    tags: val("tags") || "",
  };
}

async function save() {
  const data = collect();
  if (!data.datum) { toast("Datum is verplicht", true); return; }

  // Zachte check, geen slot: de grade moet uit de checklist volgen, niet uit
  // de uitkomst. Anders wordt dezelfde softe shift bij winst een B en bij
  // verlies een C.
  const sig = twijfelSignaal();
  if (sig.criteria.length) {
    const reden = sig.woorden.length ? `je schreef "${sig.woorden[0]}"`
                                     : "je noemde de shift soft";
    const ok = confirm(
      `Weet je zeker dat dit een \u2713 is?\n\n` +
      `Bij ${sig.criteria.join(" en ")} staat een \u2713, maar ${reden}.\n` +
      `Twijfel telt als ?.\n\nOK = toch opslaan zoals het staat.`);
    if (!ok) return;
  }
  try {
    let res, savedId;
    if (tradeId) {
      res = await api("/api/trade/" + tradeId, { method: "PUT", body: JSON.stringify(data) });
      savedId = tradeId;
    } else {
      res = await api("/api/trade", { method: "POST", body: JSON.stringify(data) });
      savedId = res.id;
    }
    if (pendingShots.length) await uploadPending(savedId, data.datum);
    // Punt 9 -- eerst het muntje, dan pas terug naar de dag van deze trade.
    await maybeCelebrate({
      result: data.resultaat_eur,
      grade: (res && res.grade) || computeGrade(crits),
    });
    location.href = "/?datum=" + encodeURIComponent(data.datum);
  } catch (e) {
    toast("Opslaan mislukt: " + e.message, true);
  }
}

async function remove() {
  if (!confirm("Deze trade naar de prullenbak?\n\nHij telt nergens meer mee, maar blijft 30 dagen terug te zetten.")) return;
  const datum = val("datum");
  try {
    await api("/api/trade/" + tradeId, { method: "DELETE" });
    location.href = "/?datum=" + encodeURIComponent(datum || "");
  } catch (e) {
    toast("Verwijderen mislukt: " + e.message, true);
  }
}

boot();
