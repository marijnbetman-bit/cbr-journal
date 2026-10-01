// Setup-bibliotheek (fase 13.2) — je eigen goede setups als beeldmateriaal.

let grade = qs("grade") || "A";
let CRITERIA = [];

function boot() {
  document.querySelectorAll("#gradeTabs button").forEach((b) => {
    b.classList.toggle("on", b.dataset.g === grade);
    b.addEventListener("click", () => {
      document.querySelectorAll("#gradeTabs button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      grade = b.dataset.g;
      load();
    });
  });
  document.getElementById("lbSluit").addEventListener("click", sluitBeeld);
  document.getElementById("lightbox").addEventListener("click", (e) => {
    if (e.target.id === "lightbox") sluitBeeld();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") sluitBeeld();
  });
  load();
}

async function load() {
  const d = await api("/api/setups?grade=" + grade);
  CRITERIA = d.criteria || [];
  history.replaceState(null, "", "/setups?grade=" + grade);
  renderKop(d);
  renderLijst(d);
}

function renderKop(d) {
  document.getElementById("bibKop").innerHTML = `
    <div class="mt-bar">
      <div class="mt-cell accent"><div class="k">★ Perfecte setups (A)</div><div class="val">${d.n_a}</div></div>
      <div class="mt-cell"><div class="k">Valide setups (B)</div><div class="val">${d.n_b}</div></div>
      <div class="mt-cell"><div class="k">Met beeld</div><div class="val">${d.n_met_beeld}</div></div>
      <div class="mt-cell"><div class="k">Zonder screenshot</div><div class="val ${d.n_zonder_beeld ? "neg" : ""}">${d.n_zonder_beeld}</div></div>
    </div>`;
}

function critRij(t) {
  return `<div class="bib-crits">${CRITERIA.map((c) => `
    <div class="bc ${t[c.key]}">
      <span class="bc-n">${c.num}</span>
      <span class="bc-v">${SYMBOLS[t[c.key]] || "?"}</span>
      <span class="bc-t">${c.title}</span>
    </div>`).join("")}</div>`;
}

function renderLijst(d) {
  const box = document.getElementById("bibLijst");
  if (!d.setups.length) {
    box.innerHTML = `<div class="empty">
      Nog geen ${grade === "AB" ? "valide" : "perfecte"} setups om terug te kijken.
      Zodra je een trade logt waarbij alle kritische criteria ✓ zijn, verschijnt hij hier —
      met de screenshots die je erbij sleepte.</div>`;
    return;
  }
  box.innerHTML = d.setups.map((t) => {
    const shots = t.screenshots || [];
    const netto = (t.resultaat_eur || 0) + (t.charges || 0);
    return `<div class="bib-setup">
      <div class="bib-kop">
        <span class="grade grade-${t.grade}">${t.grade}</span>
        <div>
          <div class="bib-titel">${t.datum}${t.tijd_entry ? " · " + t.tijd_entry : ""}
            ${t.richting ? `<span class="dir-pill ${t.richting}">${t.richting === "long" ? "▲ long" : "▼ short"}</span>` : ""}</div>
          <div class="bib-sub">${t.rr ? "RR " + Number(t.rr).toFixed(2) + " · " : ""}netto ${fmtEur(netto)}${t.tags ? " · " + t.tags : ""}</div>
        </div>
        <div class="spacer" style="flex:1"></div>
        <a class="btn" href="/trade?id=${t.id}">Openen</a>
      </div>
      ${critRij(t)}
      ${shots.length
        ? `<div class="bib-beelden">${shots.map((sh) => `
            <figure class="bib-beeld" data-pad="${shotUrl(sh.pad)}"
                    data-bij="${(t.datum + " · " + (sh.type || "") + " · " + (sh.beschrijving || "")).replace(/"/g, "&quot;")}">
              <img src="${shotUrl(sh.pad)}" alt="${sh.beschrijving || "chart"}" loading="lazy" />
              <figcaption>${sh.type || "chart"}${sh.beschrijving ? " — " + sh.beschrijving : ""}</figcaption>
            </figure>`).join("")}</div>`
        : `<div class="bib-geen">Geen screenshot bij deze setup — jammer, juist deze wil je terugzien.</div>`}
      ${t.les ? `<div class="bib-les">“${t.les}”</div>` : ""}
    </div>`;
  }).join("");

  box.querySelectorAll(".bib-beeld").forEach((el) => {
    el.addEventListener("click", () => toonBeeld(el.dataset.pad, el.dataset.bij));
  });
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
