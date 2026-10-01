# -*- coding: utf-8 -*-
"""
signaal_chart.py -- chart van een SIGNAAL, ook als je hem niet nam (1 okt 2026).

Zelfde stijl als de charts van gelogde trades (chart.maak_svg), getekend uit de
minuutcandles in marktdata.db: sweep, BOS, entry, en wat er daarna gebeurde
(TP of SL geraakt, of de entry nooit gevuld). Rood = risico, groen = doel.

Alleen voor signalen die 'klaar' waren (entry/SL/TP stonden vast).
"""

import os
from datetime import datetime, timedelta

HIER = os.path.dirname(os.path.abspath(__file__))
SCREENSHOTS_DIR = os.path.join(HIER, "screenshots")

NEUTRAAL = "#8a8f98"


def _dt(datum, hhmm, na=None):
    """datum + 'HH:MM' -> datetime. Valt de tijd vóór 'na', dan is het na middernacht."""
    if not hhmm or ":" not in str(hhmm):
        return None
    d = datetime.strptime(f"{datum} {str(hhmm)[:5]}", "%Y-%m-%d %H:%M")
    if na is not None and d < na:
        d += timedelta(days=1)
    return d


def _r_tekst(r):
    return f"{r:+.1f}R".replace(".", ",")


def uitkomst_tekst(row, rr):
    """Eén korte regel: wat zou er gebeurd zijn?"""
    st = row["status"]
    if st == "tp":
        return f"Had TP gepakt ({_r_tekst(rr)})"
    if st == "sl":
        return "Had SL geraakt (-1,0R)"
    if st == "onbeslist":
        return "Onbeslist: " + (row["reden"] or "TP en SL in dezelfde minuut")
    if st == "entry":
        return "Entry geraakt, trade loopt nog"
    if st == "rijp":
        return "Klaar: wacht op de entry"
    if st == "vervallen":
        reden = (row["reden"] or "").strip()
        return ("Nooit gevuld: " + reden)[:70]
    return st or ""


def chart_sleutel(row, oordeel_label=""):
    """Verandert er iets aan dit signaal dat de chart anders maakt? Dan opnieuw tekenen."""
    return "|".join(str(x) for x in (row["status"], row["entry_tijd"], row["uitkomst_tijd"],
                                     row["oordeel"], oordeel_label))


def maak_svg(row, md_pad=None, entry_max_candles=30, oordeel_label=""):
    """SVG-tekst voor één signaal-rij (sqlite3.Row), of None zonder data."""
    import chart
    import marktdata

    if row["entry"] is None or row["sl"] is None or row["tp"] is None:
        return None
    pad = md_pad or marktdata.MD_PAD
    if not os.path.exists(pad):
        return None
    datum = row["datum"]

    # tijdlijn (alles Amsterdamse tijd, 'HH:MM')
    t_tot = _dt(datum, row["impuls_tot_tijd"])
    if t_tot is None:
        return None
    t_van = _dt(datum, row["impuls_van_tijd"])
    if t_van is not None and t_van > t_tot:
        t_van -= timedelta(days=1)
    t_sweep = _dt(datum, row["sweep_tijd"], na=t_tot)
    t_bos = _dt(datum, row["bos_tijd"], na=t_sweep or t_tot)
    t_in = _dt(datum, row["entry_tijd"], na=t_bos or t_tot)
    t_uit = _dt(datum, row["uitkomst_tijd"], na=t_in or t_bos or t_tot)

    begin = (t_van or t_tot) - timedelta(minutes=25)
    if t_uit is not None:
        eind = t_uit + timedelta(minutes=10)
    elif t_in is not None:
        eind = t_in + timedelta(minutes=30)
    else:
        eind = (t_bos or t_tot) + timedelta(minutes=entry_max_candles + 5)

    md = marktdata.md_conn(pad)
    try:
        r = md.execute("SELECT symbool FROM candles_m1 GROUP BY symbool ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
        if not r:
            return None
        symbool = r[0]
        rijen = md.execute(
            "SELECT tijd_ams, o, h, l, c FROM candles_m1 WHERE symbool=? AND tijd_ams>=? AND tijd_ams<=? "
            "ORDER BY ts_utc", (symbool, begin.strftime("%Y-%m-%d %H:%M"),
                                eind.strftime("%Y-%m-%d %H:%M"))).fetchall()
    finally:
        md.close()
    if len(rijen) < 8:
        return None
    rijen = rijen[-400:]
    tijden = [x[0] for x in rijen]
    ohlc = [[x[1], x[2], x[3], x[4]] for x in rijen]

    def idx(dt):
        s = dt.strftime("%Y-%m-%d %H:%M")
        for i, x in enumerate(tijden):
            if x >= s:
                return i
        return len(tijden) - 1

    # markers: dezelfde minuut samenvoegen tot één label
    marks = {}

    def mark(dt, kleur, tekst):
        if dt is None:
            return
        i = idx(dt)
        if i in marks:
            marks[i] = (marks[i][0], marks[i][1] + " + " + tekst)
        else:
            marks[i] = (kleur, tekst)

    mark(t_sweep, NEUTRAAL, f"sweep {row['sweep_tijd']}")
    mark(t_bos, NEUTRAAL, f"BOS {row['bos_tijd']}")
    if t_in is not None:
        mark(t_in, chart.ENTRY_KLEUR, f"in {row['entry_tijd']}")
    if t_uit is not None:
        mark(t_uit, chart.TP_KLEUR if row["status"] == "tp" else chart.SL_KLEUR,
             f"uit {row['uitkomst_tijd']}")
    # labels die elkaar zouden overlappen samenvoegen tot één label (de lijn blijft staan)
    slot = 876.0 / max(1, len(ohlc))
    markers, vorige_x, einde_px = [], 0.0, -1e9
    for i, k, t in sorted((i, k, t) for i, (k, t) in marks.items()):
        px = i * slot
        if markers and px < einde_px:
            for j in range(len(markers) - 1, -1, -1):
                if markers[j][2]:
                    markers[j] = (markers[j][0], markers[j][1], markers[j][2] + " · " + t)
                    einde_px = vorige_x + len(markers[j][2]) * 6.3 + 12
                    break
            markers.append((i, k, ""))
        else:
            markers.append((i, k, t))
            vorige_x = px
            einde_px = px + len(t) * 6.3 + 12

    risico = abs(row["entry"] - row["sl"])
    rr = abs(row["tp"] - row["entry"]) / risico if risico else None
    info = uitkomst_tekst(row, rr or 1.0)
    if oordeel_label:
        info += "  ·  jij: " + oordeel_label

    exit_prijs = None
    if row["status"] == "tp":
        exit_prijs = row["tp"]
    elif row["status"] == "sl":
        exit_prijs = row["sl"]

    kop = f"{datum[5:]} {row['bos_tijd'] or row['impuls_tot_tijd']}  ·  signaal #{row['id']}"
    return chart.maak_svg(
        ohlc, entry=row["entry"], sl=row["sl"], tp=row["tp"], rr=rr,
        richting=row["trade"] or "", symbool=(symbool or "XAUUSD").rstrip("+"),
        kop_extra=kop, markers=markers, markeer_laatste=False, exit_prijs=exit_prijs,
        zone_van=idx(t_in) if t_in is not None else None,
        zone_tot=idx(t_uit) if t_uit is not None else None, info=info)


def herteken(con, sid, md_pad=None, entry_max_candles=30, oordeel_label="", force=False):
    """Tekent (indien nodig opnieuw) de chart van signaal sid en bewaart hem als
    screenshots/<datum>/signaal_<id>.svg. Geeft het relatieve pad of None."""
    row = con.execute("SELECT * FROM signalen WHERE id=?", (sid,)).fetchone()
    if row is None or row["entry"] is None:
        return None
    sleutel = chart_sleutel(row, oordeel_label)
    if not force and row["chart_pad"] and row["chart_status"] == sleutel \
            and os.path.exists(os.path.join(HIER, row["chart_pad"])):
        return row["chart_pad"]
    svg = maak_svg(row, md_pad=md_pad, entry_max_candles=entry_max_candles, oordeel_label=oordeel_label)
    if svg is None:
        return None
    rel = f"screenshots/{row['datum']}/signaal_{sid}.svg"
    os.makedirs(os.path.join(SCREENSHOTS_DIR, row["datum"]), exist_ok=True)
    with open(os.path.join(HIER, rel), "w", encoding="utf-8") as f:
        f.write(svg)
    con.execute("UPDATE signalen SET chart_pad=?, chart_status=? WHERE id=?", (rel, sleutel, sid))
    con.commit()
    return rel
