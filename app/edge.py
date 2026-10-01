"""
Edge-analyse (fase 5).

Beantwoordt de vraag die winrate niet beantwoordt: verdient dit model geld?

- R per trade: netto resultaat gedeeld door het risico van die trade.
- Expectancy: wat je gemiddeld per trade verdient, in R. Kosten zitten erin.
- Profit factor: bruto winst gedeeld door bruto verlies.
- Drawdown: grootste terugval van piek naar dal, en hoeveel trades herstel kostte.
- Criterium-edge: welk van de vijf criteria daadwerkelijk geld oplevert.
- Lichte MAE/MFE: hoe dicht kwam je bij je SL, en hoe liep je TP af.
"""

from . import cbr

# Beoordelingsbanden voor expectancy (in R per trade).
BANDEN = [
    (0.50, "uitstekend", "top"),
    (0.30, "solide", "goed"),
    (0.15, "marginaal", "twijfel"),
    (0.00, "nauwelijks winstgevend", "twijfel"),
    (-99.0, "verlieslatend", "slecht"),
]

# Vanaf hoeveel trades mag je iets concluderen.
N_INDICATIE = 20
N_BETROUWBAAR = 100


def _netto(t):
    return (t.get("resultaat_eur") or 0) + (t.get("charges") or 0)


def r_van_trade(t):
    """
    (R, herkomst). Herkomst: 'gemeten' (risk ingevuld), 'afgeleid' (uit RR en
    resultaat) of 'geschat' (grofste terugval).
    """
    res = t.get("resultaat_eur") or 0
    netto = _netto(t)
    # MT5 levert de echte, puntengebaseerde R aan (resultaat_r): een SL is -1,0R,
    # een handmatig gesloten trade de werkelijke afstand/SL-afstand. Dat is de
    # waarheid en houdt alle R-cijfers consistent (expectancy, equity-R, RR per
    # trade en "R laten liggen"). Alleen oudere trades zonder MT5-R vallen terug.
    if t.get("resultaat_r") is not None:
        return t["resultaat_r"], "gemeten"
    risk = t.get("risk_eur")
    if risk and risk > 0:
        return netto / risk, "gemeten"
    rr = t.get("rr")
    if res > 0 and rr:
        afgeleid_risk = res / rr          # winst / RR = wat je riskeerde
        if afgeleid_risk > 0:
            return netto / afgeleid_risk, "afgeleid"
    if res > 0:
        return float(rr or 1.0), "geschat"
    if res < 0:
        return -1.0, "geschat"
    return 0.0, "geschat"


def _band(exp_r):
    for drempel, label, kleur in BANDEN:
        if exp_r >= drempel:
            return {"label": label, "kleur": kleur, "drempel": drempel}
    return {"label": "onbekend", "kleur": "twijfel", "drempel": 0}


def _groep(trades):
    """Kerncijfers voor een set trades."""
    n = len(trades)
    if not n:
        return {"n": 0, "winrate": 0, "expectancy_r": 0.0, "netto_eur": 0.0}
    rs = [r_van_trade(t)[0] for t in trades]
    winners = [t for t in trades if (t.get("resultaat_eur") or 0) > 0]
    return {
        "n": n,
        "winrate": round(100 * len(winners) / n),
        "expectancy_r": round(sum(rs) / n, 3),
        "netto_eur": round(sum(_netto(t) for t in trades), 2),
    }


def analyse(trades, startkapitaal=0.0):
    trades = sorted(trades, key=lambda t: (t.get("datum") or "", t.get("id") or 0))
    n = len(trades)

    rs, herkomsten = [], []
    for t in trades:
        r, h = r_van_trade(t)
        rs.append(r)
        herkomsten.append(h)

    winners = [t for t in trades if (t.get("resultaat_eur") or 0) > 0]
    losers = [t for t in trades if (t.get("resultaat_eur") or 0) < 0]
    win_r = [rs[i] for i, t in enumerate(trades) if (t.get("resultaat_eur") or 0) > 0]
    loss_r = [rs[i] for i, t in enumerate(trades) if (t.get("resultaat_eur") or 0) < 0]

    expectancy_r = round(sum(rs) / n, 3) if n else 0.0
    winrate = round(100 * len(winners) / n) if n else 0

    bruto_winst = sum(_netto(t) for t in winners)
    bruto_verlies = abs(sum(_netto(t) for t in losers))
    profit_factor = round(bruto_winst / bruto_verlies, 2) if bruto_verlies > 0 else None

    # ---- Drawdown over de equity-curve ----
    equity, saldo = [], float(startkapitaal)
    for t in trades:
        saldo += _netto(t)
        equity.append(saldo)
    piek, max_dd, max_dd_pct, dd_start = float(startkapitaal), 0.0, 0.0, 0
    huidige_dd = 0.0
    herstel_trades, in_dd_sinds = None, None
    for i, e in enumerate(equity):
        if e >= piek:
            if in_dd_sinds is not None and max_dd > 0:
                herstel_trades = i - in_dd_sinds
                in_dd_sinds = None
            piek = e
        else:
            if in_dd_sinds is None:
                in_dd_sinds = i
            dd = piek - e
            if dd > max_dd:
                max_dd, dd_start = dd, i
                max_dd_pct = 100 * dd / piek if piek else 0
    if equity:
        huidige_dd = max(0.0, piek - equity[-1])

    # ---- Criterium-edge ----
    crit_edge = []
    for c in cbr.CRITERIA:
        met = [t for t in trades if t.get(c["key"]) == cbr.VAL_YES]
        zonder = [t for t in trades if t.get(c["key"]) != cbr.VAL_YES]
        g_met, g_zonder = _groep(met), _groep(zonder)
        crit_edge.append({
            "key": c["key"], "num": c["num"], "title": c["title"],
            "critical": c["critical"],
            "met": g_met, "zonder": g_zonder,
            "delta_r": round(g_met["expectancy_r"] - g_zonder["expectancy_r"], 3)
                       if met and zonder else None,
        })

    # ---- Lichte MAE/MFE ----
    def _tel(veld, waarden):
        uit = {w: {"totaal": 0, "winst": 0, "verlies": 0} for w in waarden}
        for t in trades:
            v = (t.get(veld) or "").strip()
            if v in uit:
                uit[v]["totaal"] += 1
                if (t.get("resultaat_eur") or 0) > 0:
                    uit[v]["winst"] += 1
                elif (t.get("resultaat_eur") or 0) < 0:
                    uit[v]["verlies"] += 1
        return uit

    sl_tel = _tel("sl_nabijheid", ["nooit", "halverwege", "bijna"])
    tp_tel = _tel("tp_verloop", ["precies", "liep_door", "te_vroeg"])
    n_sl = sum(v["totaal"] for v in sl_tel.values())
    n_tp = sum(v["totaal"] for v in tp_tel.values())

    signalen = []
    if n_sl >= 3:
        bijna_winst = sl_tel["bijna"]["winst"]
        if bijna_winst / max(1, len(winners)) >= 0.4:
            signalen.append("Je winnaars komen vaak bijna tot je SL. Dat wijst op een te krappe "
                            "stop of een te late entry — kijk naar R1/R2 en E7.")
    if n_tp >= 3:
        if tp_tel["liep_door"]["totaal"] / n_tp >= 0.5:
            signalen.append("De prijs liep bij de meeste trades ver door na je TP. Je laat rendement "
                            "liggen — overweeg een deel laten lopen.")
        if tp_tel["te_vroeg"]["totaal"] / n_tp >= 0.3:
            signalen.append("Je sluit regelmatig te vroeg (M1). Laat de trade tot TP of SL lopen.")

    # ---- Betrouwbaarheid ----
    if n < N_INDICATIE:
        betrouwbaar = {"niveau": "ruis", "tekst":
            f"{n} trades is te weinig om iets te concluderen. Vanaf {N_INDICATIE} krijg je een indicatie, "
            f"vanaf {N_BETROUWBAAR} mag je oordelen over het model."}
    elif n < N_BETROUWBAAR:
        betrouwbaar = {"niveau": "indicatie", "tekst":
            f"{n} trades geeft een indicatie, nog geen oordeel. Vanaf {N_BETROUWBAAR} trades wordt dit betrouwbaar."}
    else:
        betrouwbaar = {"niveau": "betrouwbaar", "tekst":
            f"{n} trades — genoeg om conclusies aan te verbinden."}

    return {
        "n_trades": n,
        "expectancy_r": expectancy_r,
        "expectancy_band": _band(expectancy_r),
        "winrate": winrate,
        "gem_winst_r": round(sum(win_r) / len(win_r), 2) if win_r else 0.0,
        "gem_verlies_r": round(sum(loss_r) / len(loss_r), 2) if loss_r else 0.0,
        "profit_factor": profit_factor,
        "bruto_winst": round(bruto_winst, 2),
        "bruto_verlies": round(bruto_verlies, 2),
        "totaal_r": round(sum(rs), 2),
        "drawdown": {
            "max_eur": round(max_dd, 2),
            "max_pct": round(max_dd_pct, 1),
            "huidig_eur": round(huidige_dd, 2),
            "herstel_trades": herstel_trades,
        },
        "datakwaliteit": {
            "gemeten": herkomsten.count("gemeten"),
            "afgeleid": herkomsten.count("afgeleid"),
            "geschat": herkomsten.count("geschat"),
        },
        "crit_edge": crit_edge,
        "sl_nabijheid": sl_tel,
        "tp_verloop": tp_tel,
        "n_sl_ingevuld": n_sl,
        "n_tp_ingevuld": n_tp,
        "signalen": signalen,
        "betrouwbaar": betrouwbaar,
    }
