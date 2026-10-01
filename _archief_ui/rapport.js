// Rapportkaart per maand en jaar (fase 12.2) — één pagina, twee minuten lezen.

let soort = qs("soort") || "maand";
let sleutel = qs("sleutel") || "";
let VALUTA = "€";

function nuMaand() { return todayISO().slice(0, 7); }
function nuJaar() { return todayISO().slice(0, 4); }

function boot() {
  if (!sleutel) sleutel = soort === "jaar" ? nuJaar() : nuMaand();
  document.getElementById("maandKies").value = soort === "maand" ? sleutel : nuMaand();
  document.getElementById("jaarKies").value = soort === "jaar" ? sleutel : nuJaar();
  toonKiezers();

  document.querySelectorAll("#soortTabs button").forEach((b) => {
    b.classList.toggle("on", b.dataset.s === soort);
    b.addEventListener("click", () => {
      document.querySelectorAll("#soortTabs button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      soort = b.dataset.s;
      sleutel = soort === "jaar" ? document.getElementById("jaarKies").value || nuJaar()
                                 : document.getElementById("maandKies").value || nuMaand();
      toonKiezers();
      load();
    });
  });
  document.getElementById("maandKies").addEventListener("change", (e) => {
    sleutel = e.target.value; load();
  });
  document.getElementById("jaarKies").addEventListener("change", (e) => {
    sleutel = e.target.value; load();
  });
  document.getElementById("printKnop").addEventListener("click", () => window.print());
  load();
}

function toonKiezers() {
  document.getElementById("maandKies").style.display = soort === "maand" ? "" : "none";
  document.getElementById("jaarKies").style.display = soort === "jaar" ? "" : "none";
}

function eur(n) {
  if (n === null || n === undefined) return "–";
  return VALUTA + " " + (n >= 0 ? "+" : "") + Number(n).toFixed(2).replace(".", ",");
}
const rr = (x) => (x >= 0 ? "+" : "") + Number(x).toFixed(2) + "R";

async function load() {
  const d = await api(`/api/rapport?soort=${soort}&sleutel=${encodeURIComponent(sleutel)}`);
  VALUTA = d.valuta || "€";
  history.replaceState(null, "", `/rapport?soort=${soort}&sleutel=${encodeURIComponent(sleutel)}`);
  render(d);
}

function render(d) {
  const k = d.kop;
  const box = document.getElementById("rapport");

  if (!k.n_trades) {
    box.innerHTML = `<div class="rap-kop"><h2>Rapportkaart ${d.titel}</h2></div>
      <div class="empty">Geen trades in deze periode.</div>`;
    return;
  }

  const tile = (label, waarde, klas, sub) => `
    <div class="rap-tile">
      <div class="rt-val ${klas || ""}">${waarde}</div>
      <div class="rt-lbl">${label}</div>
      ${sub ? `<div class="rt-sub">${sub}</div>` : ""}
    </div>`;

  const tradeRegel = (t, wat) => t ? `
    <div class="rap-trade">
      <span class="grade grade-${t.grade} mini">${t.grade}</span>
      <div>
        <div><b>${wat}</b> — ${t.datum}${t.richting ? " · " + t.richting : ""}${t.rr ? " · RR " + Number(t.rr).toFixed(2) : ""}</div>
        ${t.les ? `<div class="rap-les">“${t.les}”</div>` : ""}
      </div>
      <span class="rap-bedrag ${t.netto_eur >= 0 ? "pos" : "neg"}">${eur(t.netto_eur)}</span>
    </div>` : "";

  box.innerHTML = `
    <div class="rap-kop">
      <div>
        <div class="rap-eyebrow">Rapportkaart · ${d.soort}</div>
        <h2>${d.titel}</h2>
        <div class="rap-periode">${d.van} t/m ${d.tot}</div>
      </div>
      <div class="rap-netto ${k.netto_eur >= 0 ? "pos" : "neg"}">${eur(k.netto_eur)}</div>
    </div>

    <div class="rap-tiles">
      ${tile("Trades", k.n_trades, "", `${k.handelsdagen} handelsdag(en)`)}
      ${tile("Winrate", k.winrate + "%", "")}
      ${tile("Valide setups", k.valide_pct + "%", "", "grade A of B")}
      ${tile("★ Perfect", k.n_perfect, "", "alle vijf criteria")}
      ${tile("Expectancy", rr(k.expectancy_r), k.expectancy_r >= 0 ? "pos" : "neg", "per trade")}
      ${tile("Netto R", rr(k.netto_r), k.netto_r >= 0 ? "pos" : "neg")}
      ${tile("Profit factor", k.profit_factor === null ? "–" : Number(k.profit_factor).toFixed(2), "")}
      ${tile("Regel-adherentie", k.adherentie + "%",
             k.adherentie >= 85 ? "pos" : k.adherentie >= 60 ? "amber" : "neg", k.adherentie_band)}
      ${tile("Discipline", k.discipline + "/100",
             k.discipline >= 80 ? "pos" : k.discipline >= 60 ? "amber" : "neg")}
      ${tile("Weggebleven", k.n_overgeslagen + k.n_no_trades, "",
             `${k.n_overgeslagen} skip · ${k.n_no_trades} no-trade`)}
    </div>

    ${k.n_trades && !d.genoeg ? `<p class="rap-caveat">Deze periode telt ${k.n_trades} trade(s).
      Onder de twintig zijn winrate, expectancy en profit factor ruis — lees ze als een logboek,
      niet als een meting. Regel-adherentie en discipline zeggen nú al iets.</p>` : ""}

    <div class="rap-sectie">
      <h3>Beste en slechtste</h3>
      ${tradeRegel(d.beste, "Beste trade")}
      ${tradeRegel(d.slechtste, "Slechtste trade")}
    </div>

    ${d.top_fout ? `<div class="rap-sectie">
      <h3>Je grootste lek</h3>
      <div class="rap-fout">
        <div class="rf-code">${d.top_fout.code}</div>
        <div>
          <div><b>${d.top_fout.omschrijving}</b> — ${d.top_fout.aantal}× deze periode</div>
          <div class="rap-correctie">→ ${d.top_fout.correctie}</div>
        </div>
      </div>
      ${d.patronen.length ? `<p class="hint" style="margin-top:10px">
        ${d.patronen.length} patroon (3× binnen 10 trades): ${d.patronen.map((p) => p.code).join(", ")}.
        Zie de foutenpagina voor de corrigerende regels.</p>` : ""}
    </div>` : ""}

    ${d.tags && d.tags.tags.length ? `<div class="rap-sectie">
      <h3>Per tag</h3>
      <div class="mt-table-wrap">
        <table class="mt"><thead><tr>
          <th style="text-align:left">Tag</th><th>Trades</th><th>Winrate</th><th>Expectancy</th><th>Netto</th>
        </tr></thead><tbody>
          ${d.tags.tags.map((t) => `<tr class="${t.betrouwbaar ? "" : "zwak"}">
            <td style="text-align:left">${t.tag}</td><td>${t.n}</td><td>${t.winrate}%</td>
            <td class="${t.expectancy_r >= 0 ? "pos" : "neg"}">${rr(t.expectancy_r)}</td>
            <td>${eur(t.netto_eur)}</td></tr>`).join("")}
        </tbody></table>
      </div>
      <p class="hint" style="margin-top:8px">Grijs = minder dan ${d.tags.min_n} trades met die tag.</p>
    </div>` : ""}

    ${d.lessen.length ? `<div class="rap-sectie">
      <h3>Wat je zelf opschreef</h3>
      <ul class="rap-lessen">${d.lessen.map((l) => `<li>${l}</li>`).join("")}</ul>
    </div>` : ""}

    ${d.reviews.length ? `<div class="rap-sectie">
      <h3>Je dag- en weekreviews</h3>
      ${d.reviews.map((r) => `<div class="rap-review">
        <div class="rr-sleutel">${r.soort} ${r.sleutel}</div>
        <div>
          ${r.goed ? `<div><span class="rr-lbl">goed</span> ${r.goed}</div>` : ""}
          ${r.beter ? `<div><span class="rr-lbl">beter</span> ${r.beter}</div>` : ""}
          ${r.focus ? `<div><span class="rr-lbl">focus</span> ${r.focus}</div>` : ""}
        </div>
      </div>`).join("")}
    </div>` : ""}

    <div class="rap-voet">CBR Journal · XAUUSD · 2e uur Londen · gegenereerd op ${todayISO()}</div>`;
}

boot();
