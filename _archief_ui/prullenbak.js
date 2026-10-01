// Prullenbak (fase 16.1) — verwijderen mag, maar niet onherstelbaar.

function boot() {
  document.getElementById("leegKnop").addEventListener("click", async () => {
    if (!confirm("Alles in de prullenbak definitief verwijderen? Dit kan niet terug.")) return;
    await api("/api/prullenbak", { method: "DELETE" });
    toast("Prullenbak geleegd");
    laden();
  });
  laden();
}

async function laden() {
  const d = await api("/api/prullenbak");
  document.getElementById("dagenTekst").textContent = d.dagen;
  const box = document.getElementById("pbLijst");
  const items = [
    ...d.trades.map((t) => ({ ...t, soort: "trade" })),
    ...d.no_trades.map((t) => ({ ...t, soort: "no_trade" })),
  ].sort((a, b) => (b.verwijderd_op || "").localeCompare(a.verwijderd_op || ""));

  if (!items.length) {
    box.innerHTML = `<div class="empty">De prullenbak is leeg. Dat is precies zoals het hoort.</div>`;
    return;
  }
  box.innerHTML = `<div class="pb-lijst">${items.map((t) => `
    <div class="pb-rij" data-soort="${t.soort}" data-id="${t.id}">
      <span class="pb-soort">${t.soort === "trade" ? "trade" : "no-trade"}</span>
      ${t.grade ? `<span class="grade grade-${t.grade} mini">${t.grade}</span>` : ""}
      <div class="pb-tekst">
        <b>${t.datum}${t.tijd_entry || t.tijd ? " · " + (t.tijd_entry || t.tijd) : ""}</b>
        <span>${t.soort === "trade"
          ? (t.les || t.notities || t.instrument || "")
          : (t.reden || t.wat_zag_ik || "")}</span>
      </div>
      <span class="pb-datum">verwijderd ${(t.verwijderd_op || "").slice(0, 16).replace("T", " ")}</span>
      <button class="btn pb-herstel">Terugzetten</button>
      <button class="btn btn-danger pb-weg" title="Definitief verwijderen">✕</button>
    </div>`).join("")}</div>`;

  box.querySelectorAll(".pb-herstel").forEach((b) => {
    b.addEventListener("click", async () => {
      const r = b.closest(".pb-rij");
      await api(`/api/prullenbak/herstel/${r.dataset.soort}/${r.dataset.id}`, { method: "POST" });
      toast("Teruggezet");
      laden();
    });
  });
  box.querySelectorAll(".pb-weg").forEach((b) => {
    b.addEventListener("click", async () => {
      const r = b.closest(".pb-rij");
      if (!confirm("Definitief verwijderen? Dit kan niet terug.")) return;
      await api(`/api/prullenbak/${r.dataset.soort}/${r.dataset.id}`, { method: "DELETE" });
      laden();
    });
  });
}

boot();
