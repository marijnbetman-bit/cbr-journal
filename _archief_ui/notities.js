// Notitieboek (fase 12.3) — losse notities die niet aan één trade hangen.

let bewerktId = null;
let zoekterm = "";

function boot() {
  document.getElementById("nDatum").value = todayISO();
  document.getElementById("nSave").addEventListener("click", opslaan);
  document.getElementById("nNieuw").addEventListener("click", leegmaken);

  let timer;
  document.getElementById("zoek").addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => { zoekterm = e.target.value.trim(); laden(); }, 220);
  });

  laden();
  laadTags();
}

async function laadTags() {
  try {
    const d = await api("/api/tags");
    const box = document.getElementById("tagSuggesties");
    if (!d.lijst.length) { box.innerHTML = ""; return; }
    box.innerHTML = `<span class="tag-hint">eerder gebruikt:</span>` +
      d.lijst.slice(0, 14).map((t) =>
        `<span class="chip tag-sug" data-t="${t.tag}">${t.tag} <i>${t.aantal}</i></span>`).join("");
    box.querySelectorAll(".tag-sug").forEach((el) => {
      el.addEventListener("click", () => {
        const veld = document.getElementById("nTags");
        const huidig = veld.value.split(",").map((x) => x.trim()).filter(Boolean);
        if (!huidig.includes(el.dataset.t)) huidig.push(el.dataset.t);
        veld.value = huidig.join(", ");
      });
    });
  } catch (e) { /* suggesties zijn bijzaak */ }
}

async function laden() {
  const d = await api("/api/notities?zoek=" + encodeURIComponent(zoekterm));
  const box = document.getElementById("notitieLijst");
  document.getElementById("notitiesTitel").textContent =
    zoekterm ? `Notities met "${zoekterm}" (${d.lijst.length})` : `Notities (${d.lijst.length})`;
  if (!d.lijst.length) {
    box.innerHTML = `<div class="empty">${zoekterm
      ? "Niets gevonden."
      : "Nog niets genoteerd. Alles wat je nu in je hoofd bewaart, kan hier staan."}</div>`;
    return;
  }
  box.innerHTML = `<div class="notitie-lijst">${d.lijst.map((n) => `
    <div class="notitie" data-id="${n.id}">
      <div class="not-kop">
        <div class="not-datum">${n.datum}</div>
        <div class="not-titel">${esc(n.titel)}</div>
        <div class="spacer" style="flex:1"></div>
        <button class="btn not-edit">Bewerken</button>
        <button class="btn btn-danger not-del">✕</button>
      </div>
      ${n.tekst ? `<div class="not-tekst">${esc(n.tekst).replace(/\n/g, "<br>")}</div>` : ""}
      ${n.tags ? `<div class="chips">${n.tags.split(",").map((t) =>
        `<span class="chip">${esc(t.trim())}</span>`).join("")}</div>` : ""}
    </div>`).join("")}</div>`;

  box.querySelectorAll(".not-edit").forEach((b) => {
    b.addEventListener("click", () => {
      const n = d.lijst.find((x) => x.id === parseInt(b.closest(".notitie").dataset.id, 10));
      bewerktId = n.id;
      document.getElementById("nDatum").value = n.datum;
      document.getElementById("nTitel").value = n.titel;
      document.getElementById("nTekst").value = n.tekst || "";
      document.getElementById("nTags").value = n.tags || "";
      document.getElementById("nSave").textContent = "Bijwerken";
      document.getElementById("nNieuw").style.display = "";
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
  box.querySelectorAll(".not-del").forEach((b) => {
    b.addEventListener("click", async () => {
      if (!confirm("Deze notitie verwijderen?")) return;
      await api("/api/notitie/" + b.closest(".notitie").dataset.id, { method: "DELETE" });
      if (bewerktId === parseInt(b.closest(".notitie").dataset.id, 10)) leegmaken();
      laden();
    });
  });
}

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function leegmaken() {
  bewerktId = null;
  document.getElementById("nTitel").value = "";
  document.getElementById("nTekst").value = "";
  document.getElementById("nTags").value = "";
  document.getElementById("nDatum").value = todayISO();
  document.getElementById("nSave").textContent = "Opslaan";
  document.getElementById("nNieuw").style.display = "none";
}

async function opslaan() {
  const titel = document.getElementById("nTitel").value.trim();
  if (!titel) { toast("Geef je notitie een titel", true); return; }
  try {
    await api("/api/notitie", { method: "POST", body: JSON.stringify({
      id: bewerktId,
      datum: document.getElementById("nDatum").value || todayISO(),
      titel,
      tekst: document.getElementById("nTekst").value,
      tags: document.getElementById("nTags").value,
    }) });
    toast(bewerktId ? "Bijgewerkt" : "Opgeslagen");
    leegmaken();
    laden();
    laadTags();
  } catch (e) { toast("Opslaan mislukt: " + e.message, true); }
}

boot();
