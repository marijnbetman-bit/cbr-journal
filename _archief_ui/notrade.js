// No-trade toevoegen / bewerken (met screenshots).

let noTradeId = qs("id");
let existingShots = [];
let pendingShots = [];
const SHOT_TYPES = ["pre-entry", "entry", "post-exit"];

async function boot() {
  if (noTradeId) {
    document.getElementById("formTitle").textContent = "No-trade bewerken";
    document.getElementById("deleteBtn").style.display = "inline-flex";
    const nt = await api("/api/no_trade/" + noTradeId);
    document.getElementById("datum").value = nt.datum || "";
    document.getElementById("tijd").value = nt.tijd || "";
    document.getElementById("reden").value = nt.reden || "";
    document.getElementById("wat_zag_ik").value = nt.wat_zag_ik || "";
    existingShots = nt.screenshots || [];
  } else {
    document.getElementById("datum").value = qs("datum") || todayISO();
  }
  setupScreenshots();
  renderShots();
  document.getElementById("saveBtn").addEventListener("click", save);
  document.getElementById("deleteBtn").addEventListener("click", remove);
}

function v(id) { const el = document.getElementById(id); return el.value; }

// ---- screenshots ----
function setupScreenshots() {
  const dz = document.getElementById("dropzone");
  const input = document.createElement("input");
  input.type = "file"; input.accept = "image/*"; input.multiple = true; input.style.display = "none";
  document.body.appendChild(input);
  dz.addEventListener("click", () => input.click());
  input.addEventListener("change", () => { addFiles(input.files); input.value = ""; });
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => { if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files); });
}

function addFiles(files) {
  Array.from(files).forEach((f) => {
    if (!f.type.startsWith("image/")) return;
    pendingShots.push({ file: f, url: URL.createObjectURL(f), beschrijving: "" });
  });
  renderShots();
}

function renderShots() {
  const grid = document.getElementById("shotGrid");
  grid.innerHTML = "";
  existingShots.forEach((s) => {
    const el = document.createElement("div");
    el.className = "shot";
    el.innerHTML = `<img src="${shotUrl(s.pad)}" alt="" /><button class="rm">✕</button>`;
    const cap = document.createElement("input");
    cap.className = "cap"; cap.placeholder = "beschrijving…"; cap.value = s.beschrijving || "";
    cap.addEventListener("change", async () => {
      const fd = new FormData(); fd.append("beschrijving", cap.value); fd.append("type", s.type || "entry");
      try { await fetch("/api/screenshot/" + s.id, { method: "PUT", body: fd }); } catch (e) {}
    });
    el.appendChild(cap);
    el.querySelector(".rm").addEventListener("click", async () => {
      try { await api("/api/screenshot/" + s.id, { method: "DELETE" }); } catch (e) {}
      existingShots = existingShots.filter((x) => x.id !== s.id); renderShots();
    });
    grid.appendChild(el);
  });
  pendingShots.forEach((p, idx) => {
    const el = document.createElement("div");
    el.className = "shot pending";
    el.innerHTML = `<img src="${p.url}" alt="" /><button class="rm">✕</button>`;
    const cap = document.createElement("input");
    cap.className = "cap"; cap.placeholder = "beschrijving…"; cap.value = p.beschrijving;
    cap.addEventListener("input", () => { p.beschrijving = cap.value; });
    el.appendChild(cap);
    el.querySelector(".rm").addEventListener("click", () => { pendingShots.splice(idx, 1); renderShots(); });
    grid.appendChild(el);
  });
}

async function uploadPending(ntid, datum) {
  for (const p of pendingShots) {
    const fd = new FormData();
    fd.append("file", p.file); fd.append("datum", datum);
    fd.append("no_trade_id", ntid); fd.append("beschrijving", p.beschrijving || "");
    fd.append("type", "entry");
    try { await fetch("/api/screenshot", { method: "POST", body: fd }); } catch (e) {}
  }
}

async function save() {
  const data = { datum: v("datum"), tijd: v("tijd"), reden: v("reden"), wat_zag_ik: v("wat_zag_ik") };
  if (!data.datum) { toast("Datum is verplicht", true); return; }
  try {
    let savedId;
    if (noTradeId) { await api("/api/no_trade/" + noTradeId, { method: "PUT", body: JSON.stringify(data) }); savedId = noTradeId; }
    else { const res = await api("/api/no_trade", { method: "POST", body: JSON.stringify(data) }); savedId = res.id; }
    if (pendingShots.length) await uploadPending(savedId, data.datum);
    location.href = "/?datum=" + encodeURIComponent(data.datum);
  } catch (e) { toast("Opslaan mislukt: " + e.message, true); }
}

async function remove() {
  if (!confirm("Deze no-trade verwijderen?")) return;
  const datum = v("datum");
  try {
    await api("/api/no_trade/" + noTradeId, { method: "DELETE" });
    location.href = "/?datum=" + encodeURIComponent(datum || "");
  } catch (e) { toast("Verwijderen mislukt: " + e.message, true); }
}

boot();
