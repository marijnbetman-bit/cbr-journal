"""
Wanneer ben ik goed? (fase 10.2, 10.3 en 10.4)

10.2  Kwartier- en weekdaganalyse. Je handelt één uur per dag; binnen dat uur
      zitten vier kwartieren en die presteren zelden gelijk. Je eigen regel zegt
      al: zoek entries pas na ~20 minuten in de hourly candle. Hier zie je of dat
      klopt met je resultaten.

10.3  Is je onderbuik gekalibreerd? Je logt zekerheid 1-5 en emotie-chips.
      Als je vijven slechter presteren dan je drieën, is overtuiging jouw
      waarschuwingssignaal.

10.4  Discipline-meter. Edgewonk laat je zelf een tiltscore invullen; wij leiden
      hem af uit wat er al in de journal staat, zodat je niets extra hoeft te doen.

Alle R-uitkomsten komen uit edge.py.
"""

from datetime import date

from . import edge

MIN_N = 10          # onder dit aantal zeggen we het eerlijk: te weinig data
WEEKDAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
             "zaterdag", "zondag"]
KWARTIEREN = [(0, "00–14"), (15, "15–29"), (30, "30–44"), (45, "45–59")]


def _cel(naam, trades, extra=None):
    n = len(trades)
    rs = [edge.r_van_trade(t)[0] for t in trades]
    winners = [t for t in trades if (t.get("resultaat_eur") or 0) > 0]
    cel = {
        "naam": naam,
        "n": n,
        "winrate": round(100 * len(winners) / n) if n else 0,
        "expectancy_r": round(sum(rs) / n, 3) if n else 0.0,
        "netto_eur": round(sum(edge._netto(t) for t in trades), 2),
        "genoeg": n >= MIN_N,
    }
    if extra:
        cel.update(extra)
    return cel


def _minuut(t):
    tijd = (t.get("tijd_entry") or "").strip()
    if ":" not in tijd:
        return None
    try:
        return int(tijd.split(":")[1])
    except (ValueError, IndexError):
        return None


def _uur(t):
    tijd = (t.get("tijd_entry") or "").strip()
    if ":" not in tijd:
        return None
    try:
        return int(tijd.split(":")[0])
    except (ValueError, IndexError):
        return None


# ---------- 10.2 ----------

def timing(trades):
    met_tijd = [t for t in trades if _minuut(t) is not None]

    kwart = []
    for start, label in KWARTIEREN:
        groep = [t for t in met_tijd if start <= _minuut(t) < start + 15]
        kwart.append(_cel(label, groep, {"start": start}))

    per_uur = {}
    for t in met_tijd:
        per_uur.setdefault(_uur(t), []).append(t)
    uren = [_cel(f"{u:02d}:00", per_uur[u], {"uur": u}) for u in sorted(per_uur)]

    per_dag = {}
    for t in trades:
        try:
            wd = date.fromisoformat(t.get("datum") or "").weekday()
        except ValueError:
            continue
        per_dag.setdefault(wd, []).append(t)
    dagen = [_cel(WEEKDAGEN[wd], per_dag[wd], {"weekdag": wd}) for wd in sorted(per_dag)]

    # De beste en slechtste bak, maar alleen als er genoeg in zit om iets te zeggen.
    bruikbaar = [k for k in kwart if k["n"] >= 3]
    beste = max(bruikbaar, key=lambda k: k["expectancy_r"], default=None)
    slechtste = min(bruikbaar, key=lambda k: k["expectancy_r"], default=None)

    conclusie = ""
    if beste and slechtste and beste["naam"] != slechtste["naam"]:
        verschil = round(beste["expectancy_r"] - slechtste["expectancy_r"], 2)
        conclusie = (f"Je beste kwartier is minuut {beste['naam']} "
                     f"({beste['expectancy_r']:+.2f}R over {beste['n']} trades), je slechtste is "
                     f"{slechtste['naam']} ({slechtste['expectancy_r']:+.2f}R over {slechtste['n']}). "
                     f"Verschil: {verschil:+.2f}R per trade.")
        if not (beste["genoeg"] and slechtste["genoeg"]):
            conclusie += (" Allebei nog te weinig trades om er iets aan te veranderen — "
                          f"vanaf {MIN_N} per bak wordt dit bruikbaar.")

    return {
        "kwartieren": kwart,
        "uren": uren,
        "weekdagen": dagen,
        "zonder_tijd": len(trades) - len(met_tijd),
        "conclusie": conclusie,
        "min_n": MIN_N,
    }


# ---------- 10.3 ----------

def kalibratie(trades):
    per_zeker = {}
    for t in trades:
        z = t.get("zekerheid")
        if z:
            per_zeker.setdefault(int(z), []).append(t)
    niveaus = [_cel(str(z), per_zeker[z], {"zekerheid": z}) for z in sorted(per_zeker)]

    hoog = [t for z, rij in per_zeker.items() if z >= 4 for t in rij]
    laag = [t for z, rij in per_zeker.items() if z <= 2 for t in rij]
    h, l = _cel("hoog (4–5)", hoog), _cel("laag (1–2)", laag)

    oordeel = ""
    if hoog and laag:
        d = round(h["expectancy_r"] - l["expectancy_r"], 2)
        if d > 0.2:
            oordeel = (f"Je onderbuik klopt: setups waar je zeker van was leveren {d:+.2f}R per trade "
                       "méér op. Vertrouw je zekerheid — maar laat de checklist beslissen.")
        elif d < -0.2:
            oordeel = (f"Let op: je meest zekere setups presteren {abs(d):.2f}R per trade sléchter. "
                       "Overtuiging is bij jou een waarschuwingssignaal, geen groen licht.")
        else:
            oordeel = ("Je zekerheid zegt tot nu toe niets over je resultaat. Dat is niet erg — "
                       "het betekent dat de checklist het werk doet, niet je gevoel.")
    else:
        oordeel = ("Vul bij je entry de zekerheid 1–5 in. Na een stuk of twintig trades zie je hier "
                   "of je onderbuik gekalibreerd is.")

    per_emotie = {}
    for t in trades:
        for e in (t.get("mentale_staat") or "").split(","):
            e = e.strip()
            if e:
                per_emotie.setdefault(e, []).append(t)
    emoties = sorted([_cel(e, rij, {"emotie": e}) for e, rij in per_emotie.items()],
                     key=lambda c: -c["n"])

    return {
        "niveaus": niveaus,
        "hoog": h, "laag": l,
        "oordeel": oordeel,
        "emoties": emoties,
        "n_met_zekerheid": sum(len(v) for v in per_zeker.values()),
        "min_n": MIN_N,
    }


# ---------- 10.4 ----------

# Wat kost wat. Bewust grof: dit is een thermometer, geen weegschaal.
STRAF = {
    "C_genomen": (25, "C-setup toch genomen"),
    "boven_limiet": (20, "boven je dagmaximum"),
    "na_stop": (25, "doorgegaan na je stoploss-regel"),
    "P1": (20, "revenge"),
    "P2": (15, "overtrading"),
    "P3": (15, "verveling-entry"),
    "P4": (10, "size-up na winst"),
    "E5": (15, "C-setup geforceerd"),
    "E4": (15, "buiten het tijdvenster"),
    "M2": (15, "SL verschoven tegen de regels"),
    "R3": (10, "RR onder de vloer"),
    "geen_screenshot": (5, "geen screenshot"),
    "geen_voorbereiding": (12, "voorbereiding niet af"),
}
BONUS_SKIP = 8          # per bewust overgeslagen setup
BONUS_MAX = 16


def discipline(trades, overgeslagen, max_trades=3, stop_na=2,
               voorbereid=None, n_voorbereiding=5):
    """Per handelsdag een score 0–100, afgeleid uit wat er al in de journal staat."""
    per_dag = {}
    for t in trades:
        per_dag.setdefault(t.get("datum"), []).append(t)
    skips_per_dag = {}
    for t in overgeslagen:
        skips_per_dag[t.get("datum")] = skips_per_dag.get(t.get("datum"), 0) + 1
    for d in skips_per_dag:
        per_dag.setdefault(d, [])

    reeks = []
    for datum in sorted(per_dag):
        dag = sorted(per_dag[datum], key=lambda t: (t.get("tijd_entry") or "", t.get("id") or 0))
        score = 100
        redenen = []

        op_rij = 0
        gestopt_had_gemoeten = False
        for i, t in enumerate(dag):
            codes = {c.strip() for c in (t.get("foutcodes") or "").split(",") if c.strip()}
            if t.get("grade") == "C":
                score -= STRAF["C_genomen"][0]; redenen.append(STRAF["C_genomen"][1])
            if max_trades and i >= max_trades:
                score -= STRAF["boven_limiet"][0]; redenen.append(STRAF["boven_limiet"][1])
            if gestopt_had_gemoeten:
                score -= STRAF["na_stop"][0]; redenen.append(STRAF["na_stop"][1])
            for code in codes:
                if code in STRAF:
                    score -= STRAF[code][0]; redenen.append(STRAF[code][1])
            if not t.get("heeft_screenshot"):
                score -= STRAF["geen_screenshot"][0]

            netto = edge._netto(t)
            if netto < 0:
                op_rij += 1
                if stop_na and op_rij >= stop_na:
                    gestopt_had_gemoeten = True
            elif netto > 0:
                op_rij = 0

        # Fase 14.2 -- de voorbereiding hoort bij de discipline van die dag.
        if voorbereid is not None and dag:
            gedaan = [p for p in (voorbereid.get(datum) or "").split(",") if p.strip()]
            if len(gedaan) < n_voorbereiding:
                score -= STRAF["geen_voorbereiding"][0]
                redenen.append(STRAF["geen_voorbereiding"][1])

        skips = skips_per_dag.get(datum, 0)
        if skips:
            score += min(skips * BONUS_SKIP, BONUS_MAX)

        score = max(0, min(100, score))
        reeks.append({
            "datum": datum,
            "score": score,
            "n": len(dag),
            "netto_eur": round(sum(edge._netto(t) for t in dag), 2),
            "netto_r": round(sum(edge.r_van_trade(t)[0] for t in dag), 2),
            "skips": skips,
            "redenen": sorted(set(redenen)),
        })

    scores = [d["score"] for d in reeks]
    gem = round(sum(scores) / len(scores)) if scores else 0
    laatste3 = round(sum(scores[-3:]) / len(scores[-3:])) if scores else 0
    eerder = scores[:-3]
    eerder_gem = round(sum(eerder) / len(eerder)) if eerder else None

    if not scores:
        trend = "Nog geen handelsdagen om te scoren."
    elif eerder_gem is None:
        trend = f"Gemiddeld {gem}/100 over {len(scores)} handelsdag(en)."
    elif laatste3 > eerder_gem + 5:
        trend = f"Je laatste drie dagen ({laatste3}/100) zijn discipliner dan daarvoor ({eerder_gem}/100)."
    elif laatste3 < eerder_gem - 5:
        trend = (f"Je laatste drie dagen ({laatste3}/100) zijn slordiger dan daarvoor "
                 f"({eerder_gem}/100). Dat gaat meestal een paar dagen vóór de curve uit.")
    else:
        trend = f"Je discipline is stabiel rond {gem}/100."

    return {"reeks": reeks, "gemiddeld": gem, "laatste3": laatste3,
            "eerder": eerder_gem, "trend": trend, "straf": {
                k: {"punten": v[0], "reden": v[1]} for k, v in STRAF.items()}}
