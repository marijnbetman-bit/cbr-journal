// Trading log — één map per handelsdag; open een map en je ziet die dag.

let DATA = null;
let open = qs("datum") || "";
let CRITERIA = [];

function boot() {
  document.getElementById("lbSluit").addEventListener("click", sluitBeeld);
  document.getElementById("lightbox").addEventListener("click", (e) => {
    if (e.target.id === "lightbox") sluitBeeld();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") sluitBeeld(); });
  load();
}

async function load() {
  DATA = await api("/api/log");
  CRITERIA = DATA.criteria || [];
  document.getElementById("nieuwKnop").href = "/nieuw" + (open ? "?datum=" + open : "");
  renderBar();
  render();
}

function renderBar() {
  const t = DATA.totaal;
  document.getElementById("logBar").innerHTML = `
    <div class="mt-cell"><div class="k">Handelsdagen</div><div class="val">${t.dagen}</div></div>
    <div class="mt-cell"><div class="k">Trades</div><div class="val">${t.trades}</div></div>
    <div class="mt-cell"><div class="k">Netto</div><div class="val ${eurClass(t.netto_eur)}">${fmtEur(t.netto_eur)}</div></div>
    <div class="mt-cell"><div class="k">Netto R</div><div class="val ${eurClass(t.netto_r)}">${(t.netto_r >= 0 ? "+" : "") + t.netto_r.toFixed(2)}R</div></div>
    <div class="mt-cell accent"><div class="k">★ Perfecte trades</div><div class="val">${t.perfect}</div></div>`;
}

function render() {
  const box = document.getElementById("logInhoud");
  if (!DATA.dagen.length) {
    box.innerHTML = `<div class="empty wachtend">
      <b>Nog niets gelogd.</b>
      <span>Zodra je je eerste trade toevoegt, verschijnt hier een map voor die dag.</span>
      <span><a href="/nieuw">+ Trade toevoegen</a></span></div>`;
    return;
  }
  const dag = open ? DATA.dagen.find((d) => d.datum === open) : null;
  if (dag) renderDag(box, dag); else renderMappen(box);
}

// ---------- mappen ----------
function renderMappen(box) {
  box.innerHTML = `<div class="section-title">Alle handelsdagen (${DATA.dagen.length})</div>
    <div class="mappen">${DATA.dagen.map((d) => {
      const badges = ["A", "B", "C"].filter((g) => d.grades[g])
        .map((g) => `<span class="grade grade-${g} mini">${g}</span><i>${d.grades[g]}</i>`).join("");
      const shot = d.trades.find((t) => t.screenshots.length);
      return `<div class="map" data-datum="${d.datum}">
        <div class="map-tab ${d.netto_eur > 0 ? "op" : d.netto_eur < 0 ? "neer" : ""}"></div>
        <div class="map-kop">
          <div class="map-datum">${dagNaam(d.datum)}</div>
        </div>
        ${shot ? `<div class="map-beeld" style="background-image:url('${shotUrl(shot.screenshots[0].pad)}')"></div>`
               : `<div class="map-beeld leeg">geen screenshot</div>`}
        <div class="map-voet">
          <span class="map-netto ${eurClass(d.netto_eur)}">${d.n ? fmtEur(d.netto_eur) : "–"}</span>
          <span class="map-n">${d.n} trade${d.n === 1 ? "" : "s"}</span>
          <div class="map-badges">${badges}</div>
        </div>
        <div class="map-extra">
          ${d.n_no_trades ? `<span>${d.n_no_trades} no-trade</span>` : ""}
          ${d.n_overgeslagen ? `<span>🛡 ${d.n_overgeslagen}</span>` : ""}
          ${d.n_shots ? `<span>📷 ${d.n_shots}</span>` : ""}
          ${d.review ? `<span>✎ afgesloten</span>` : ""}
        </div>
      </div>`;
    }).join("")}</div>`;

  box.querySelectorAll(".map").forEach((el) => {
    el.addEventListener("click", () => {
      open = el.dataset.datum;
      history.replaceState(null, "", "/log?datum=" + open);
      document.getElementById("nieuwKnop").href = "/nieuw?datum=" + open;
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

function dagNaam(iso) {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("nl-NL", { weekday: "long", day: "numeric", month: "long" });
}

// ---------- één dag open ----------
function renderDag(box, d) {
  box.innerHTML = `
    <div class="dag-kop">
      <button class="btn" id="terug">← Alle dagen</button>
      <h2>${dagNaam(d.datum)}</h2>
      <span class="dag-som ${eurClass(d.netto_eur)}">${fmtEur(d.netto_eur)}
        <i>${(d.netto_r >= 0 ? "+" : "") + d.netto_r.toFixed(2)}R</i></span>
      <div class="spacer" style="flex:1"></div>
      <a class="btn" href="/nieuw?datum=${d.datum}">+ Trade op deze dag</a>
      <a class="btn btn-ghost" href="/?datum=${d.datum}">Dagoverzicht</a>
    </div>

    ${d.review ? `<div class="dag-review-kaart">
      ${d.review.goed ? `<div><span class="drl">goed</span>${d.review.goed}</div>` : ""}
      ${d.review.beter ? `<div><span class="drl">beter</span>${d.review.beter}</div>` : ""}
      ${d.review.focus ? `<div><span class="drl">focus</span>${d.review.focus}</div>` : ""}
    </div>` : ""}

    ${d.trades.length ? d.trades.map((t, i) => logTrade(t, i + 1)).join("")
      : `<div class="empty">Geen trades genomen op deze dag.
          ${d.n_no_trades ? d.n_no_trades + " no-trade(s) genoteerd." : ""}</div>`}`;

  document.getElementById("terug").addEventListener("click", () => {
    open = "";
    history.replaceState(null, "", "/log");
    document.getElementById("nieuwKnop").href = "/nieuw";
    render();
  });
  box.querySelectorAll(".lt-beeld").forEach((el) => {
    el.addEventListener("click", () => toonBeeld(el.dataset.pad, el.dataset.bij));
  });
}

function logTrade(t, nr) {
  const netto = (t.resultaat_eur || 0) + (t.charges || 0);
  const fouten = (t.foutcodes || "").split(",").map((s) => s.trim()).filter(Boolean);
  const crits = CRITERIA.map((c) => `
    <span class="lt-crit ${t[c.key]}" title="${c.title}">
      <i>${c.num}</i>${SYMBOLS[t[c.key]] || "?"}</span>`).join("");
  return `<div class="log-trade">
    <div class="lt-kop">
      <span class="lt-nr">#${nr}</span>
      <span class="grade grade-${t.grade}">${t.grade}</span>
      <span class="lt-tijd">${t.tijd_entry || "–"}</span>
      <span class="lt-inst">${t.instrument}</span>
      ${t.richting ? `<span class="dir-pill ${t.richting}">${t.richting === "long" ? "▲ long" : "▼ short"}</span>` : ""}
      ${t.rr ? `<span class="lt-rr">RR ${Number(t.rr).toFixed(2)}</span>` : ""}
      <div class="spacer" style="flex:1"></div>
      <span class="lt-bedrag ${eurClass(netto)}">${fmtEur(netto)}</span>
      <a class="btn" href="/trade?id=${t.id}">Bewerken</a>
    </div>
    <div class="lt-crits">${crits}</div>
    ${t.les ? `<div class="lt-tekst">${esc(t.les)}</div>`
            : `<div class="lt-tekst leeg">Geen omschrijving — open de trade en schrijf er één zin bij.</div>`}
    ${t.screenshots.length ? `<div class="lt-beelden">${t.screenshots.map((sh) => `
      <figure class="lt-beeld" data-pad="${shotUrl(sh.pad)}"
              data-bij="${esc(t.datum + " · " + (sh.beschrijving || sh.type || ""))}">
        <img src="${shotUrl(sh.pad)}" alt="" loading="lazy" />
        <figcaption>${esc(sh.type || "chart")}${sh.beschrijving ? " — " + esc(sh.beschrijving) : ""}</figcaption>
      </figure>`).join("")}</div>` : ""}
    ${(fouten.length || t.tags) ? `<div class="lt-voet">
      ${fouten.map((c) => `<span class="tag fout">${c}</span>`).join("")}
      ${t.tags ? t.tags.split(",").map((x) => `<span class="tag">${esc(x.trim())}</span>`).join("") : ""}
    </div>` : ""}
  </div>`;
}

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function toonBeeld(pad, bij) {
  document.getElementById("lbImg").src = pad;
  document.getElementById("lbBij").textContent = bij || "";
  document.getElementById("lightbox").hidden = false;
}
function sluitBeeld() {
  document.getElementById("lightbox").hidden = true;
  document.getElementById("lbImg").src = "";
}

boot();
