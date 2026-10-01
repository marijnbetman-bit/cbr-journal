// Regel-changelog (fase 11.4) — markeer wanneer je je eigen regels wijzigt.

async function boot() {
  document.getElementById("rwDatum").value = todayISO();
  document.getElementById("rwSave").addEventListener("click", opslaan);
  await laden();
}

async function laden() {
  const d = await api("/api/regelwijzigingen");
  const box = document.getElementById("rwLijst");
  if (!d.lijst.length) {
    box.innerHTML = `<div class="empty">Nog geen regelwijzigingen vastgelegd.
      Zolang je model hetzelfde blijft, hoeft dat ook niet.</div>`;
    return;
  }
  box.innerHTML = `<div class="rw-lijst">${d.lijst.map((r, i) => `
    <div class="rw-item${i === 0 ? " nieuwste" : ""}">
      <div class="rw-datum">${r.datum}${i === 0 ? ' <span class="rw-tag">geldt nu</span>' : ""}</div>
      <div class="rw-body">
        <div class="rw-titel">${r.titel}</div>
        ${r.toelichting ? `<div class="rw-toe">${r.toelichting}</div>` : ""}
      </div>
      <button class="btn btn-danger rw-del" data-id="${r.id}" title="Verwijderen">✕</button>
    </div>`).join("")}</div>`;
  box.querySelectorAll(".rw-del").forEach((b) => {
    b.addEventListener("click", async () => {
      if (!confirm("Deze regelwijziging verwijderen?")) return;
      await api("/api/regelwijziging/" + b.dataset.id, { method: "DELETE" });
      laden();
    });
  });
}

async function opslaan() {
  const titel = document.getElementById("rwTitel").value.trim();
  if (!titel) { toast("Geef je regelwijziging een titel", true); return; }
  try {
    await api("/api/regelwijziging", { method: "POST", body: JSON.stringify({
      datum: document.getElementById("rwDatum").value || todayISO(),
      titel,
      toelichting: document.getElementById("rwToelichting").value.trim(),
    }) });
    document.getElementById("rwTitel").value = "";
    document.getElementById("rwToelichting").value = "";
    toast("Vastgelegd");
    laden();
  } catch (e) { toast("Opslaan mislukt: " + e.message, true); }
}

boot();
