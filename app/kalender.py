"""
Kalender-heatmap (fase 10.1).

Een maandrooster van handelsdagen, gekleurd naar netto R, met een ster bij een
perfecte setup en een schild bij een bewust overgeslagen setup. Daaronder een
jaarstrook: twaalf maanden naast elkaar.

De R-berekening komt uit edge.py, zodat de kalender nooit iets anders zegt dan
het dashboard.
"""

import calendar
from datetime import date

from . import edge

DAGNAMEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
MAANDNAMEN = ["jan", "feb", "mrt", "apr", "mei", "jun",
              "jul", "aug", "sep", "okt", "nov", "dec"]
MAANDNAMEN_VOL = ["januari", "februari", "maart", "april", "mei", "juni",
                  "juli", "augustus", "september", "oktober", "november", "december"]


def _leeg_dag(d: str):
    return {
        "datum": d,
        "n": 0,
        "netto_eur": 0.0,
        "netto_r": 0.0,
        "n_a": 0,
        "n_c": 0,
        "n_overgeslagen": 0,
        "n_no_trades": 0,
        "win": 0,
        "verlies": 0,
    }


def _vul(dagen, trades, overgeslagen, no_trades):
    for t in trades:
        d = t.get("datum")
        if not d:
            continue
        cel = dagen.setdefault(d, _leeg_dag(d))
        cel["n"] += 1
        netto = (t.get("resultaat_eur") or 0) + (t.get("charges") or 0)
        cel["netto_eur"] += netto
        cel["netto_r"] += edge.r_van_trade(t)[0]
        if t.get("grade") == "A":
            cel["n_a"] += 1
        if t.get("grade") == "C":
            cel["n_c"] += 1
        if netto > 0:
            cel["win"] += 1
        elif netto < 0:
            cel["verlies"] += 1

    for t in overgeslagen:
        d = t.get("datum")
        if d:
            dagen.setdefault(d, _leeg_dag(d))["n_overgeslagen"] += 1

    for nt in no_trades:
        d = nt.get("datum")
        if d:
            dagen.setdefault(d, _leeg_dag(d))["n_no_trades"] += 1

    for cel in dagen.values():
        cel["netto_eur"] = round(cel["netto_eur"], 2)
        cel["netto_r"] = round(cel["netto_r"], 2)
    return dagen


def maand(jaar: int, mnd: int, trades, overgeslagen, no_trades):
    """Rooster voor één maand: weken van maandag t/m zondag."""
    prefix = f"{jaar:04d}-{mnd:02d}"

    def _deze_maand(rij):
        return [x for x in rij if (x.get("datum") or "").startswith(prefix)]

    trades = _deze_maand(trades)
    overgeslagen = _deze_maand(overgeslagen)
    no_trades = _deze_maand(no_trades)
    dagen = _vul({}, trades, overgeslagen, no_trades)

    cal = calendar.Calendar(firstweekday=0)   # maandag
    weken = []
    for week in cal.monthdatescalendar(jaar, mnd):
        rij = []
        for d in week:
            iso = d.isoformat()
            cel = dagen.get(iso)
            rij.append({
                "datum": iso,
                "dag": d.day,
                "buiten": d.month != mnd,
                "weekend": d.weekday() >= 5,
                "data": cel,
            })
        weken.append(rij)

    actief = [c for c in dagen.values() if c["n"]]
    tot_r = round(sum(edge.r_van_trade(t)[0] for t in trades), 2)
    tot_eur = round(sum((t.get("resultaat_eur") or 0) + (t.get("charges") or 0)
                        for t in trades), 2)
    max_abs_r = max([abs(c["netto_r"]) for c in actief], default=0) or 1.0

    return {
        "jaar": jaar,
        "maand": mnd,
        "maandnaam": MAANDNAMEN_VOL[mnd - 1],
        "dagnamen": DAGNAMEN,
        "weken": weken,
        "schaal_r": round(max_abs_r, 2),
        "totaal": {
            "handelsdagen": len(actief),
            "trades": sum(c["n"] for c in actief),
            "netto_eur": tot_eur,
            "netto_r": tot_r,
            "groene_dagen": sum(1 for c in actief if c["netto_eur"] > 0),
            "rode_dagen": sum(1 for c in actief if c["netto_eur"] < 0),
            "perfecte": sum(c["n_a"] for c in actief),
            "overgeslagen": sum(c["n_overgeslagen"] for c in dagen.values()),
        },
    }


def jaarstrook(jaar: int, trades, overgeslagen):
    """Twaalf maanden: netto R en netto €, plus aantal trades."""
    per = {m: {"maand": m, "naam": MAANDNAMEN[m - 1], "n": 0,
               "netto_eur": 0.0, "netto_r": 0.0, "n_a": 0} for m in range(1, 13)}
    for t in trades:
        d = t.get("datum") or ""
        try:
            dt = date.fromisoformat(d)
        except ValueError:
            continue
        if dt.year != jaar:
            continue
        cel = per[dt.month]
        cel["n"] += 1
        cel["netto_eur"] += (t.get("resultaat_eur") or 0) + (t.get("charges") or 0)
        cel["netto_r"] += edge.r_van_trade(t)[0]
        if t.get("grade") == "A":
            cel["n_a"] += 1
    lijst = []
    for m in range(1, 13):
        c = per[m]
        c["netto_eur"] = round(c["netto_eur"], 2)
        c["netto_r"] = round(c["netto_r"], 2)
        lijst.append(c)
    schaal = max([abs(c["netto_r"]) for c in lijst], default=0) or 1.0
    return {"jaar": jaar, "maanden": lijst, "schaal_r": round(schaal, 2)}
