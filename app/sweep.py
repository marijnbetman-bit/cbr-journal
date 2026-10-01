"""
Sweep-analyse en retro-simulatie van SL-afstanden (ronde 2).

Waarom dit bestaat: twee van de eerste acht trades verloren op precies dezelfde
manier -- SL geraakt met een minimale marge, waarna prijs alsnog het TP-niveau
haalde. Bij trade 8 kwam prijs 3,0 points boven de vorige high uit terwijl de SL
op 2,5 points stond. De SL lag dus BINNEN de sweep.

Dat is geen pech en het is ook geen bewijs dat je SL in het algemeen te krap is.
Het is SL-PLAATSINGSDATA: je stop stond op een niveau waar de beweging waar je
setup op gebouwd is nog niet klaar was. Daarom rekent deze module niet in
"gemiste winst" maar in overleving van de sweep -- zie de noot onderaan.

Alles hier is meetbaar, niets is aangenomen:
  - overleving volgt uit overshoot vs SL-afstand, dat is pure meting;
  - een verliezer telt alleen als scenario-winnaar wanneer JIJ hebt gelogd dat
    prijs na de stop alsnog het TP-niveau haalde (sl_dan_tp = ja).

1 point = 0,10 in prijs.
"""

from . import cbr, edge

MIN_N = 5            # onder dit aantal metingen zeggen we het eerlijk
SL_MIN, SL_MAX = 2.0, 8.0
SL_STAP = 0.5


def _f(waarde):
    """Naar float, of None. Lege strings en rommel horen niet te knallen."""
    if waarde is None or waarde == "":
        return None
    try:
        return float(waarde)
    except (TypeError, ValueError):
        return None


def meetbaar(trades):
    """Trades waarvan we de sweep echt gemeten hebben."""
    uit = []
    for t in trades:
        ov = _f(t.get("sweep_overshoot_points"))
        sl = _f(t.get("sl_afstand_points"))
        if ov is None or sl is None:
            continue
        uit.append(t)
    return uit


def dekking(trades):
    """
    Hoeveel van je trades hebben de meting? Dit is bewust prominent: alleen
    verliezers meten geeft een scheve steekproef, en dan lijkt elke sweep groot.
    """
    totaal = len(trades)
    gemeten = len(meetbaar(trades))
    winnaars = [t for t in trades if (t.get("resultaat_eur") or 0) > 0]
    winnaars_gemeten = len(meetbaar(winnaars))
    return {
        "totaal": totaal,
        "gemeten": gemeten,
        "ontbreekt": totaal - gemeten,
        "winnaars_totaal": len(winnaars),
        "winnaars_gemeten": winnaars_gemeten,
        "volledig": gemeten == totaal and totaal > 0,
        "waarschuwing": (
            "Vul overshoot, SL- en TP-afstand ook bij je winnaars in. "
            "Zolang dat niet gebeurt meet je alleen de trades die misgingen, "
            "en dan lijkt elke sweep groter dan hij is."
            if winnaars_gemeten < len(winnaars) else ""
        ),
    }


# ---------- histogram van de overshoot ----------

def histogram(trades, bin_grootte=1.0):
    """
    Verdeling van sweep_overshoot_points. De vraag die het beantwoordt:
    welk deel van de sweeps past binnen mijn SL-afstand?
    """
    waarden = sorted(_f(t.get("sweep_overshoot_points")) for t in meetbaar(trades))
    if not waarden:
        return {"bins": [], "n": 0, "max": 0.0, "bin_grootte": bin_grootte,
                "mediaan": None, "p80": None, "p95": None}

    grootste = max(waarden)
    aantal_bins = max(1, int(grootste // bin_grootte) + 1)
    bins = []
    for i in range(aantal_bins):
        laag = round(i * bin_grootte, 2)
        hoog = round(laag + bin_grootte, 2)
        # laatste bin is inclusief, anders valt de hoogste waarde eruit
        in_bin = [w for w in waarden
                  if (laag <= w < hoog or (i == aantal_bins - 1 and w == hoog))]
        bins.append({"van": laag, "tot": hoog, "n": len(in_bin),
                     "label": f"{laag:g}–{hoog:g}"})

    def perc(p):
        if not waarden:
            return None
        idx = min(len(waarden) - 1, int(round((p / 100) * (len(waarden) - 1))))
        return round(waarden[idx], 2)

    return {
        "bins": bins,
        "n": len(waarden),
        "max": round(grootste, 2),
        "bin_grootte": bin_grootte,
        "mediaan": perc(50),
        "p80": perc(80),
        "p95": perc(95),
    }


# ---------- retro-simulatie ----------

def _scenario_trade(t, sl_points):
    """
    Wat zou deze trade hebben gedaan met een SL op sl_points?

    overleefd  -- de sweep kwam niet tot aan je stop (overshoot < SL-afstand)
    winnaar    -- werkelijk gewonnen, of: verloren, zou nu overleefd hebben en
                  jij hebt gelogd dat prijs daarna alsnog TP haalde
    rr         -- TP-afstand gedeeld door de gesimuleerde SL-afstand
    """
    ov = _f(t.get("sweep_overshoot_points"))
    tp = _f(t.get("tp_afstand_points"))
    netto = edge._netto(t)
    echt_gewonnen = netto > 0

    overleefd = ov < sl_points
    if not overleefd:
        # De sweep kwam tot aan deze stop. Dat geldt net zo goed voor een trade
        # die je in werkelijkheid won: stond je stop krapper dan de gemeten
        # overshoot, dan had diezelfde beweging je er alsnog uitgehaald.
        # Zonder deze regel lijkt krapper zetten gratis, en dat is het niet.
        winnaar = False
    elif echt_gewonnen:
        winnaar = True
    else:
        winnaar = bool(t.get("sl_dan_tp") == "ja")

    rr = round(tp / sl_points, 2) if (tp is not None and sl_points > 0) else None
    return {
        "id": t.get("id"),
        "datum": t.get("datum"),
        "overleefd": overleefd,
        "winnaar": winnaar,
        "veranderd": (not echt_gewonnen) and winnaar,      # verlies werd winst
        "verspeeld": echt_gewonnen and not winnaar,        # winst werd verlies
        "rr": rr,
        "rr_ok": (rr is not None and rr >= 1),
        "overshoot": ov,
    }


def simuleer(trades, sl_points):
    """Eén SL-instelling doorgerekend over alle gemeten trades."""
    rijen = [_scenario_trade(t, sl_points) for t in meetbaar(trades)]
    n = len(rijen)
    if not n:
        return {"sl_points": sl_points, "n": 0, "genoeg": False}

    overleefd = [r for r in rijen if r["overleefd"]]
    winnaars = [r for r in rijen if r["winnaar"]]
    met_rr = [r for r in rijen if r["rr"] is not None]
    rr_onder_1 = [r for r in met_rr if not r["rr_ok"]]

    return {
        "sl_points": sl_points,
        "sl_prijs": cbr.points_naar_prijs(sl_points),
        "n": n,
        "genoeg": n >= MIN_N,
        "overleefd": len(overleefd),
        "overleefd_pct": round(100 * len(overleefd) / n),
        "winnaars": len(winnaars),
        "winrate": round(100 * len(winnaars) / n),
        "veranderd": len([r for r in rijen if r["veranderd"]]),
        "verspeeld": len([r for r in rijen if r["verspeeld"]]),
        # Bewust apart: bij goud rond 4500 is het verschil tussen 0,25 en 0,50
        # verwaarloosbaar t.o.v. de prijs, dus de TP hoeft meestal niet mee te
        # schuiven en blijft de RR in de praktijk vaak gewoon boven 1. Maar dat
        # moet je per trade kunnen zien, niet aannemen.
        "rr_gemiddeld": round(sum(r["rr"] for r in met_rr) / len(met_rr), 2) if met_rr else None,
        "rr_onder_1": len(rr_onder_1),
        "rr_onder_1_pct": round(100 * len(rr_onder_1) / len(met_rr)) if met_rr else 0,
        "trades": rijen,
    }


def reeks(trades, van=SL_MIN, tot=SL_MAX, stap=SL_STAP):
    """De hele schuifregelaar in één keer, zodat de frontend niet hoeft te pollen."""
    uit, s = [], van
    while s <= tot + 1e-9:
        r = simuleer(trades, round(s, 2))
        r.pop("trades", None)            # per stand de details weglaten: te zwaar
        uit.append(r)
        s += stap
    return uit


def huidige_sl(trades):
    """Je feitelijke SL-afstand: de mediaan van wat je tot nu toe gebruikte."""
    waarden = sorted(_f(t.get("sl_afstand_points")) for t in meetbaar(trades))
    if not waarden:
        return None
    m = len(waarden) // 2
    return round(waarden[m] if len(waarden) % 2 else (waarden[m - 1] + waarden[m]) / 2, 2)


def binnen_de_sweep(trades):
    """
    De kern in één lijst: trades waarvan de SL binnen de sweep lag.
    Dit is SL-plaatsingsdata, geen gemiste winst -- zie de noot in analyse().
    """
    uit = []
    for t in meetbaar(trades):
        marge = cbr.sl_marge(t)
        if marge is not None and marge < 0:
            uit.append({
                "id": t.get("id"), "datum": t.get("datum"),
                "resultaat_eur": t.get("resultaat_eur"),
                "overshoot": _f(t.get("sweep_overshoot_points")),
                "sl_afstand": _f(t.get("sl_afstand_points")),
                "marge": marge,
                "daarna_tp": t.get("sl_dan_tp") == "ja",
            })
    return uit


def analyse(trades, sl_points=None):
    """Alles wat het dashboardpaneel nodig heeft."""
    gemeten = meetbaar(trades)
    nu = huidige_sl(trades)
    gekozen = sl_points if sl_points is not None else (nu or 3.0)
    binnen = binnen_de_sweep(trades)

    return {
        "dekking": dekking(trades),
        "histogram": histogram(trades),
        "huidige_sl": nu,
        "gekozen_sl": gekozen,
        "nu": simuleer(trades, nu) if nu else None,
        "gekozen": simuleer(trades, gekozen) if gemeten else None,
        "reeks": reeks(trades) if gemeten else [],
        "binnen_de_sweep": binnen,
        "min_n": MIN_N,
        # Deze zin hoort in de UI te staan, niet alleen in de code.
        "kader": (
            "Dit is SL-plaatsingsdata, geen gemiste winst. Een stop die binnen "
            "de sweep lag zegt iets over wáár je stop stond ten opzichte van de "
            "beweging waar je setup op gebouwd is -- niet dat je stops in het "
            "algemeen ruimer moeten. Vaker zit het echte probleem in de "
            "setup-kwaliteit of de plaatsing t.o.v. de sweep dan in de breedte."
        ),
    }


# ---------- kwaliteit naast de checklist ----------

def _cel(naam, rij, extra=None):
    n = len(rij)
    rs = [edge.r_van_trade(t)[0] for t in rij]
    winnaars = [t for t in rij if edge._netto(t) > 0]
    cel = {
        "naam": naam,
        "n": n,
        "winrate": round(100 * len(winnaars) / n) if n else 0,
        "expectancy_r": round(sum(rs) / n, 3) if n else 0.0,
        "netto_eur": round(sum(edge._netto(t) for t in rij), 2),
        "genoeg": n >= MIN_N,
    }
    if extra:
        cel.update(extra)
    return cel


def _per_optie(trades, veld, opties):
    per = {}
    for t in trades:
        v = (t.get(veld) or "").strip()
        if v:
            per.setdefault(v, []).append(t)
    rijen = [_cel(o["label"], per.get(o["key"], []), {"key": o["key"], "goed": o["goed"]})
             for o in opties]
    return {
        "rijen": rijen,
        "gelogd": sum(len(v) for v in per.values()),
        "ontbreekt": len(trades) - sum(len(v) for v in per.values()),
    }


def kwaliteit(trades):
    """
    Shift-kwaliteit, volume en overextensie-kwaliteit naast elkaar.
    Een type-3 shift is niet binair: er bestaat duidelijk en er bestaat soft.
    """
    shift = _per_optie(trades, "shift_kwaliteit", cbr.SHIFT_KWALITEIT)
    volume = _per_optie(trades, "volume_hoog", cbr.VOLUME_OPTIES)
    over = _per_optie(trades, "overextensie_kwaliteit", cbr.OVEREXTENSIE_OPTIES)

    duidelijk = next((r for r in shift["rijen"] if r["key"] == "duidelijk"), None)
    soft = next((r for r in shift["rijen"] if r["key"] == "soft"), None)
    oordeel = ""
    if duidelijk and soft and duidelijk["n"] and soft["n"]:
        d = round(duidelijk["expectancy_r"] - soft["expectancy_r"], 2)
        if d > 0:
            oordeel = (f"Duidelijke shifts leveren {d:+.2f}R per trade méér op dan softe. "
                       "Een softe shift is bij jou dus geen halve ✓ maar een ?.")
        else:
            oordeel = ("Softe shifts doen het tot nu toe niet slechter. Te weinig data "
                       "om je regel op aan te passen -- blijf loggen.")
        if not (duidelijk["genoeg"] and soft["genoeg"]):
            oordeel += f" Vanaf {MIN_N} per soort wordt dit bruikbaar."

    return {
        "shift": shift, "volume": volume, "overextensie": over,
        "oordeel": oordeel, "min_n": MIN_N, "tooltip": cbr.SHIFT_TOOLTIP,
    }


def timing_in_hourly(trades):
    """Entry hoort ~30-45 min in de hourly candle te vallen, en pas na ~20 min."""
    per = {"te vroeg (<20)": [], "20–29": [], "30–45 (jouw venster)": [], "na 45": []}
    ontbreekt = 0
    for t in trades:
        m = t.get("minuten_in_hourly")
        if m is None or m == "":
            ontbreekt += 1
            continue
        m = int(m)
        if m < 20:
            per["te vroeg (<20)"].append(t)
        elif m < 30:
            per["20–29"].append(t)
        elif m <= 45:
            per["30–45 (jouw venster)"].append(t)
        else:
            per["na 45"].append(t)
    return {
        "rijen": [_cel(k, v) for k, v in per.items()],
        "ontbreekt": ontbreekt,
        "min_n": MIN_N,
    }
