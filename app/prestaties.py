"""
Prestatie-tracker: hoe scoor ik, uitgesplitst naar tijd en soort trade.

Over percentages, want daar gaat het bijna altijd mis:
  - een periode-percentage rekent over het saldo aan het BEGIN van die periode,
    niet over je startkapitaal en niet over je eindsaldo;
  - percentages van losse periodes tel je NOOIT bij elkaar op. Twee maanden van
    +10% is +21%, niet +20%. Hier wordt daarom altijd samengesteld:
    (1+r1) * (1+r2) - 1;
  - zonder startkapitaal is een percentage betekenisloos; dan geven we None
    terug in plaats van 0, zodat de UI "–" kan tonen en niet "0%".

Alles wat hier "netto" heet is resultaat + charges. Kosten horen bij de trade.
"""

from datetime import date

from . import edge

MIN_N = 5          # onder dit aantal noemen we een bak niet betrouwbaar

WEEKDAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
             "zaterdag", "zondag"]
MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli",
           "augustus", "september", "oktober", "november", "december"]


# ---------- kleine helpers ----------

def _netto(t):
    return edge._netto(t)


def _r(t):
    return edge.r_van_trade(t)[0]


def _uur(t):
    tijd = (t.get("tijd_entry") or "").strip()
    if ":" not in tijd:
        return None
    try:
        u = int(tijd.split(":")[0])
        return u if 0 <= u <= 23 else None
    except (ValueError, IndexError):
        return None


def _minuut(t):
    tijd = (t.get("tijd_entry") or "").strip()
    if ":" not in tijd:
        return None
    try:
        m = int(tijd.split(":")[1])
        return m if 0 <= m <= 59 else None
    except (ValueError, IndexError):
        return None


def _pct(bedrag, basis):
    """Procent over een basis. Geen basis -> None, niet 0."""
    if not basis:
        return None
    return round(100 * bedrag / basis, 2)


def _samengesteld(rendementen):
    """
    Losse periode-rendementen (in procenten) correct samenvoegen.
    +10% en +10% wordt +21%, niet +20%.
    """
    factor = 1.0
    for r in rendementen:
        if r is None:
            continue
        factor *= (1 + r / 100)
    return round((factor - 1) * 100, 2)


def _cel(naam, rij, extra=None):
    """Eén bak: hoeveel, hoe vaak goed, hoeveel het opleverde."""
    n = len(rij)
    winnaars = [t for t in rij if _netto(t) > 0]
    verliezers = [t for t in rij if _netto(t) < 0]
    netto = sum(_netto(t) for t in rij)
    rs = [_r(t) for t in rij]
    cel = {
        "naam": naam,
        "n": n,
        "winnaars": len(winnaars),
        "verliezers": len(verliezers),
        "winrate": round(100 * len(winnaars) / n) if n else 0,
        "netto_eur": round(netto, 2),
        "gem_eur": round(netto / n, 2) if n else 0.0,
        "netto_r": round(sum(rs), 2) if n else 0.0,
        "expectancy_r": round(sum(rs) / n, 3) if n else 0.0,
        "genoeg": n >= MIN_N,
    }
    if extra:
        cel.update(extra)
    return cel


def _groepeer(trades, sleutel):
    per = {}
    for t in trades:
        k = sleutel(t)
        if k is None:
            continue
        per.setdefault(k, []).append(t)
    return per


# ---------- de tijdlijn: per dag, per maand ----------

def _kas_tot(kas, grens, toegepast):
    """Tel kasstromen op met datum <= grens die nog niet meegenomen zijn."""
    som = 0.0
    for i, k in enumerate(kas):
        if i in toegepast:
            continue
        if (k.get("datum") or "") <= grens:
            som += float(k.get("bedrag") or 0)
            toegepast.add(i)
    return som


def per_dag(trades, startkapitaal=0.0, kasstromen=None):
    """
    Elke handelsdag met zijn eigen resultaat en zijn eigen procentuele stijging,
    gerekend over het saldo waarmee die dag BEGON (stortingen van die dag tellen
    al mee in dat beginsaldo). Plus het lopende saldo.
    """
    kas = sorted(kasstromen or [], key=lambda k: (k.get("datum") or "", k.get("tijd") or ""))
    toegepast = set()
    per = _groepeer(trades, lambda t: t.get("datum"))
    saldo = float(startkapitaal)
    rijen = []
    for d in sorted(per):
        dag = per[d]
        saldo += _kas_tot(kas, d, toegepast)
        netto = round(sum(_netto(t) for t in dag), 2)
        begin = saldo
        saldo = round(saldo + netto, 2)
        rijen.append({
            **_cel(d, dag),
            "datum": d,
            "weekdag": WEEKDAGEN[date.fromisoformat(d).weekday()],
            "saldo_begin": round(begin, 2),
            "saldo_eind": saldo,
            "pct": _pct(netto, begin),          # over het beginsaldo van die dag
            "kosten": round(sum(t.get("charges") or 0 for t in dag), 2),
        })
    return rijen


def per_maand(trades, startkapitaal=0.0, kasstromen=None):
    """Per maand; het % is samengesteld uit de dagrendementen (stortingen tellen niet als winst)."""
    dagen = per_dag(trades, startkapitaal, kasstromen)
    per = _groepeer(trades, lambda t: (t.get("datum") or "")[:7])
    rijen = []
    for m in sorted(per):
        maand = per[m]
        mdagen = [d for d in dagen if d["datum"][:7] == m]
        netto = round(sum(_netto(t) for t in maand), 2)
        jaar, nr = m.split("-")
        rijen.append({
            **_cel(m, maand),
            "maand": m,
            "label": f"{MAANDEN[int(nr) - 1]} {jaar}",
            "kort": MAANDEN[int(nr) - 1][:3],
            "handelsdagen": len({t.get("datum") for t in maand}),
            "saldo_begin": mdagen[0]["saldo_begin"] if mdagen else None,
            "saldo_eind": mdagen[-1]["saldo_eind"] if mdagen else None,
            "pct": _samengesteld([d["pct"] for d in mdagen]),
        })
    return rijen


def equity(trades, startkapitaal=0.0, kasstromen=None):
    """Saldoverloop per trade én per kasstroom. `trading` = alleen tradingresultaat
    (startkapitaal + trades), `saldo` = wat er echt op je rekening staat."""
    start = float(startkapitaal)
    events = []
    for t in trades:
        events.append((t.get("datum") or "", t.get("tijd_exit") or t.get("tijd_entry") or "", 1,
                       t.get("id") or 0, "trade", t))
    for k in kasstromen or []:
        events.append((k.get("datum") or "", k.get("tijd") or "00:00", 0, k.get("id") or 0, "kas", k))
    events.sort(key=lambda e: e[:4])
    saldo = trading = start
    punten = [{"label": "start", "saldo": round(saldo, 2), "trading": round(trading, 2),
               "pct": 0.0, "datum": None, "soort": "start"}]
    factor = 1.0
    n = 0
    for datum, tijd, _, _, soort, x in events:
        if soort == "kas":
            saldo = round(saldo + float(x.get("bedrag") or 0), 2)
            punten.append({"label": x.get("soort"), "datum": datum, "tijd": tijd, "saldo": saldo,
                           "trading": round(trading, 2), "pct": round((factor - 1) * 100, 2),
                           "soort": "kas", "kas_soort": x.get("soort"),
                           "bedrag": round(float(x.get("bedrag") or 0), 2),
                           "notitie": x.get("notitie") or ""})
            continue
        n += 1
        net = _netto(x)
        if saldo > 0:
            factor *= 1 + net / saldo
        saldo = round(saldo + net, 2)
        trading = round(trading + net, 2)
        punten.append({"label": f"#{n}", "datum": datum, "tijd": tijd, "saldo": saldo,
                       "trading": trading, "pct": round((factor - 1) * 100, 2),
                       "soort": "trade", "id": x.get("id"), "netto": round(net, 2)})
    return punten


# ---------- de klok: uur en moment in het uur ----------

def per_uur(trades):
    """Welk uur van de dag levert op. Jij handelt er één, dus dit is vooral een check."""
    per = _groepeer(trades, _uur)
    rijen = [_cel(f"{u:02d}:00", per[u], {"uur": u}) for u in sorted(per)]
    zonder = len([t for t in trades if _uur(t) is None])
    beste = max([r for r in rijen if r["n"]], key=lambda r: r["netto_eur"], default=None)
    return {"rijen": rijen, "zonder_tijd": zonder, "beste": beste, "min_n": MIN_N}


def per_moment_in_uur(trades):
    """
    Waar in het uur open je, en scoort dat? Twee korrelgroottes:
    kwartieren voor het grote beeld, blokjes van vijf minuten voor het detail.
    Je eigen regel: entries pas zoeken na ~20 min, entry rond 30-45 min.
    """
    met_tijd = [t for t in trades if _minuut(t) is not None]

    kwartieren = []
    for start, label in [(0, "00–14"), (15, "15–29"), (30, "30–44"), (45, "45–59")]:
        groep = [t for t in met_tijd if start <= _minuut(t) < start + 15]
        kwartieren.append(_cel(label, groep, {
            "start": start,
            "in_venster": start == 30,          # 30-45 is zijn eigen venster
        }))

    vijf = []
    for start in range(0, 60, 5):
        groep = [t for t in met_tijd if start <= _minuut(t) < start + 5]
        vijf.append(_cel(f"{start:02d}–{start + 4:02d}", groep, {
            "start": start,
            "te_vroeg": start < 20,             # vóór minuut 20 = tegen zijn regel
            "in_venster": 30 <= start <= 45,
        }))

    venster = [t for t in met_tijd if 30 <= _minuut(t) <= 45]
    te_vroeg = [t for t in met_tijd if _minuut(t) < 20]
    buiten = [t for t in met_tijd if not (30 <= _minuut(t) <= 45)]

    oordeel = ""
    if venster and buiten:
        v, b = _cel("venster", venster), _cel("buiten", buiten)
        d = round(v["expectancy_r"] - b["expectancy_r"], 2)
        if d > 0:
            oordeel = (f"Binnen je venster van 30–45 minuten haal je {d:+.2f}R per trade "
                       f"méér dan daarbuiten ({v['n']} tegen {b['n']} trades).")
        elif d < 0:
            oordeel = (f"Buiten je venster scoor je tot nu toe {abs(d):.2f}R per trade béter. "
                       "Te weinig trades om je regel op te veranderen — blijf loggen.")
        else:
            oordeel = "Binnen en buiten je venster ontlopen elkaar nog niets."
        if not (v["genoeg"] and b["genoeg"]):
            oordeel += f" Vanaf {MIN_N} per bak wordt dit bruikbaar."

    return {
        "kwartieren": kwartieren,
        "vijf_minuten": vijf,
        "venster": _cel("30–45 (jouw venster)", venster),
        "te_vroeg": _cel("vóór minuut 20", te_vroeg),
        "buiten_venster": _cel("buiten 30–45", buiten),
        "zonder_tijd": len(trades) - len(met_tijd),
        "oordeel": oordeel,
        "min_n": MIN_N,
    }


def per_weekdag(trades):
    per = _groepeer(trades, lambda t: date.fromisoformat(t["datum"]).weekday()
                    if t.get("datum") else None)
    return {"rijen": [_cel(WEEKDAGEN[wd], per[wd], {"weekdag": wd}) for wd in sorted(per)],
            "min_n": MIN_N}


# ---------- uitsplitsingen ----------

def uitsplitsingen(trades):
    """Dezelfde meetlat langs de assen die je al logt."""
    def groep(veld, labels=None):
        per = _groepeer(trades, lambda t: (t.get(veld) or "").strip() or None)
        rijen = [_cel((labels or {}).get(k, k), per[k], {"key": k}) for k in sorted(per)]
        return sorted(rijen, key=lambda r: -r["n"])

    return {
        "richting": groep("richting", {"long": "▲ long", "short": "▼ short"}),
        "grade": groep("grade"),
        "sessie": groep("sessie"),
        "shift_kwaliteit": groep("shift_kwaliteit"),
        "volume": groep("volume_hoog", {"ja": "hoog volume", "nee": "laag volume"}),
        "min_n": MIN_N,
    }


# ---------- reeksen, uitschieters, risico ----------

def reeksen(trades):
    """Langste winst- en verliesreeks, en de grootste terugval in euro's."""
    op_volgorde = sorted(trades, key=lambda t: (t.get("datum") or "",
                                                t.get("tijd_entry") or "", t.get("id") or 0))
    langste_w = langste_v = huidige_w = huidige_v = 0
    for t in op_volgorde:
        n = _netto(t)
        if n > 0:
            huidige_w += 1; huidige_v = 0
        elif n < 0:
            huidige_v += 1; huidige_w = 0
        langste_w = max(langste_w, huidige_w)
        langste_v = max(langste_v, huidige_v)

    # drawdown over het saldoverloop
    saldo = 0.0
    top = 0.0
    diepste = 0.0
    for t in op_volgorde:
        saldo += _netto(t)
        top = max(top, saldo)
        diepste = min(diepste, saldo - top)

    return {
        "langste_winstreeks": langste_w,
        "langste_verliesreeks": langste_v,
        "huidige_winstreeks": huidige_w,
        "huidige_verliesreeks": huidige_v,
        "grootste_terugval_eur": round(abs(diepste), 2),
    }


def uitschieters(trades, dagen):
    winnaars = [t for t in trades if _netto(t) > 0]
    verliezers = [t for t in trades if _netto(t) < 0]
    dagen_met = [d for d in dagen if d["n"]]

    def kop(rij, sleutel, grootste=True):
        if not rij:
            return None
        return (max if grootste else min)(rij, key=sleutel)

    beste_t = kop(winnaars, _netto)
    slechtste_t = kop(verliezers, _netto, grootste=False)
    beste_d = kop(dagen_met, lambda d: d["netto_eur"])
    slechtste_d = kop(dagen_met, lambda d: d["netto_eur"], grootste=False)

    gem_w = round(sum(_netto(t) for t in winnaars) / len(winnaars), 2) if winnaars else 0.0
    gem_v = round(sum(_netto(t) for t in verliezers) / len(verliezers), 2) if verliezers else 0.0

    # Draagt één uitschieter je hele resultaat? Dat is geen edge maar een meevaller.
    netto_totaal = sum(_netto(t) for t in trades)
    aandeel = None
    if beste_t and netto_totaal > 0:
        aandeel = round(100 * _netto(beste_t) / netto_totaal)

    return {
        "beste_trade": {"datum": beste_t.get("datum"), "netto": round(_netto(beste_t), 2)} if beste_t else None,
        "slechtste_trade": {"datum": slechtste_t.get("datum"), "netto": round(_netto(slechtste_t), 2)} if slechtste_t else None,
        "beste_dag": {"datum": beste_d["datum"], "netto": beste_d["netto_eur"], "pct": beste_d["pct"]} if beste_d else None,
        "slechtste_dag": {"datum": slechtste_d["datum"], "netto": slechtste_d["netto_eur"], "pct": slechtste_d["pct"]} if slechtste_d else None,
        "gem_winst": gem_w,
        "gem_verlies": gem_v,
        "payoff": round(abs(gem_w / gem_v), 2) if gem_v else None,
        "grootste_aandeel_pct": aandeel,
        "aandeel_waarschuwing": (
            "Je grootste winnaar draagt meer dan de helft van je resultaat. "
            "Dat is nog geen edge maar een meevaller — één trade mag je cijfers niet maken."
            if (aandeel or 0) >= 50 else ""
        ),
    }


# ---------- alles bij elkaar ----------

def r_laten_liggen(trades):
    """Hoeveel R stond er maximaal in je voordeel dat je niet meepakte.

    Per trade: MFE-in-R (max favorable excursion / SL-afstand) minus de R die je
    echt pakte. Dit is het cijfer achter "te vroeg gesloten": een winnaar die je
    op +0,3R sloot terwijl er +1,3R in zat, liet 1,0R liggen. Alleen trades met
    een gemeten MFE en SL-afstand tellen mee.
    """
    items = []
    for t in trades:
        mfe = t.get("mfe_points")
        sl_afst = t.get("sl_afstand_points")
        if not mfe or not sl_afst or sl_afst <= 0:
            continue
        max_r = mfe / sl_afst
        # Gepakte R op dezelfde puntenbasis als max_r (MT5 resultaat_r). Zo
        # reconcilieert het: een handmatig gesloten winnaar op +0,3R met +1,3R
        # in de kaars liet 1,0R liggen. Alleen oudere trades zonder MT5-R vallen
        # terug op de afgeleide R.
        gepakt = t["resultaat_r"] if t.get("resultaat_r") is not None else _r(t)
        items.append({
            "id": t.get("id"), "datum": t.get("datum"),
            "tijd": t.get("tijd_entry") or "", "richting": t.get("richting") or "",
            "gepakt_r": round(gepakt, 2), "max_r": round(max_r, 2),
            "liggen_r": round(max_r - gepakt, 2), "netto": round(_netto(t), 2),
        })
    winnaars = [x for x in items if x["gepakt_r"] > 0]
    gem_win = round(sum(x["liggen_r"] for x in winnaars) / len(winnaars), 2) if winnaars else 0.0
    totaal = round(sum(max(0.0, x["liggen_r"]) for x in items), 2)
    top = sorted(items, key=lambda x: -x["liggen_r"])[:6]
    return {
        "n": len(items), "n_winnaars": len(winnaars),
        "gem_winnaars_r": gem_win, "totaal_r": totaal, "top": top,
    }


def analyse(trades, startkapitaal=0.0, kosten_apart=True, kasstromen=None):
    kas = list(kasstromen or [])
    dagen = per_dag(trades, startkapitaal, kas)
    maanden = per_maand(trades, startkapitaal, kas)

    bruto = round(sum(t.get("resultaat_eur") or 0 for t in trades), 2)
    kosten = round(sum(t.get("charges") or 0 for t in trades), 2)
    netto = round(bruto + kosten, 2)
    start = float(startkapitaal)
    kas_som = round(sum(float(k.get("bedrag") or 0) for k in kas), 2)
    eind = round(start + netto + kas_som, 2)

    winnaars = [t for t in trades if _netto(t) > 0]
    verliezers = [t for t in trades if _netto(t) < 0]
    rs = [_r(t) for t in trades]
    winst = sum(_netto(t) for t in winnaars)
    verlies = abs(sum(_netto(t) for t in verliezers))
    eq = equity(trades, startkapitaal, kas)
    dd = drawdown(eq)

    kern = {
        "n": len(trades),
        "handelsdagen": len(dagen),
        "bruto_eur": bruto,
        "kosten_eur": kosten,
        "netto_eur": netto,
        "netto_r": round(sum(rs), 2),
        "expectancy_r": round(sum(rs) / len(rs), 3) if rs else 0.0,
        "winrate": round(100 * len(winnaars) / len(trades)) if trades else 0,
        "startkapitaal": round(start, 2),
        "kasstromen": kas_som,
        "saldo": eind,
        # Tijdgewogen rendement: alleen trading, stortingen tellen niet mee.
        "groei_pct": _samengesteld([d["pct"] for d in dagen]),
        "groei_pct_samengesteld": _samengesteld([d["pct"] for d in dagen]),
        "gem_per_dag_eur": round(netto / len(dagen), 2) if dagen else 0.0,
        "gem_per_trade_eur": round(netto / len(trades), 2) if trades else 0.0,
        "kosten_aandeel_pct": round(100 * abs(kosten) / bruto, 1) if bruto > 0 else None,
        "winst_dagen": len([d for d in dagen if d["netto_eur"] > 0]),
        "verlies_dagen": len([d for d in dagen if d["netto_eur"] < 0]),
        "profit_factor": round(winst / verlies, 2) if verlies else None,
        "gem_winst_eur": round(winst / len(winnaars), 2) if winnaars else 0.0,
        "gem_verlies_eur": round(-verlies / len(verliezers), 2) if verliezers else 0.0,
        "gem_winst_r": round(sum(_r(t) for t in winnaars) / len(winnaars), 2) if winnaars else 0.0,
        "gem_verlies_r": round(sum(_r(t) for t in verliezers) / len(verliezers), 2) if verliezers else 0.0,
        "max_dd_eur": dd["max_eur"],
        "max_dd_pct": dd["max_pct"],
        "huidige_dd_eur": dd["huidig_eur"],
    }

    return {
        "kern": kern,
        "per_dag": dagen,
        "per_maand": maanden,
        "per_uur": per_uur(trades),
        "moment_in_uur": per_moment_in_uur(trades),
        "per_weekdag": per_weekdag(trades),
        "per_sessie": per_sessie(trades),
        "heatmap": heatmap(trades),
        "uitsplitsingen": uitsplitsingen(trades),
        "equity": eq,
        "drawdown": dd["reeks"],
        "reeksen": reeksen(trades),
        "r_liggen": r_laten_liggen(trades),
        "r_verdeling": r_verdeling(trades),
        "scatter": scatter(trades),
        "rollend": rollend(trades),
        "proces": proces(trades),
        "emoties": emoties(trades),
        "uitschieters": uitschieters(trades, dagen),
        "min_n": MIN_N,
    }


# ---------- v2 (29 sep 2026): meer grafieken voor de homepage ----------

SESSIES = [  # Amsterdamse tijd
    ("Azië", 0, 9 * 60),
    ("Londen open", 9 * 60, 10 * 60),
    ("Londen", 10 * 60, 14 * 60 + 30),
    ("NY open", 14 * 60 + 30, 16 * 60),
    ("New York", 16 * 60, 22 * 60),
    ("Na-beurs", 22 * 60, 24 * 60),
]


def sessie_van(tijd):
    try:
        u, m = str(tijd).split(":")[:2]
        mm = int(u) * 60 + int(m)
    except (ValueError, AttributeError):
        return None
    for naam, van, tot in SESSIES:
        if van <= mm < tot:
            return naam
    return None


def per_sessie(trades):
    per = _groepeer(trades, lambda t: sessie_van(t.get("tijd_entry")))
    volgorde = [s[0] for s in SESSIES]
    rijen = [_cel(n, per[n], {"van": f"{v // 60:02d}:{v % 60:02d}", "tot": f"{e // 60:02d}:{e % 60:02d}"})
             for n, v, e in SESSIES if n in per]
    beste = max([r for r in rijen if r["n"]], key=lambda r: r["expectancy_r"], default=None)
    return {"rijen": sorted(rijen, key=lambda r: volgorde.index(r["naam"])),
            "beste": beste, "min_n": MIN_N}


def heatmap(trades):
    """Weekdag x uur: aantal, netto en expectancy per vakje."""
    cellen = {}
    for t in trades:
        u = _uur(t)
        if u is None or not t.get("datum"):
            continue
        wd = date.fromisoformat(t["datum"]).weekday()
        cellen.setdefault((wd, u), []).append(t)
    uren = sorted({u for _, u in cellen}) or []
    if uren:
        uren = list(range(min(uren), max(uren) + 1))
    rijen = []
    for wd in range(5):
        rij = []
        for u in uren:
            c = cellen.get((wd, u), [])
            rij.append({"uur": u, "n": len(c),
                        "netto_eur": round(sum(_netto(t) for t in c), 2),
                        "expectancy_r": round(sum(_r(t) for t in c) / len(c), 2) if c else None})
        rijen.append({"weekdag": WEEKDAGEN[wd], "cellen": rij})
    return {"uren": uren, "rijen": rijen}


def drawdown(eq):
    """Onderwaterlijn op het tradingresultaat (stortingen tellen niet)."""
    piek = None
    reeks, max_eur, max_pct = [], 0.0, 0.0
    for p in eq:
        v = p["trading"]
        piek = v if piek is None else max(piek, v)
        d = round(v - piek, 2)
        pc = round(100 * d / piek, 2) if piek else 0.0
        reeks.append({"datum": p.get("datum"), "dd_eur": d, "dd_pct": pc, "soort": p.get("soort")})
        max_eur = min(max_eur, d)
        max_pct = min(max_pct, pc)
    huidig = reeks[-1]["dd_eur"] if reeks else 0.0
    return {"reeks": [r for r in reeks if r["soort"] != "kas"],
            "max_eur": round(max_eur, 2), "max_pct": round(max_pct, 2), "huidig_eur": huidig}


def r_verdeling(trades):
    grenzen = [-99, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25, 1.75, 99]
    labels = ["< -1,25R", "-1R", "-0,5R", "±0", "+0,5R", "+1R", "+1,5R", "> 1,75R"]
    tel = [0] * len(labels)
    for t in trades:
        r = _r(t)
        for i in range(len(labels)):
            if grenzen[i] <= r < grenzen[i + 1]:
                tel[i] += 1
                break
    return {"labels": labels, "aantallen": tel}


def scatter(trades):
    """Per trade: hoe ver ging hij voor/tegen je (in R), hoe lang, en wat pakte je."""
    uit = []
    for t in trades:
        sl = t.get("sl_afstand_points")
        uit.append({
            "id": t.get("id"), "datum": t.get("datum"), "tijd": t.get("tijd_entry"),
            "r": round(_r(t), 2), "netto": round(_netto(t), 2),
            "duur": t.get("duur_minuten"),
            "mfe_r": round(t["mfe_points"] / sl, 2) if t.get("mfe_points") is not None and sl else None,
            "mae_r": round(t["mae_points"] / sl, 2) if t.get("mae_points") is not None and sl else None,
        })
    return uit


def rollend(trades, venster=10):
    op = sorted(trades, key=lambda t: (t.get("datum") or "", t.get("tijd_entry") or "", t.get("id") or 0))
    uit = []
    for i in range(len(op)):
        blok = op[max(0, i - venster + 1): i + 1]
        rs = [_r(t) for t in blok]
        uit.append({"n": i + 1, "datum": op[i].get("datum"),
                    "expectancy_r": round(sum(rs) / len(rs), 3),
                    "winrate": round(100 * sum(1 for t in blok if _netto(t) > 0) / len(blok))})
    return {"venster": venster, "punten": uit}


def proces(trades):
    """Loont het om je regels te volgen? Proces tegen uitkomst."""
    def g(naam, rij):
        return _cel(naam, rij)
    grade = [g(f"Grade {x}", [t for t in trades if (t.get("grade") or "") == x]) for x in ("A", "B", "C")]
    beoordeeld = [t for t in trades if t.get("beoordeeld") == 1]
    schoon = [g("Regels gevolgd", [t for t in beoordeeld if t.get("schoon") == 1]),
              g("Regels gebroken", [t for t in beoordeeld if t.get("schoon") == 0])]
    scores = [t.get("proces_score") for t in trades if t.get("proces_score") is not None]
    opnieuw = [g("Zou ik opnieuw nemen", [t for t in trades if t.get("opnieuw") == 1]),
               g("Niet opnieuw", [t for t in trades if t.get("opnieuw") == 0])]
    return {
        "grade": grade, "schoon": schoon, "opnieuw": opnieuw,
        "gem_score": round(sum(scores) / len(scores)) if scores else None,
        "n_scores": len(scores),
        "n_beoordeeld": len(beoordeeld),
    }


def emoties(trades):
    per = _groepeer(trades, lambda t: (t.get("emotie_voor") or "").strip() or None)
    rijen = [_cel(k, v) for k, v in per.items()]
    return sorted(rijen, key=lambda r: -r["n"])
