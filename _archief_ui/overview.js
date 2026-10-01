// Dagoverzicht — landingspagina.

let currentDate = qs("datum") || todayISO();

async function boot() {
  const picker = document.getElementById("datePicker");
  picker.value = currentDate;
  picker.addEventListener("change", () => {
    currentDate = picker.value;
    history.replaceState(null, "", "/?datum=" + encodeURIComponent(currentDate));
    load();
  });
  document.getElementById("saveDag").addEventListener("click", bewaarDag);
  await load();
}

async function load() {
  const d = encodeURIComponent(currentDate);
  document.getElementById("addTrade").href = "/nieuw?datum=" + d;
  document.getElementById("addTradeVol").href = "/trade?datum=" + d;
  document.getElementById("addNoTrade").href = "/notrade?datum=" + d;
  document.getElementById("planTrade").href = "/trade?plan=1&datum=" + d;
  document.getElementById("snelLoggen").href = "/snel?datum=" + d;

  const day = await api("/api/day/" + currentDate);
  renderSummary(day.summary);
  const genomen = day.trades.filter((t) => (t.status || "genomen") === "genomen");
  renderTrades(genomen);
  renderPlannen(day.trades.filter((t) => t.status === "gepland"));
  renderOvergeslagen(day.trades.filter((t) => t.status === "overgeslagen"));
  renderNoTrades(day.no_trades);
  renderWeekFocus(day.week_focus, day.week_focus_af, day.week_maandag);
  renderDagregels(day.dagregels);
  renderVoorbereiding(day.voorbereiding);
  renderSessie(currentDate);
  renderDagReview(day.review);
}

function renderWeekFocus(focus, af, maandag) {
  // Ronde 3, punt 5: je focus blijft bovenaan staan tot je 'm afvinkt.
  const box = document.getElementById("weekFocus");
  if (!focus || af === "ja") { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="focus-banner"><span class="ic">🎯</span>
      <div><b>Focus deze week:</b> ${focus}</div>
      <div class="spacer" style="flex:1"></div>
      <button class="btn" id="focusKlaar">Gelukt ✓</button></div>`;
  const kn = document.getElementById("focusKlaar");
  if (kn) kn.addEventListener("click", async () => {
    try {
      await api(`/api/review/week/${maandag}/focus_af`,
        { method: "PUT", body: JSON.stringify({ af: true }) });
      box.innerHTML = "";
      toast("Focus afgevinkt — mooi.");
    } catch (e) { toast("Opslaan mislukt: " + e.message, true); }
  });
}

// Fase 14.2 -- de routine die vóór de sessie hoort.
let CONFIG_V = null;

async function renderVoorbereiding(v) {
  const box = document.getElementById("voorbereiding");
  if (!box || !v) return;
  if (!CONFIG_V) {
    try { CONFIG_V = (await api("/api/config")).voorbereiding || []; } catch (e) { return; }
  }
  const open = box.querySelector(".vb.uit") ? false : v.compleet;
  box.innerHTML = `
    <div class="vb ${v.compleet ? "klaar" : ""} ${open ? "uit" : ""}">
      <div class="vb-kop">
        <span class="vb-ic">${v.compleet ? "✓" : "◷"}</span>
        <b>Voorbereiding</b>
        <span class="vb-tel">${v.n} van ${v.totaal}</span>
        ${v.compleet
          ? `<span class="vb-msg goed">Klaar voor de sessie.</span>`
          : `<span class="vb-msg">${v.codes.length
              ? "Nog niet af — dit is waar " + v.codes.join(" en ") + " vandaan komen."
              : "Vink af wat je gedaan hebt."}</span>`}
        <div class="spacer" style="flex:1"></div>
        <button class="btn vb-klap">${v.compleet ? "Tonen" : "Verbergen"}</button>
      </div>
      <div class="vb-lijst">
        ${CONFIG_V.map((c) => `
          <label class="vb-punt ${v.punten.includes(c.key) ? "aan" : ""}">
            <input type="checkbox" data-k="${c.key}" ${v.punten.includes(c.key) ? "checked" : ""} />
            <span class="vb-t">${c.label}</span>
            <span class="vb-h">${c.help}</span>
          </label>`).join("")}
      </div>
    </div>`;
  box.querySelectorAll(".vb-punt input").forEach((el) => {
    el.addEventListener("change", async () => {
      const punten = [...box.querySelectorAll(".vb-punt input:checked")].map((x) => x.dataset.k);
      try {
        const nieuw = await api("/api/voorbereiding/" + currentDate,
          { method: "PUT", body: JSON.stringify({ punten }) });
        renderVoorbereiding(nieuw);
        if (nieuw.compleet) toast("Voorbereiding compleet — succes vandaag");
      } catch (e) { toast("Opslaan mislukt: " + e.message, true); }
    });
  });
  const klap = box.querySelector(".vb-klap");
  if (klap) klap.addEventListener("click", () => {
    const vb = box.querySelector(".vb");
    vb.classList.toggle("uit");
    klap.textContent = vb.classList.contains("uit") ? "Tonen" : "Verbergen";
  });
}

/* =====================================================================
   Discipline-kaart per sessie (ronde 3, punt 2).

   Bewust op DAGniveau en bewust klein: drie klikken en één zin. Per trade een
   stemming bijhouden is een klus die je na een week laat vallen, en dan heb je
   niets. Dit is de laag waar "groeien als mens" zit -- niet in nóg een grafiek.
   ===================================================================== */
let CONFIG_S = null;

async function renderSessie(datum) {
  const box = document.getElementById("sessieKaart");
  if (!box) return;
  if (!CONFIG_S) {
    try {
      const c = await api("/api/config");
      CONFIG_S = { toggles: c.sessie_toggles || [], staten: c.staten || [] };
    } catch (e) { return; }
  }
  let s;
  try { s = await api("/api/sessie/" + datum); } catch (e) { return; }

  const ingevuld = !!(s.in_venster || s.plan_gevolgd || s.staat || (s.les || "").trim());
  const jaNee = (veld) => CONFIG_S.toggles.length ? "" : "";

  box.innerHTML = `
    <div class="sessie ${ingevuld ? "gevuld" : ""}">
      <div class="sessie-kop">
        <span class="sessie-ic">${ingevuld ? "✓" : "◷"}</span>
        <b>Hoe ging het vandaag?</b>
        <span class="sessie-sub">Drie klikken en één zin. Dit is het stuk dat je trades niet meten.</span>
      </div>

      ${CONFIG_S.toggles.map((t) => `
        <div class="sessie-rij">
          <span class="sessie-lbl">${t.label}<em>${t.help}</em></span>
          <div class="seg-sm" data-veld="${t.key}">
            <button type="button" data-v="ja" class="${s[t.key] === "ja" ? "on" : ""}">ja</button>
            <button type="button" data-v="nee" class="${s[t.key] === "nee" ? "on" : ""}">nee</button>
          </div>
        </div>`).join("")}

      <div class="sessie-rij">
        <span class="sessie-lbl">Hoe stond je erin vóór de sessie?<em>Niet per trade — één keer per dag is genoeg.</em></span>
        <div class="seg-sm" data-veld="staat">
          ${CONFIG_S.staten.map((o) => `
            <button type="button" data-v="${o.key}" class="${s.staat === o.key ? "on" : ""}">${o.label}</button>`).join("")}
        </div>
      </div>

      <label class="sessie-les">
        <span class="lbl">Belangrijkste les vandaag</span>
        <input type="text" id="sessieLes" value="${(s.les || "").replace(/"/g, "&quot;")}"
               placeholder="Eén regel is genoeg." />
      </label>
    </div>`;

  const bewaar = async (patch) => {
    const body = {
      in_venster: s.in_venster || "", plan_gevolgd: s.plan_gevolgd || "",
      staat: s.staat || "", les: (document.getElementById("sessieLes") || {}).value || "",
      ...patch,
    };
    try {
      s = await api("/api/sessie/" + datum, { method: "PUT", body: JSON.stringify(body) });
      renderSessie(datum);
    } catch (e) { toast("Opslaan mislukt: " + e.message, true); }
  };

  box.querySelectorAll(".seg-sm").forEach((seg) => {
    const veld = seg.dataset.veld;
    seg.querySelectorAll("button").forEach((b) => {
      b.addEventListener("click", () => {
        const nieuw = s[veld] === b.dataset.v ? "" : b.dataset.v;   // nogmaals klikken = leeg
        bewaar({ [veld]: nieuw });
      });
    });
  });
  const les = document.getElementById("sessieLes");
  if (les) les.addEventListener("blur", () => { if (les.value !== (s.les || "")) bewaar({ les: les.value }); });
}

// Fase 9.4 -- de vangrail: hoeveel trades heb je vandaag, en wat zeggen je regels?
function renderDagregels(r) {
  const box = document.getElementById("dagregels");
  if (!box) return;
  if (!r || !r.max_trades) { box.innerHTML = ""; return; }
  const vakjes = [];
  for (let i = 0; i < Math.max(r.max_trades, r.n_genomen); i++) {
    const over = i >= r.max_trades;
    vakjes.push(`<i class="vak ${i < r.n_genomen ? (over ? "over" : "vol") : "leeg"}"></i>`);
  }
  const hard = r.over_limiet || r.na_stop;
  box.innerHTML = `<div class="dagregel-balk ${hard ? "stop" : r.op_limiet ? "vol" : ""}">
      <div class="dr-meter">${vakjes.join("")}</div>
      <div class="dr-tekst">
        <b>${r.n_genomen} van ${r.max_trades} trades vandaag</b>
        ${r.verliezers_op_rij ? ` · ${r.verliezers_op_rij} verlies${r.verliezers_op_rij > 1 ? "sers" : ""} op rij` : ""}
        ${r.boodschap ? `<span class="dr-msg">${r.boodschap}</span>` : ""}
      </div>
    </div>`;
}

function renderDagReview(r) {
  r = r || {};
  document.getElementById("dagGoed").value = r.goed || "";
  document.getElementById("dagBeter").value = r.beter || "";
  document.getElementById("dagFocus").value = r.focus || "";
  const gevuld = (r.goed || r.beter || r.focus);
  document.getElementById("reviewGevuld").innerHTML = gevuld
    ? `<div class="review-gevuld"><b>✓ Dag afgesloten.</b> Je kunt het hieronder nog bijwerken.</div>` : "";
}

async function bewaarDag() {
  const body = JSON.stringify({
    goed: document.getElementById("dagGoed").value,
    beter: document.getElementById("dagBeter").value,
    focus: document.getElementById("dagFocus").value,
  });
  try {
    await api(`/api/review/dag/${currentDate}`, { method: "PUT", body });
    toast("Dag afgesloten");
    load();
  } catch (e) { toast("Opslaan mislukt: " + e.message, true); }
}

function renderSummary(s) {
  const box = document.getElementById("summary");
  const netClass = eurClass(s.netto_eur);
  box.innerHTML = `
    <div class="stat"><div class="num">${s.n_trades}</div><div class="cap">Trades</div></div>
    <div class="stat"><div class="num">${s.valide_pct}%</div><div class="cap">Valide setups</div></div>
    <div class="stat"><div class="num ${netClass}">${fmtEur(s.netto_eur)}</div><div class="cap">Netto (incl. charges)</div></div>
    <div class="stat"><div class="num">${s.winrate}%</div><div class="cap">Winrate</div></div>
    <div class="stat"><div class="num">${s.n_fouten}</div><div class="cap">Fouten gemaakt</div></div>
    <div class="stat"><div class="num">${s.n_no_trades}</div><div class="cap">No-trades</div></div>`;
}

function critDot(val, label) {
  return `<div class="crit-icon">
      <div class="dot v-${val}">${SYMBOLS[val]}</div>
      <span>${label}</span>
    </div>`;
}

function renderTrades(trades) {
  const box = document.getElementById("tradeCards");
  document.getElementById("tradesTitle").textContent = `Trades (${trades.length})`;
  if (!trades.length) {
    box.innerHTML = `<div class="empty">Nog geen trades op deze dag. Klik op <b>+ Trade</b>.</div>`;
    return;
  }
  box.innerHTML = "";
  trades.forEach((t) => {
    const netto = (t.resultaat_eur || 0) + (t.charges || 0);
    const shot = (t.screenshots && t.screenshots[0]) ? t.screenshots[0] : null;
    const nshots = (t.screenshots || []).length;
    const thumb = shot
      ? `<div class="thumb" style="background-image:url('${shotUrl(shot.pad)}')">${nshots > 1 ? `<span class="thumb-badge">${nshots} 📷</span>` : ""}</div>`
      : `<div class="thumb">geen screenshot — sleep er een in bij bewerken</div>`;
    const fouten = (t.foutcodes || "").split(",").map((s) => s.trim()).filter(Boolean);

    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-head">
        <div class="grade grade-${t.grade}">${t.grade}</div>
        <div class="result-eur ${eurClass(t.resultaat_eur)}">${fmtEur(t.resultaat_eur)}</div>
      </div>
      <div class="card-time">${t.tijd_entry ? t.tijd_entry + " · " : ""}${t.instrument}
        ${t.richting ? `<span class="dir-pill ${t.richting}">${t.richting === "long" ? "▲ long" : "▼ short"}</span>` : ""}</div>
      <div class="crit-icons">
        ${critDot(t.crit1_conditie, "1 range")}
        ${critDot(t.crit2_sweep, "2 sweep")}
        ${critDot(t.crit3_shift, "3 shift")}
      </div>
      ${thumb}
      ${t.les ? `<div class="les">“${t.les}”</div>` : ""}
      ${fouten.length ? `<div class="foutcodes">${fouten.map((c) => `<span class="tag fout">${c}</span>`).join("")}</div>` : ""}
      <div style="margin-top:8px;font-size:12px;color:var(--muted)">netto ${fmtEur(netto)}</div>`;
    card.addEventListener("click", () => { location.href = "/trade?id=" + t.id; });
    box.appendChild(card);
  });
}

function critRij(t) {
  return `<div class="crit-icons">
    ${critDot(t.crit1_conditie, "1 range")}
    ${critDot(t.crit2_sweep, "2 sweep")}
    ${critDot(t.crit3_shift, "3 shift")}
  </div>`;
}

async function zetStatus(id, status, skip_reden) {
  try {
    await api(`/api/trade/${id}/status`, {
      method: "PUT", body: JSON.stringify({ status, skip_reden: skip_reden || "" }) });
    load();
  } catch (e) { toast("Mislukt: " + e.message, true); }
}

// Fase 11.2 — waarom bleef je weg? Bij een C is dat de checklist; bij een A of B
// is het een keuze die geld kost, dus die vragen we uit.
// Gegroepeerd naar soort, want "overgeslagen" is vier verschillende dingen.
// De volgorde is bewust: eerst wat je goed deed, dan wat je jezelf mag
// aanrekenen, dan wat helemaal geen fout was.
const SKIP_KEUZES = [
  ["regels", "De checklist zei nee", "bewust"],
  ["buiten_venster", "Buiten het tijdvenster", "bewust"],
  ["twijfel", "Twijfel — ik durfde niet", "aarzeling"],
  ["geen_order", "Geen order neergelegd", "uitvoering"],
  ["te_laat", "Te laat gezien", "uitvoering"],
  ["niet_aan_scherm", "Niet aan het scherm", "uitvoering"],
  ["order_niet_gevuld", "Order lag klaar, net niet gevuld", "markt"],
  ["anders", "Andere reden", "onbekend"],
];

const SKIP_SOORT_KOP = {
  bewust: "Bewust — je regel deed zijn werk",
  aarzeling: "Aarzeling — je durfde niet",
  uitvoering: "Uitvoering — je was er niet bij",
  markt: "Geen fout — de markt kwam niet",
  onbekend: "",
};

function vraagSkipReden(kaart, grade, klaar) {
  if (grade === "C") { klaar("regels"); return; }
  const oud = kaart.querySelector(".skip-vraag");
  if (oud) { oud.remove(); return; }
  const box = document.createElement("div");
  box.className = "skip-vraag";
  let laatsteSoort = null;
  const keuzes = SKIP_KEUZES.map(([k, l, soort]) => {
    const kop = (soort !== laatsteSoort && SKIP_SOORT_KOP[soort])
      ? `<div class="sv-groep">${SKIP_SOORT_KOP[soort]}</div>` : "";
    laatsteSoort = soort;
    return kop + `<button type="button" data-k="${k}" data-soort="${soort}">${l}</button>`;
  }).join("");
  box.innerHTML = `<div class="sv-kop">Dit was een valide setup (${grade}). Waarom bleef je weg?</div>
    <div class="sv-keuzes">${keuzes}</div>`;
  box.addEventListener("click", (ev) => ev.stopPropagation());
  box.querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => klaar(b.dataset.k));
  });
  kaart.appendChild(box);
}

function renderPlannen(plannen) {
  const box = document.getElementById("planCards");
  const titel = document.getElementById("planTitle");
  titel.style.display = plannen.length ? "" : "none";
  box.innerHTML = "";
  plannen.forEach((t) => {
    const card = document.createElement("div");
    card.className = "card gepland";
    const advies = t.grade === "C"
      ? `<div style="color:var(--red);font-weight:600;margin-bottom:4px">✕ Niet nemen</div>`
      : `<div style="color:var(--green);font-weight:600;margin-bottom:4px">✓ Mag je nemen</div>`;
    card.innerHTML = `
      <div class="card-head">
        <div class="grade grade-${t.grade}">${t.grade}</div>
        <span class="badge-status gepland">gepland</span>
      </div>
      <div class="card-time">${t.tijd_entry ? t.tijd_entry + " · " : ""}${t.instrument}
        ${t.richting ? `<span class="dir-pill ${t.richting}">${t.richting === "long" ? "▲ long" : "▼ short"}</span>` : ""}</div>
      ${advies}
      ${critRij(t)}
      <div class="plan-acties">
        <button class="ja">Ik heb 'm genomen</button>
        <button class="nee">Toch weggebleven</button>
      </div>`;
    card.querySelector(".ja").addEventListener("click", async (ev) => {
      ev.stopPropagation();
      if (t.grade === "C" && !confirm("Dit plan is grade C — je eigen regels zeggen: niet nemen.\n\nToch als genomen markeren? Dan wordt E5 (C-setup geforceerd) automatisch toegevoegd.")) return;
      await zetStatus(t.id, "genomen");
      location.href = "/trade?id=" + t.id;
    });
    card.querySelector(".nee").addEventListener("click", (ev) => {
      ev.stopPropagation();
      vraagSkipReden(card, t.grade, (reden) => zetStatus(t.id, "overgeslagen", reden));
    });
    box.appendChild(card);
  });
}

function renderOvergeslagen(lijst) {
  const box = document.getElementById("skipCards");
  const titel = document.getElementById("skipTitle");
  titel.style.display = lijst.length ? "" : "none";
  box.innerHTML = "";
  lijst.forEach((t) => {
    const card = document.createElement("div");
    card.className = "card overgeslagen";
    card.innerHTML = `
      <div class="card-head">
        <div class="grade grade-${t.grade}">${t.grade}</div>
        ${skipBadge(t)}
      </div>
      <div class="card-time">${t.tijd_entry ? t.tijd_entry + " · " : ""}${t.instrument}</div>
      ${critRij(t)}
      <div style="font-size:13px;color:var(--muted);margin-top:6px">
        ${skipTekst(t)}</div>`;
    card.addEventListener("click", () => { location.href = "/trade?id=" + t.id; });
    box.appendChild(card);
  });
}

const SKIP_LABEL = {
  regels: "De checklist zei nee — precies waar hij voor is.",
  buiten_venster: "Buiten het tijdvenster — wegblijven is dan de regel.",
  twijfel: "Twijfel. De setup was valide; dit kostte je geld.",
  geen_order: "Geen order neergelegd, en toen liep hij weg. Routine, geen model.",
  te_laat: "Te laat gezien. Vaak een routine-probleem, geen setup-probleem.",
  niet_aan_scherm: "De setup was er, jij niet. Dit los je op met je agenda.",
  order_niet_gevuld: "Je order lag klaar en de prijs kwam er net niet aan. Geen fout.",
  anders: "Andere reden.",
};

// Welke redenen tellen als 'gemist' op de badge, en welke niet. Een order die
// net niet vulde is geen gemiste kans die je jezelf mag aanrekenen.
const SKIP_GEEN_FOUT = new Set(["regels", "buiten_venster", "order_niet_gevuld"]);

// Drie badges in plaats van twee. Een order die net niet vulde krijgt niet
// hetzelfde stempel als een setup die je uit angst liet lopen.
function skipBadge(t) {
  if (t.skip_reden === "order_niet_gevuld") {
    return `<span class="badge-status overgeslagen markt" title="Je order lag klaar; de prijs kwam er net niet aan.">≈ net misgelopen</span>`;
  }
  if (t.grade === "C" || SKIP_GEEN_FOUT.has(t.skip_reden)) {
    return `<span class="badge-status overgeslagen">🛡️ discipline</span>`;
  }
  return `<span class="badge-status overgeslagen gemist">◌ gemist</span>`;
}

function skipTekst(t) {
  if (t.skip_reden && SKIP_LABEL[t.skip_reden]) return SKIP_LABEL[t.skip_reden];
  if (t.grade === "C") return "Je zag de setup en bent weggebleven. Precies wat de checklist zegt.";
  return "Valide setup, geen reden ingevuld. Open 'm en zeg eerlijk waarom.";
}

function renderNoTrades(nts) {
  const box = document.getElementById("noTradeCards");
  document.getElementById("noTradesTitle").textContent = `No-trades (${nts.length})`;
  if (!nts.length) {
    box.innerHTML = `<div class="empty">Geen bewuste no-trades genoteerd.</div>`;
    return;
  }
  box.innerHTML = "";
  nts.forEach((nt) => {
    const shot = (nt.screenshots && nt.screenshots[0]) ? nt.screenshots[0] : null;
    const card = document.createElement("div");
    card.className = "card no-trade";
    card.innerHTML = `
      <div class="card-head">
        <div class="tag">NO-TRADE</div>
        <div class="card-time">${nt.tijd || ""}</div>
      </div>
      <div style="font-weight:600;margin-bottom:6px">${nt.reden || "—"}</div>
      <div style="font-size:13px;color:var(--muted)">${nt.wat_zag_ik || ""}</div>
      ${shot ? `<div class="thumb" style="background-image:url('${shotUrl(shot.pad)}');margin-top:10px"></div>` : ""}`;
    card.addEventListener("click", () => { location.href = "/notrade?id=" + nt.id; });
    box.appendChild(card);
  });
}

boot();
