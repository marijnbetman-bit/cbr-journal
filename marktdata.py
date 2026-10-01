# -*- coding: utf-8 -*-
"""
marktdata.py -- de dataset voor later (automatiseren / AI), 29 sep 2026.

Alles wat MT5 ons geeft, gestructureerd en blijvend opgeslagen:

  marktdata.db  (apart bestand, zodat de journal-db klein en snel blijft)
    candles_m1        elke minuutcandle XAU: open/high/low/close, tick-volume,
                      spread. Tijd in UTC (ts_utc) én Amsterdams (tijd_ams).
                      Bij de eerste keer ~2 maanden terug, daarna continu bij.
                      Hieruit zijn M5/M15/H1 altijd af te leiden.

  cbr_journal.db
    mt5_positie_events  tijdlijn van elke open positie: SL/TP-wijzigingen,
                        koers en zwevende winst (max 1x per minuut)
    mt5_account_log     balans/equity/margin (via app/saldo.py)
    trades (kolommen)   sessie_markt, atr_m1, spread_entry, vorige_1h_high/low

  /export/dataset.csv   één rij per trade: feiten uit MT5 + marktcontext +
                        signaalkenmerken + JOUW oordeel (grade, checklist,
                        emotie, uitvoering, opnieuw nemen). Dat is een
                        gelabelde dataset: precies wat een model nodig heeft.

LEEST alleen uit MT5. Nooit orders.
"""

import csv
import io
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone

HIER = os.path.dirname(os.path.abspath(__file__))
MD_PAD = os.path.join(HIER, "marktdata.db")
DB_PAD = os.path.join(HIER, "cbr_journal.db")
TIMEFRAME_M1 = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles_m1 (
    symbool     TEXT NOT NULL,
    ts_utc      INTEGER NOT NULL,
    tijd_ams    TEXT,
    o REAL, h REAL, l REAL, c REAL,
    tick_volume INTEGER, spread INTEGER,
    PRIMARY KEY (symbool, ts_utc)
);
"""

EVENTS = """
CREATE TABLE IF NOT EXISTS mt5_positie_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    positie_id INTEGER, ts TEXT, soort TEXT,     -- open | sl_tp | tick
    sl REAL, tp REAL, prijs REAL, winst REAL, volume REAL
);
CREATE INDEX IF NOT EXISTS idx_pos_events ON mt5_positie_events(positie_id, ts);
"""

_LAATST = {"candles": 0.0}


def md_conn(pad=None):
    con = sqlite3.connect(pad or MD_PAD, timeout=20)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _ams(utc_dt):
    import mt5_koppeling as K
    return (utc_dt + timedelta(hours=K.amsterdam_uur(utc_dt))).replace(tzinfo=None)


# ------------------------------------------------------------------ candles verzamelen

def verzamel_candles(mt5, symbool, offset_uur, pad=None, elke_sec=120, backfill=90000):
    """Wordt vanuit de MT5-thread aangeroepen. Hooguit elke 2 minuten."""
    if time.time() - _LAATST["candles"] < elke_sec:
        return 0
    _LAATST["candles"] = time.time()
    con = md_conn(pad)
    try:
        r = con.execute("SELECT MAX(ts_utc) FROM candles_m1 WHERE symbool=?", (symbool,)).fetchone()
        laatste = r[0]
        tf = getattr(mt5, "TIMEFRAME_M1", TIMEFRAME_M1)
        if laatste is None:
            rates = mt5.copy_rates_from_pos(symbool, tf, 0, backfill)
        else:
            van = datetime.fromtimestamp(laatste + offset_uur * 3600 - 120, tz=timezone.utc)
            tot = datetime.now(timezone.utc) + timedelta(days=1)
            rates = mt5.copy_rates_range(symbool, tf, van, tot)
        if rates is None:
            return 0
        rijen = []
        for x in rates:
            utc = int(x["time"]) - int(offset_uur) * 3600
            udt = datetime.fromtimestamp(utc, tz=timezone.utc)
            rijen.append((symbool, utc, _ams(udt).strftime("%Y-%m-%d %H:%M"),
                          float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"]),
                          int(x["tick_volume"]), int(x["spread"]) if "spread" in x.dtype.names else None))
        con.executemany("INSERT OR REPLACE INTO candles_m1 VALUES (?,?,?,?,?,?,?,?,?)", rijen)
        con.commit()
        return len(rijen)
    finally:
        con.close()


# ------------------------------------------------------------------ positie-tijdlijn

def log_positie(con, pid, sl, tp, prijs, winst, volume, nieuw=False):
    """SL/TP-wijziging meteen, verder max 1x per minuut een tick."""
    con.executescript(EVENTS)
    nu = datetime.now()
    vorige = con.execute("SELECT ts, sl, tp FROM mt5_positie_events WHERE positie_id=? "
                         "ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
    if vorige is None or nieuw:
        soort = "open"
    elif (vorige[1], vorige[2]) != (sl, tp):
        soort = "sl_tp"
    elif (nu - datetime.fromisoformat(vorige[0])).total_seconds() >= 60:
        soort = "tick"
    else:
        return
    con.execute("INSERT INTO mt5_positie_events (positie_id, ts, soort, sl, tp, prijs, winst, volume) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (pid, nu.isoformat(timespec="seconds"), soort, sl, tp, prijs, winst, volume))


# ------------------------------------------------------------------ kenmerken per trade

def _candles_rond(md, symbool, eind_ams, minuten):
    begin = (datetime.strptime(eind_ams, "%Y-%m-%d %H:%M") - timedelta(minutes=minuten)).strftime("%Y-%m-%d %H:%M")
    return md.execute("SELECT * FROM candles_m1 WHERE symbool=? AND tijd_ams>=? AND tijd_ams<? "
                      "ORDER BY ts_utc", (symbool, begin, eind_ams)).fetchall()


def kenmerken(md, symbool, datum, tijd):
    """ATR(14) op M1 vlak voor entry, spread, en de high/low van het vorige
    volle uur (jouw 1H-breekregel)."""
    if not (datum and tijd and ":" in tijd):
        return {}
    eind = f"{datum} {tijd[:5]}"
    c = _candles_rond(md, symbool, eind, 15)
    uit = {}
    if len(c) >= 2:
        trs = []
        for i in range(1, len(c)):
            trs.append(max(c[i]["h"] - c[i]["l"], abs(c[i]["h"] - c[i - 1]["c"]),
                           abs(c[i]["l"] - c[i - 1]["c"])))
        uit["atr_m1"] = round(sum(trs[-14:]) / len(trs[-14:]) / 0.10, 1)  # in points
        if c[-1]["spread"] is not None:
            uit["spread_entry"] = c[-1]["spread"]
    t = datetime.strptime(eind, "%Y-%m-%d %H:%M")
    uur_start = t.replace(minute=0)
    vorige = md.execute(
        "SELECT MAX(h), MIN(l), COUNT(*) FROM candles_m1 WHERE symbool=? AND tijd_ams>=? AND tijd_ams<?",
        (symbool, (uur_start - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"),
         uur_start.strftime("%Y-%m-%d %H:%M"))).fetchone()
    if vorige and vorige[2]:
        uit["vorige_1h_high"], uit["vorige_1h_low"] = vorige[0], vorige[1]
    return uit


def verrijk_trades(symbool="XAUUSD+", pad=None, md_pad=None, alleen_nieuw=True):
    """Vul de contextkolommen van trades die ze nog niet hebben."""
    from app import prestaties, saldo
    if not os.path.exists(md_pad or MD_PAD):
        return 0
    con = sqlite3.connect(pad or DB_PAD, timeout=20)
    con.row_factory = sqlite3.Row
    md = md_conn(md_pad)
    n = 0
    try:
        saldo.zorg_trade_kolommen(con)
        q = "SELECT id, datum, tijd_entry FROM trades WHERE verwijderd_op IS NULL"
        if alleen_nieuw:
            q += " AND (atr_m1 IS NULL OR sessie_markt IS NULL)"
        for t in con.execute(q).fetchall():
            zet = {"sessie_markt": prestaties.sessie_van(t["tijd_entry"])}
            zet.update(kenmerken(md, symbool, t["datum"], t["tijd_entry"]))
            zet = {k: v for k, v in zet.items() if v is not None}
            if zet:
                con.execute("UPDATE trades SET " + ", ".join(f"{k}=?" for k in zet) +
                            " WHERE id=?", list(zet.values()) + [t["id"]])
                n += 1
        con.commit()
    finally:
        con.close()
        md.close()
    return n


# ------------------------------------------------------------------ export

DATASET_KOLOMMEN = [
    "id", "datum", "tijd_entry", "tijd_exit", "richting", "lot", "entry_prijs", "exit_prijs",
    "sl_prijs", "tp_prijs", "sl_afstand_points", "tp_afstand_points", "rr", "resultaat_eur",
    "charges", "resultaat_r", "exit_reden", "duur_minuten", "mfe_points", "mae_points",
    "minuut_in_uur", "sessie_markt", "atr_m1", "spread_entry", "vorige_1h_high", "vorige_1h_low",
    "model", "grade", "schoon", "proces_score", "s_impuls", "s_top", "s_sweep", "s_bos",
    "f2_entry", "f2_sl", "f2_tp", "check_venster", "check_dagmax", "check_sl_vast",
    "check_beheer", "emotie_voor", "uitvoering", "opnieuw", "foutcodes", "les",
    "signaal_id", "positie_id",
]
SIGNAAL_KOLOMMEN = ["impuls_richting", "impuls_candles", "kracht", "overlap", "efficientie",
                    "top", "pullback", "sweep", "risico_points", "in_venster", "status"]


def dataset_csv(pad=None):
    con = sqlite3.connect(pad or DB_PAD, timeout=20)
    con.row_factory = sqlite3.Row
    try:
        heeft_sig = con.execute("SELECT 1 FROM sqlite_master WHERE name='signalen'").fetchone()
        kol = {r[1] for r in con.execute("PRAGMA table_info(trades)")}
        cols = [c for c in DATASET_KOLOMMEN if c in kol]
        rijen = con.execute("SELECT " + ", ".join(cols) + " FROM trades WHERE verwijderd_op IS NULL "
                            "AND status='genomen' AND fase=2 ORDER BY datum, tijd_entry, id").fetchall()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols + ["netto_eur", "winst"] + ["sig_" + c for c in SIGNAAL_KOLOMMEN])
        for r in rijen:
            d = dict(r)
            netto = round((d.get("resultaat_eur") or 0) + (d.get("charges") or 0), 2)
            sig = [None] * len(SIGNAAL_KOLOMMEN)
            if heeft_sig and d.get("signaal_id"):
                s = con.execute("SELECT * FROM signalen WHERE id=?", (d["signaal_id"],)).fetchone()
                if s:
                    sig = [s[c] if c in s.keys() else None for c in SIGNAAL_KOLOMMEN]
            w.writerow([d.get(c) for c in cols] + [netto, 1 if netto > 0 else 0] + sig)
        return buf.getvalue()
    finally:
        con.close()


def status(md_pad=None):
    p = md_pad or MD_PAD
    if not os.path.exists(p):
        return {"candles": 0}
    con = md_conn(p)
    try:
        r = con.execute("SELECT COUNT(*), MIN(tijd_ams), MAX(tijd_ams) FROM candles_m1").fetchone()
        return {"candles": r[0], "van": r[1], "tot": r[2],
                "mb": round(os.path.getsize(p) / 1e6, 1)}
    finally:
        con.close()
