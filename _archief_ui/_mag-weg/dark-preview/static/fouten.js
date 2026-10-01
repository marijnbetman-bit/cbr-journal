/* Foutenanalyse — automatisch afgeleid uit de trade-feiten. Niets handmatig. */

let fbron = (function () { try { return localStorage.getItem("cbr_bron") || "live"; } catch (e) { return "live"; } })();

function kortD(datum) {
  if (!datum) return "";
  const [j, m, d] = datum.split("-");
  return `${parseInt(d, 10)}/${parseInt(m, 10)}`;
}

async function boot() {
  document.querySelectorAll("#bronTabs button").forEach((b) => {
    b.classList.toggle("on", b.dataset.b === fbron);
    b.addEventListener("click", () => {
      document.querySelectorAll("#bronTabs button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      fbron = b.dataset.b;
      try { localStorage.setItem("cbr_bron", fbron); } catch (e) {}
      load();
    });
  });
  await load();
}

async function load() {
  let d;
  try { d = await api("/api/fouten?bron=" + encodeURIComponent(fbron)); }
  catch (e) { document.getElementById("signalen").innerHTML =
    `<div class="panel"><b>Kon niet laden.</b> ${e.message}</div>`; return; }
  renderKpi(d);
  renderSignalen(d);
}

function renderKpi(d) {
  const cellen = [
    { k: "Trades", v: String(d.n_trades) },
    { k: "Schone trades", v: d.schoon_pct + "%", cls: d.schoon_pct >= 60 ? "pos" : "" },
    { k: "Signalen", v: String(d.n_signalen), cls: d.n_signalen ? "neg" : "pos" },
    { k: "Soorten fout", v: String(d.signalen.length) },
  ];
  document.getElementById("kpi").innerHTML =
    `<div class="mt-bar">${cellen.map((c) => `
      <div class="mt-cell"><div class="k">${c.k}</div>
        <div class="val ${c.cls || ""}">${c.v}</div></div>`).join("")}</div>`;
}

function renderSignalen(d) {
  const box = document.getElementById("signalen");
  if (!d.signalen.length) {
    box.innerHTML = `<div class="empty wachtend"><b>Geen fouten gevonden.</b>
      <span>${d.n_trades ? "Schoon gehandeld — mooi." : "Zodra je trades hebt, kijkt de journal automatisch mee."}</span></div>`;
    return;
  }
  box.innerHTML = d.signalen.map((s) => `
    <div class="panel fout-kaart">
      <div class="fk-kop">
        <div class="fk-titel">${s.label}</div>
        <div class="fk-telling"><b>${s.aantal}×</b> · ${s.pct}% van je trades</div>
      </div>
      <p class="fk-uitleg">${s.uitleg}</p>
      <div class="fk-regel"><span class="fk-regel-lbl">Regel</span> ${s.correctie}</div>
      <div class="mt-table-wrap"><table class="mt">
        <thead><tr><th>Trade</th><th style="text-align:left">Wat er gebeurde</th></tr></thead>
        <tbody>${s.trades.map((t) => `<tr onclick="location.href='/trade?id=${t.id}'" style="cursor:pointer">
          <td><a href="/trade?id=${t.id}">${kortD(t.datum)}${t.tijd ? " " + t.tijd : ""}</a></td>
          <td style="text-align:left">${t.detail}</td></tr>`).join("")}</tbody>
      </table></div>
    </div>`).join("");
}

document.addEventListener("DOMContentLoaded", boot);
