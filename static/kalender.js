// Kalender-heatmap (fase 10.1) — het scherm dat je 's ochtends opent.

let jaar, maand;
let bron = localStorage_get("cbr_bron") || "live";

function localStorage_get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function localStorage_set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

function boot() {
  const nu = new Date();
  jaar = parseInt(qs("jaar") || nu.getFullYear(), 10);
  maand = parseInt(qs("maand") || (nu.getMonth() + 1), 10);

  document.getElementById("prevMaand").addEventListener("click", () => stap(-1));
  document.getElementById("nextMaand").addEventListener("click", () => stap(1));
  document.getElementById("naarVandaag").addEventListener("click", () => {
    const d = new Date();
    jaar = d.getFullYear(); maand = d.getMonth() + 1; load();
  });

  document.querySelectorAll("#bronTabs button").forEach((b) => {
    b.classList.toggle("on", b.dataset.b === bron);
    b.addEventListener("click", () => {
      bron = b.dataset.b;
      localStorage_set("cbr_bron", bron);
      document.querySelectorAll("#bronTabs button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      load();
    });
  });

  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    if (e.key === "ArrowLeft") stap(-1);
    if (e.key === "ArrowRight") stap(1);
  });

  load();
}

function stap(n) {
  maand += n;
  if (maand < 1) { maand = 12; jaar -= 1; }
  if (maand > 12) { maand = 1; jaar += 1; }
  load();
}

async function load() {
  const d = await api(`/api/kalender?jaar=${jaar}&maand=${maand}&bron=${encodeURIComponent(bron)}`);
  history.replaceState(null, "", `/kalender?jaar=${jaar}&maand=${maand}`);
  document.getElementById("maandTitel").textContent =
    d.maandnaam.charAt(0).toUpperCase() + d.maandnaam.slice(1) + " " + d.jaar;
  renderBar(d.totaal, d);
  renderDagnamen(d.dagnamen);
  renderGrid(d);
  renderJaar(d.jaarstrook);
}

function renderBar(t, d) {
  const box = document.getElementById("maandBar");
  box.innerHTML = `
    <div class="mt-cell"><div class="k">Handelsdagen</div><div class="val">${t.handelsdagen}</div></div>
    <div class="mt-cell"><div class="k">Trades</div><div class="val">${t.trades}</div></div>
    <div class="mt-cell"><div class="k">Netto</div><div class="val ${eurClass(t.netto_eur)}">${fmtEur(t.netto_eur)}</div></div>
    <div class="mt-cell"><div class="k">Netto R</div><div class="val ${eurClass(t.netto_r)}">${(t.netto_r >= 0 ? "+" : "") + t.netto_r.toFixed(2)}R</div></div>
    <div class="mt-cell"><div class="k">Groen / rood</div><div class="val"><span class="pos">${t.groene_dagen}</span> / <span class="neg">${t.rode_dagen}</span></div></div>
    <div class="mt-cell"><div class="k">★ Perfect · 🛡 Overgeslagen</div><div class="val">${t.perfecte} <span style="color:var(--muted)">·</span> ${t.overgeslagen}</div></div>`;
}

function renderDagnamen(namen) {
  document.getElementById("dagNamen").innerHTML =
    namen.map((n) => `<div class="kal-dn">${n}</div>`).join("");
}

// Kleurintensiteit naar verhouding van de grootste dag van de maand.
function tint(r, schaal) {
  if (!r) return "";
  const f = Math.min(1, Math.abs(r) / (schaal || 1));
  const stap = f > 0.72 ? 3 : f > 0.38 ? 2 : 1;
  return (r > 0 ? "w" : "l") + stap;
}

function renderGrid(d) {
  const grid = document.getElementById("kalGrid");
  const vandaag = todayISO();
  grid.innerHTML = "";
  d.weken.forEach((week) => {
    week.forEach((cel) => {
      const el = document.createElement("div");
      const data = cel.data;
      const klas = ["kal-dag"];
      if (cel.buiten) klas.push("buiten");
      if (cel.weekend) klas.push("weekend");
      if (cel.datum === vandaag) klas.push("vandaag");
      if (data && data.n) klas.push(tint(data.netto_r, d.schaal_r));
      else if (data) klas.push("alleen-skip");
      else klas.push("leeg");
      el.className = klas.join(" ");

      let merk = "";
      if (data && data.n_a) merk += `<span class="merk ster" title="${data.n_a}× perfecte setup">★</span>`;
      if (data && data.n_overgeslagen) merk += `<span class="merk schild" title="${data.n_overgeslagen}× bewust overgeslagen">🛡</span>`;
      if (data && data.n_no_trades && !data.n) merk += `<span class="merk nt" title="no-trade genoteerd">·</span>`;

      const r = data && data.n
        ? `<div class="kal-r">${(data.netto_r >= 0 ? "+" : "") + data.netto_r.toFixed(2)}R</div>
           <div class="kal-eur">${fmtEur(data.netto_eur)}</div>
           <div class="kal-n">${data.n} trade${data.n === 1 ? "" : "s"}${data.n_c ? ` · ${data.n_c}× C` : ""}</div>`
        : "";

      el.innerHTML = `<div class="kal-d">${cel.dag}</div>${merk}${r}`;
      if (data || !cel.buiten) {
        el.addEventListener("click", () => { location.href = "/?datum=" + cel.datum; });
        el.classList.add("klikbaar");
      }
      grid.appendChild(el);
    });
  });
}

function renderJaar(js) {
  const box = document.getElementById("jaarstrook");
  const schaal = js.schaal_r || 1;
  box.innerHTML = js.maanden.map((m) => {
    const h = Math.round(Math.min(1, Math.abs(m.netto_r) / schaal) * 46) + (m.n ? 4 : 0);
    const kant = m.netto_r >= 0 ? "op" : "neer";
    return `<div class="jm ${m.maand === maand ? "actief" : ""}" data-m="${m.maand}">
      <div class="jm-vak">
        <div class="jm-balk ${kant}" style="height:${h}px"></div>
      </div>
      <div class="jm-r ${eurClass(m.netto_r)}">${m.n ? (m.netto_r >= 0 ? "+" : "") + m.netto_r.toFixed(1) + "R" : "–"}</div>
      <div class="jm-naam">${m.naam}</div>
      <div class="jm-n">${m.n ? m.n + "×" : ""}</div>
    </div>`;
  }).join("");
  box.querySelectorAll(".jm").forEach((el) => {
    el.addEventListener("click", () => { maand = parseInt(el.dataset.m, 10); load(); });
  });
}

boot();
