# -*- coding: utf-8 -*-
"""
trade_chart.py -- (her)teken de chart van een trade uit marktdata.db (v2.1, 29 sep 2026).

Gebruikt de minuutcandles die de journal zelf verzamelt, dus het werkt ook
achteraf: als je SL/TP later invult (Telegram of homepage), of voor oude
trades die een mooiere chart verdienen. TradingView-stijl positievak:
rood = risico (entry->SL), groen = doel (entry->TP), stippel = je exit.
"""

import os
import sqlite3
from datetime import datetime, timedelta

HIER = os.path.dirname(os.path.abspath(__file__))
SCREENSHOTS_DIR = os.path.join(HIER, "screenshots")
BESCHRIJVING = "Chart uit MetaTrader 5 (automatisch): entry, exit, SL en TP"


def _eur(v):
    return ("+" if v >= 0 else "-") + "EUR " + f"{abs(v):.2f}".replace(".", ",")


def info_tekst(t):
    netto = (t.get("resultaat_eur") or 0) + (t.get("charges") or 0)
    delen = [_eur(netto)]
    if t.get("resultaat_r") is not None:
        delen.append(f"{t['resultaat_r']:+.2f}R".replace(".", ","))
    if t.get("duur_minuten") is not None:
        delen.append(f"{t['duur_minuten']} min")
    return "  ·  ".join(delen)


def herteken(con, tid, md_pad=None, symbool=None):
    import chart
    import marktdata
    t = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
    if t is None:
        return False
    t = dict(t)
    entry = t.get("entry_prijs") or t.get("entry")
    if not entry or not t.get("datum") or not (t.get("tijd_entry") or "").count(":"):
        return False
    pad = md_pad or marktdata.MD_PAD
    if not os.path.exists(pad):
        return False
    md = marktdata.md_conn(pad)
    try:
        if not symbool:
            r = md.execute("SELECT symbool FROM candles_m1 GROUP BY symbool ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
            if not r:
                return False
            symbool = r[0]
        t_in = datetime.strptime(f"{t['datum']} {t['tijd_entry'][:5]}", "%Y-%m-%d %H:%M")
        t_uit = t_in
        if (t.get("tijd_exit") or "").count(":"):
            t_uit = datetime.strptime(f"{t['datum']} {t['tijd_exit'][:5]}", "%Y-%m-%d %H:%M")
            if t_uit < t_in:
                t_uit += timedelta(days=1)
        voor = 30 if (t_uit - t_in) > timedelta(hours=4) else 90
        rijen = md.execute(
            "SELECT tijd_ams, o, h, l, c FROM candles_m1 WHERE symbool=? AND tijd_ams>=? AND tijd_ams<=? "
            "ORDER BY ts_utc", (symbool, (t_in - timedelta(minutes=voor)).strftime("%Y-%m-%d %H:%M"),
                                (t_uit + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M"))).fetchall()
    finally:
        md.close()
    if len(rijen) < 5:
        return False
    rijen = rijen[-400:]
    tijden = [r[0] for r in rijen]
    ohlc = [[r[1], r[2], r[3], r[4]] for r in rijen]

    def idx(dt):
        s = dt.strftime("%Y-%m-%d %H:%M")
        for i, x in enumerate(tijden):
            if x >= s:
                return i
        return len(tijden) - 1

    i_in, i_uit = idx(t_in), idx(t_uit)
    sl = t.get("sl_prijs") if t.get("sl_prijs") is not None else t.get("sl")
    tp = t.get("tp_prijs") if t.get("tp_prijs") is not None else t.get("tp")
    netto = (t.get("resultaat_eur") or 0) + (t.get("charges") or 0)
    markers = [(i_in, chart.ENTRY_KLEUR, f"in {t['tijd_entry'][:5]}")]
    if t.get("tijd_exit"):
        markers.append((i_uit, chart.TP_KLEUR if netto >= 0 else chart.SL_KLEUR, f"exit {t['tijd_exit'][:5]}"))
    kop = f"{t['datum'][5:]} {t['tijd_entry'][:5]}" + (f"  ·  MT5 #{t['positie_id']}" if t.get("positie_id") else f"  ·  #{t['id']}")
    svg = chart.maak_svg(
        ohlc, entry=entry, sl=sl, tp=tp, rr=t.get("rr"), richting=t.get("richting") or "",
        symbool=(symbool or "XAUUSD").rstrip("+"), kop_extra=kop, markers=markers,
        markeer_laatste=False, exit_prijs=t.get("exit_prijs"), zone_van=i_in, zone_tot=i_uit,
        info=info_tekst(t))
    naam = f"mt5_{t['positie_id']}.svg" if t.get("positie_id") else f"trade_{t['id']}.svg"
    daydir = os.path.join(SCREENSHOTS_DIR, t["datum"])
    os.makedirs(daydir, exist_ok=True)
    with open(os.path.join(daydir, naam), "w", encoding="utf-8") as f:
        f.write(svg)
    rel = f"screenshots/{t['datum']}/{naam}"
    if not con.execute("SELECT 1 FROM screenshots WHERE trade_id=? AND pad=?", (tid, rel)).fetchone():
        con.execute("INSERT INTO screenshots (trade_id, no_trade_id, pad, beschrijving, type) "
                    "VALUES (?,?,?,?,?)", (tid, None, rel, BESCHRIJVING, "entry"))
    con.commit()
    return True


def herteken_alles(db_pad=None, md_pad=None, alleen_mt5=True):
    """Eenmalig: alle MT5-trades opnieuw tekenen in de nieuwe stijl."""
    con = sqlite3.connect(db_pad or os.path.join(HIER, "cbr_journal.db"), timeout=20)
    con.row_factory = sqlite3.Row
    n = 0
    try:
        q = "SELECT id FROM trades WHERE verwijderd_op IS NULL"
        if alleen_mt5:
            q += " AND positie_id IS NOT NULL"
        for (tid,) in con.execute(q).fetchall():
            try:
                if herteken(con, tid, md_pad):
                    n += 1
            except Exception as e:  # pragma: no cover
                print(f"[chart] #{tid}: {e}")
    finally:
        con.close()
    return n
