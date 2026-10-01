/* =====================================================================
   Prestatie-tracker: hoe scoor ik, per dag, per maand en per moment.

   Over percentages: elk periodepercentage rekent over het saldo waarmee die
   periode BEGON, en periodes worden samengesteld en niet opgeteld. De server
   rekent dat uit; hier tonen we het alleen, en tonen we "–" als er geen
   startkapitaal is — een percentage zonder basis is betekenisloos.
   ===================================================================== */

let VALUTA = "€";
let period = "alles";
let bron = "live";
const charts = {};

const KLEUR = {
  groen: "#089981", rood: "#f23645", blauw: "#2962ff",
  goud: "#f2900d", grijs: "#98a2b3",
};

function eur(n) {
  if (n === null || n === undefined) return "–";
  return VALUTA + " " + (n >= 0 ? "+" : "") + Number(n).toFixed(2).replace(".", ",");
}
function pct(n) {
  if (n === null || n === undefined) return "–";
  return (n >= 0 ? "+" : "") + Number(n).toFixed(2).replace(".", ",") + "%";
}
function cls(n) { return n > 0 ? "pos" : (n < 0 ? "neg" : ""); }
function mkChart(id, cfg) {
  const el = document.getElementById(id);
  if (!el) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(el, cfg);
}
function kort(datum) {
  if (!datum) return "";
  const [j, m, d] = datum.split("-");
  return `${parseInt(d, 10)}/${parseInt(m, 10)}`;
}
const basisAs = {
  responsive: true, maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { display: false }, ticks: { color: "#787b86", font: { size: 11 } } },
    y: { grid: { color: "rgba(120,123,134,.15)" }, ticks: { color: "#787b86", font: { size: 11 } } },
  },
};

/* ---------- lege staat, in dezelfde toon als de rest ---------- */
function leeg(wat) {
  return `<div class="empty wachtend"><b>Nog niets te zeggen.</b><span>${wat}</span></div>`;
}

/* ---------- tabelhelper ---------- */
function tabel(kop, rijen, cellen) {
  if (!rijen || !rijen.length) return leeg("Zodra je trades hebt gelogd staat het hier.");
  const th = kop.map((k) => `<th${k.num ? ' class="num"' : ""}>${k.t}</th>`).join("");
  const tr = rijen.map((r) => "<tr>" + cellen(r).join("") + "</tr>").join("");
  return `<div class="mt-table-wrap"><table class="mt">
    <thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`;
}
const td = (v, k = "") => `<td${k ? ` class="${k}"` : ""}>${v}</td>`;
const tdn = (v, k = "") => `<td class="num ${k}">${v}</td>`;

/* ---------- kern ---------- */
function renderKern(d) {
  const k = d.kern;
  const cellen = [
    { key: "Saldo", val: eur(k.saldo).replace("+", ""), accent: true },
    { key: "Netto P/L", val: eur(k.netto_eur), cls: cls(k.netto_eur) },
    { key: "Rendement", val: pct(k.groei_pct), cls: cls(k.groei_pct), accent: true },
    { key: "Winrate", val: k.winrate + "%" },
    { key: "Trades", val: String(k.n) },
    { key: "Handelsdagen", val: `${k.handelsdagen} (${k.winst_dagen}↑ ${k.verlies_dagen}↓)` },
    { key: "Gem. per dag", val: eur(k.gem_per_dag_eur), cls: cls(k.gem_per_dag_eur) },
    { key: "Gem. per trade", val: eur(k.gem_per_trade_eur), cls: cls(k.gem_per_trade_eur) },
    { key: "Expectancy", val: k.expectancy_r.toFixed(2) + "R", cls: cls(k.expectancy_r) },
    { key: "Kosten", val: eur(k.kosten_eur), cls: "neg" },
  ];
  document.getElementById("kernBar").innerHTML =
    `<div class="mt-bar">${cellen.map((c) => `
      <div class="mt-cell${c.accent ? " accent" : ""}">
        <div class="k">${c.key}</div>
        <div class="val ${c.cls || ""}">${c.val}</div></div>`).join("")}</div>` +
    (k.startkapitaal
      ? (d.gefilterd
        ? `<p class="hint">Je filtert op een periode. Het rendement blijft gerekend over je
             startkapitaal van ${eur(k.startkapitaal).replace("+", "")} — dat is een
             totaalcijfer, geen periodecijfer.</p>`
        : `<p class="hint">Rendement over je startkapitaal van
             ${eur(k.startkapitaal).replace("+", "")}. De maanden samengesteld komen uit op
             ${pct(k.groei_pct_samengesteld)} — dezelfde uitkomst, zoals het hoort.</p>`)
      : `<p class="hint">Vul je startkapitaal in bij de instellingen op het dashboard,
           dan kan de journal ook percentages tonen.</p>`);

  const noot = document.getElementById("aandeelNoot");
  noot.innerHTML = d.uitschieters.aandeel_waarschuwing
    ? `<div class="dekking-waarschuwing"><strong>Let op je uitschieter.</strong>
       ${d.uitschieters.aandeel_waarschuwing}</div>` : "";
}

/* ---------- saldoverloop ---------- */
function renderEquity(d) {
  const e = d.equity;
  mkChart("cEquity", {
    type: "line",
    data: {
      labels: e.map((p) => p.datum ? kort(p.datum) : "start"),
      datasets: [{
        data: e.map((p) => p.saldo),
        borderColor: KLEUR.blauw, backgroundColor: "rgba(41,98,255,.10)",
        fill: true, tension: .25, pointRadius: 2.5, borderWidth: 2,
      }],
    },
    options: {
      ...basisAs,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              const p = e[c.dataIndex];
              return `Saldo ${eur(p.saldo).replace("+", "")}` +
                (p.pct !== null && p.pct !== undefined ? `  (${pct(p.pct)} t.o.v. start)` : "");
            },
          },
        },
      },
    },
  });
}

/* ---------- per maand ---------- */
function renderMaand(d) {
  const m = d.per_maand;
  if (!m.length) {
    document.getElementById("maandTabel").innerHTML = leeg("Nog geen maand met trades.");
    return;
  }
  mkChart("cMaand", {
    type: "bar",
    data: {
      labels: m.map((x) => x.kort),
      datasets: [{
        data: m.map((x) => x.netto_eur),
        backgroundColor: m.map((x) => x.netto_eur >= 0 ? KLEUR.groen : KLEUR.rood),
        borderRadius: 3,
      }],
    },
    options: {
      ...basisAs,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              const x = m[c.dataIndex];
              return `${eur(x.netto_eur)}  (${pct(x.pct)})  ${x.n} trades`;
            },
          },
        },
      },
    },
  });

  document.getElementById("maandTabel").innerHTML = tabel(
    [{ t: "Maand" }, { t: "Trades", num: true }, { t: "Dagen", num: true },
     { t: "Netto", num: true }, { t: "Rendement", num: true }, { t: "Saldo", num: true }],
    m, (r) => [
      td(r.label), tdn(r.n), tdn(r.handelsdagen),
      tdn(eur(r.netto_eur), cls(r.netto_eur)),
      tdn(pct(r.pct), cls(r.pct)),
      tdn(eur(r.saldo_eind).replace("+", "")),
    ]);
}

/* ---------- per dag ---------- */
function renderDag(d) {
  const dg = d.per_dag;
  if (!dg.length) {
    document.getElementById("dagTabel").innerHTML = leeg("Nog geen handelsdag gelogd.");
    return;
  }
  mkChart("cDag", {
    type: "bar",
    data: {
      labels: dg.map((x) => kort(x.datum)),
      datasets: [{
        data: dg.map((x) => x.netto_eur),
        backgroundColor: dg.map((x) => x.netto_eur >= 0 ? KLEUR.groen : KLEUR.rood),
        borderRadius: 3,
      }],
    },
    options: {
      ...basisAs,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              const x = dg[c.dataIndex];
              return `${eur(x.netto_eur)}  (${pct(x.pct)})  ${x.n} trades · ${x.weekdag}`;
            },
          },
        },
      },
    },
  });

  const laatste = dg.slice(-14).reverse();
  document.getElementById("dagTabel").innerHTML = tabel(
    [{ t: "Dag" }, { t: "Trades", num: true }, { t: "Winrate", num: true },
     { t: "Netto", num: true }, { t: "Dagrendement", num: true }, { t: "Saldo", num: true }],
    laatste, (r) => [
      td(`${kort(r.datum)} <span class="mono" style="color:var(--muted)">${r.weekdag.slice(0, 2)}</span>`),
      tdn(r.n), tdn(r.n ? r.winrate + "%" : "–"),
      tdn(eur(r.netto_eur), cls(r.netto_eur)),
      tdn(pct(r.pct), cls(r.pct)),
      tdn(eur(r.saldo_eind).replace("+", "")),
    ]) + (dg.length > 14 ? `<p class="hint">Laatste 14 van ${dg.length} handelsdagen.</p>` : "");
}

/* ---------- de klok ---------- */
function renderUur(d) {
  const u = d.per_uur;
  if (!u.rijen.length) {
    document.getElementById("uurTabel").innerHTML =
      leeg("Vul de entrytijd in bij je trades, dan verschijnt dit vanzelf.");
    return;
  }
  mkChart("cUur", {
    type: "bar",
    data: {
      labels: u.rijen.map((r) => r.naam),
      datasets: [{
        data: u.rijen.map((r) => r.netto_eur),
        backgroundColor: u.rijen.map((r) => r.netto_eur >= 0 ? KLEUR.groen : KLEUR.rood),
        borderRadius: 3,
      }],
    },
    options: {
      ...basisAs,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              const r = u.rijen[c.dataIndex];
              return `${eur(r.netto_eur)}  ${r.n} trades · winrate ${r.winrate}%`;
            },
          },
        },
      },
    },
  });
  document.getElementById("uurTabel").innerHTML = tabel(
    [{ t: "Uur" }, { t: "n", num: true }, { t: "Winrate", num: true },
     { t: "Netto", num: true }, { t: "Expectancy", num: true }],
    u.rijen, (r) => [
      td(r.naam), tdn(r.n), tdn(r.winrate + "%"),
      tdn(eur(r.netto_eur), cls(r.netto_eur)),
      tdn(r.expectancy_r.toFixed(2) + "R", cls(r.expectancy_r)),
    ]) + (u.zonder_tijd
      ? `<p class="hint">${u.zonder_tijd} ${u.zonder_tijd === 1 ? "trade heeft" : "trades hebben"} geen entrytijd.</p>` : "");
}

function renderMoment(d) {
  const m = d.moment_in_uur;
  mkChart("cMoment", {
    type: "bar",
    data: {
      labels: m.kwartieren.map((r) => r.naam),
      datasets: [{
        data: m.kwartieren.map((r) => r.netto_eur),
        backgroundColor: m.kwartieren.map((r) =>
          r.in_venster ? KLEUR.blauw : (r.netto_eur >= 0 ? KLEUR.groen : KLEUR.rood)),
        borderRadius: 3,
      }],
    },
    options: {
      ...basisAs,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              const r = m.kwartieren[c.dataIndex];
              return `${eur(r.netto_eur)}  ${r.n} trades · winrate ${r.winrate}% · ${r.expectancy_r.toFixed(2)}R` +
                (r.in_venster ? "  — jouw venster" : "");
            },
          },
        },
      },
    },
  });

  mkChart("cVijf", {
    type: "bar",
    data: {
      labels: m.vijf_minuten.map((r) => r.naam),
      datasets: [{
        data: m.vijf_minuten.map((r) => r.netto_eur),
        backgroundColor: m.vijf_minuten.map((r) =>
          r.te_vroeg ? KLEUR.rood : (r.in_venster ? KLEUR.blauw : KLEUR.grijs)),
        borderRadius: 3,
      }],
    },
    options: {
      ...basisAs,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              const r = m.vijf_minuten[c.dataIndex];
              if (!r.n) return "geen trades";
              return `${eur(r.netto_eur)}  ${r.n} trades · winrate ${r.winrate}%` +
                (r.te_vroeg ? "  — vóór minuut 20" : r.in_venster ? "  — jouw venster" : "");
            },
          },
        },
      },
    },
  });

  const rijen = [m.venster, m.buiten_venster, m.te_vroeg];
  document.getElementById("momentOordeel").innerHTML =
    tabel([{ t: "Moment" }, { t: "n", num: true }, { t: "Winrate", num: true },
           { t: "Netto", num: true }, { t: "Expectancy", num: true }],
      rijen, (r) => [
        td(r.naam), tdn(r.n), tdn(r.n ? r.winrate + "%" : "–"),
        tdn(r.n ? eur(r.netto_eur) : "–", cls(r.netto_eur)),
        tdn(r.n ? r.expectancy_r.toFixed(2) + "R" : "–", cls(r.expectancy_r)),
      ]) +
    (m.oordeel ? `<p class="hint" style="margin-top:8px">${m.oordeel}</p>` : "") +
    (m.zonder_tijd ? `<p class="hint">${m.zonder_tijd} zonder entrytijd.</p>` : "");
}

/* ---------- uitsplitsingen ---------- */
function bakTabel(rijen, kop) {
  return tabel([{ t: kop }, { t: "n", num: true }, { t: "Winrate", num: true },
                { t: "Netto", num: true }, { t: "Expectancy", num: true }],
    rijen, (r) => [
      td(r.naam), tdn(r.n), tdn(r.n ? r.winrate + "%" : "–"),
      tdn(eur(r.netto_eur), cls(r.netto_eur)),
      tdn(r.expectancy_r.toFixed(2) + "R", cls(r.expectancy_r)),
    ]);
}

function renderUitsplitsingen(d) {
  document.getElementById("weekdagTabel").innerHTML = bakTabel(d.per_weekdag.rijen, "Weekdag");
  document.getElementById("richtingTabel").innerHTML = bakTabel(d.uitsplitsingen.richting, "Richting");
  document.getElementById("gradeTabel").innerHTML = bakTabel(d.uitsplitsingen.grade, "Grade");
}

/* ---------- reeksen en uitschieters ---------- */
function renderReeksen(d) {
  const r = d.reeksen, u = d.uitschieters;
  document.getElementById("reeksBar").innerHTML = `<div class="mt-bar">
    <div class="mt-cell"><div class="k">Langste winstreeks</div><div class="val pos">${r.langste_winstreeks}</div></div>
    <div class="mt-cell"><div class="k">Langste verliesreeks</div><div class="val neg">${r.langste_verliesreeks}</div></div>
    <div class="mt-cell"><div class="k">Nu bezig</div><div class="val">${
      r.huidige_winstreeks ? r.huidige_winstreeks + "× winst" :
      r.huidige_verliesreeks ? r.huidige_verliesreeks + "× verlies" : "–"}</div></div>
    <div class="mt-cell"><div class="k">Grootste terugval</div><div class="val neg">${eur(-r.grootste_terugval_eur)}</div></div>
    <div class="mt-cell"><div class="k">Payoff</div><div class="val">${u.payoff ?? "–"}</div></div>
  </div>`;

  const rijen = [
    { n: "Beste dag", v: u.beste_dag ? `${kort(u.beste_dag.datum)} · ${eur(u.beste_dag.netto)} (${pct(u.beste_dag.pct)})` : "–", k: "pos" },
    { n: "Slechtste dag", v: u.slechtste_dag ? `${kort(u.slechtste_dag.datum)} · ${eur(u.slechtste_dag.netto)} (${pct(u.slechtste_dag.pct)})` : "–", k: "neg" },
    { n: "Beste trade", v: u.beste_trade ? `${kort(u.beste_trade.datum)} · ${eur(u.beste_trade.netto)}` : "–", k: "pos" },
    { n: "Slechtste trade", v: u.slechtste_trade ? `${kort(u.slechtste_trade.datum)} · ${eur(u.slechtste_trade.netto)}` : "–", k: "neg" },
    { n: "Aandeel grootste winnaar", v: u.grootste_aandeel_pct !== null && u.grootste_aandeel_pct !== undefined ? u.grootste_aandeel_pct + "% van je netto" : "–", k: "" },
  ];
  document.getElementById("uitschietersTabel").innerHTML = tabel(
    [{ t: "" }, { t: "" }], rijen, (r2) => [td(r2.n), td(r2.v, r2.k)]);

  document.getElementById("payoffTabel").innerHTML = tabel(
    [{ t: "" }, { t: "", num: true }],
    [{ n: "Gemiddelde winst", v: eur(u.gem_winst), k: "pos" },
     { n: "Gemiddeld verlies", v: eur(u.gem_verlies), k: "neg" },
     { n: "Payoff (winst / verlies)", v: u.payoff ?? "–", k: "" },
     { n: "Winrate", v: d.kern.winrate + "%", k: "" },
     { n: "Expectancy", v: d.kern.expectancy_r.toFixed(3) + "R", k: cls(d.kern.expectancy_r) }],
    (r2) => [td(r2.n), tdn(r2.v, r2.k)]);
}

/* ---------- laden ---------- */
function periodRange(p) {
  const now = new Date();
  const iso = (dt) => dt.toISOString().slice(0, 10);
  if (p === "week") {
    const day = (now.getDay() + 6) % 7;
    const mon = new Date(now); mon.setDate(now.getDate() - day);
    return { van: iso(mon), tot: iso(now) };
  }
  if (p === "maand") {
    const first = new Date(now.getFullYear(), now.getMonth(), 1);
    return { van: iso(first), tot: iso(now) };
  }
  return { van: null, tot: null };
}

async function load() {
  const { van, tot } = periodRange(period);
  const qp = [];
  if (van) qp.push("van=" + van);
  if (tot) qp.push("tot=" + tot);
  if (period === "regel") qp.push("sinds_regel=true");
  qp.push("bron=" + encodeURIComponent(bron));

  document.body.classList.add("laadt");
  let d;
  try { d = await api("/api/prestaties?" + qp.join("&")); }
  finally { document.body.classList.remove("laadt"); }

  renderKern(d);
  renderEquity(d);
  renderMaand(d);
  renderDag(d);
  renderUur(d);
  renderMoment(d);
  renderUitsplitsingen(d);
  renderReeksen(d);
}

async function boot() {
  try {
    const settings = await api("/api/settings");
    VALUTA = settings.valuta || "€";
  } catch (e) { /* valuta blijft € */ }

  document.querySelectorAll("#periodTabs button").forEach((b) => {
    b.addEventListener("click", () => {
      period = b.dataset.p;
      document.querySelectorAll("#periodTabs button").forEach((x) => x.classList.toggle("on", x === b));
      load();
    });
  });
  document.querySelectorAll("#bronTabs button").forEach((b) => {
    b.addEventListener("click", () => {
      bron = b.dataset.b;
      document.querySelectorAll("#bronTabs button").forEach((x) => x.classList.toggle("on", x === b));
      load();
    });
  });

  await load();
}

boot();
