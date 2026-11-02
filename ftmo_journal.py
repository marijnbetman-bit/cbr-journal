# -*- coding: utf-8 -*-
"""FTMO 1-Step in het journal (Marijn, 2 nov 2026: 'ja, in het journal'; ook eigen trades op FTMO; eigen pagina).

Los van de gewone journal: eigen tabellen (ftmo_*), eigen pagina /ftmo. Je live-trades (1705040), edge, proces en game mode
blijven zoals ze waren. Bot of zelf: magic number (CBR Station FTMO-bot = 26217021, met de hand = 0).

Alleen LEZEN: account_info, history_deals_get, history_orders_get, positions_get. Nooit een order.
Het uitlezen gebeurt in een APART proces (python ftmo_journal.py --lees), omdat één Python-proces maar met één MT5-terminal
tegelijk kan praten en de journal-koppeling op de live-terminal moet blijven zitten.
Alleen account 511465222 op FTMO-Server; anders wordt er niets opgeslagen.

R = RR: koersbeweging / afstand tot de eerste SL (zoals de rest van het journal). Zonder SL: geen R (niet geschat).
FTMO-grenzen (controleer ze in je FTMO-dashboard): max dagverlies 3% van het startkapitaal, gemeten vanaf de stand om
00:00 Amsterdamse tijd (inclusief open posities); max verlies 10%.
"""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

try:
    from fastapi import APIRouter
except Exception:                                   # pragma: no cover (tests zonder fastapi)
    APIRouter = None

import mt5_koppeling as mk

FTMO_LOGIN = 511465222
FTMO_SERVER = "FTMO-Server"
TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
MAGIC_BOT = 26217021
STARTKAPITAAL = 10000.0
DAG_PCT, MAX_PCT = 3.0, 10.0
VANAF = datetime(2026, 11, 1)                       # het account bestaat sinds 2 nov 2026
INTERVAL_S = 60


# ------------------------------------------------------------------ uitlezen (apart proces)

def _naar_dict(x, velden):
    return {k: getattr(x, k, None) for k in velden}


def lees_mt5(mt5, pad=TERMINAL, nu=time.time):
    """Alles wat het journal over FTMO nodig heeft, als dict. Alleen lezen."""
    if not mt5.initialize(pad):
        return {"ok": False, "fout": "FTMO-terminal niet bereikbaar (%s)" % (mt5.last_error(),)}
    try:
        acc = mt5.account_info()
        if acc is None:
            return {"ok": False, "fout": "geen account ingelogd in de FTMO-terminal"}
        if int(acc.login) != FTMO_LOGIN or str(acc.server) != FTMO_SERVER:
            return {"ok": False, "fout": "ander account in de FTMO-terminal (...%s, %s): niets gelezen" % (str(acc.login)[-3:], acc.server)}
        offset = None
        try:
            mt5.symbol_select("XAUUSD", True)
            t = mt5.symbol_info_tick("XAUUSD")
            offset = mk.detecteer_offset(getattr(t, "time", 0), nu()) if t is not None else None
        except Exception:
            offset = None
        if offset is None:                         # markt dicht: FTMO-servertijd = Amsterdam + 1
            offset = mk.amsterdam_uur(datetime.now(timezone.utc)) + 1
        tot = datetime.fromtimestamp(nu() + 3 * 86400)
        deals = [dict(mk._deal_dict(d), magic=getattr(d, "magic", 0)) for d in (mt5.history_deals_get(VANAF, tot) or [])]
        orders = {}
        for o in (mt5.history_orders_get(VANAF, tot) or []):
            orders[int(o.ticket)] = _naar_dict(o, ("ticket", "sl", "tp", "magic", "type", "price_open", "position_id"))
        posities = [_naar_dict(p, ("ticket", "type", "volume", "price_open", "sl", "tp", "profit", "magic", "time", "symbol"))
                    for p in (mt5.positions_get() or [])]
        return {"ok": True, "offset": int(offset), "acc": {"login": int(acc.login), "server": acc.server, "balans": float(acc.balance),
                "equity": float(acc.equity), "valuta": acc.currency}, "deals": deals, "orders": orders, "posities": posities}
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass


def lees_apart(timeout=90):
    """Start 'python ftmo_journal.py --lees' en geeft de dict terug."""
    vlag = 0x08000000 if os.name == "nt" else 0         # CREATE_NO_WINDOW
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--lees"], capture_output=True, text=True,
                       timeout=timeout, creationflags=vlag, cwd=os.path.dirname(os.path.abspath(__file__)))
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"ok": False, "fout": "uitlezen mislukt: %s" % ((r.stderr or r.stdout or "").strip()[-200:] or "geen uitvoer")}


# ------------------------------------------------------------------ opslaan

SCHEMA = """
CREATE TABLE IF NOT EXISTS ftmo_trades (
    positie_id INTEGER PRIMARY KEY, bron TEXT, magic INTEGER, symbool TEXT, richting TEXT, lot REAL,
    open_utc INTEGER, dicht_utc INTEGER, datum TEXT, tijd TEXT, entry REAL, exit REAL, sl REAL, tp REAL,
    bruto REAL, kosten REAL, netto REAL, r REAL, reden TEXT, bijgewerkt TEXT);
CREATE TABLE IF NOT EXISTS ftmo_gezien (
    positie_id INTEGER PRIMARY KEY, eerste_sl REAL, eerste_tp REAL, laatste_sl REAL, laatste_tp REAL);
CREATE TABLE IF NOT EXISTS ftmo_dag (datum TEXT PRIMARY KEY, start_balans REAL, start_equity REAL, ts TEXT);
CREATE TABLE IF NOT EXISTS ftmo_stand (ts_utc INTEGER PRIMARY KEY, balans REAL, equity REAL, open_n INTEGER);
"""
REDEN = {0: "met de hand", 1: "mobiel", 2: "web", 3: "bot", 4: "SL", 5: "TP", 6: "stop-out"}


def zorg_schema(con):
    con.executescript(SCHEMA)
    con.commit()


def bron_van(magic):
    return "bot" if int(magic or 0) == MAGIC_BOT else ("zelf" if not magic else "anders")


def _ams(utc_ts):
    utc = datetime.fromtimestamp(int(utc_ts), tz=timezone.utc)
    return (utc + timedelta(hours=mk.amsterdam_uur(utc))).replace(tzinfo=None)


def r_van(richting, entry, exit_, sl):
    if None in (entry, exit_, sl) or abs(entry - sl) < 1e-9:
        return None
    teken = 1 if richting == "long" else -1
    return round(teken * (exit_ - entry) / abs(entry - sl), 2)


def verwerk(con, data, nu=time.time):
    """Slaat één uitlezing op. Geeft {'nieuw': n, 'open': n}."""
    zorg_schema(con)
    off = int(data["offset"]) * 3600
    # eerste en laatste SL/TP die we op open posities zien (je kunt een SL later verschuiven; R hoort bij de eerste)
    for p in data["posities"]:
        pid = int(p["ticket"])
        rij = con.execute("SELECT eerste_sl, eerste_tp FROM ftmo_gezien WHERE positie_id=?", (pid,)).fetchone()
        sl, tp = (p.get("sl") or None), (p.get("tp") or None)
        if rij is None:
            con.execute("INSERT INTO ftmo_gezien VALUES(?,?,?,?,?)", (pid, sl, tp, sl, tp))
        else:
            con.execute("UPDATE ftmo_gezien SET eerste_sl=COALESCE(eerste_sl, ?), eerste_tp=COALESCE(eerste_tp, ?), laatste_sl=?, laatste_tp=? "
                        "WHERE positie_id=?", (sl, tp, sl, tp, pid))
    nieuw = 0
    magic_per_pos = {}
    for d in data["deals"]:
        if d.get("entry") == mk.ENTRY_IN and d.get("position_id"):
            magic_per_pos.setdefault(int(d["position_id"]), d.get("magic") or 0)
    orders = {int(k): v for k, v in (data.get("orders") or {}).items()}
    for pid, pos in mk.groepeer(data["deals"]).items():
        if not pos["gesloten"]:
            continue
        g = con.execute("SELECT eerste_sl, eerste_tp, laatste_sl, laatste_tp FROM ftmo_gezien WHERE positie_id=?", (pid,)).fetchone()
        gezien = {"eerste_sl": g[0], "eerste_tp": g[1], "laatste_sl": g[2], "laatste_tp": g[3]} if g else {}
        o = orders.get(int(pos.get("order_id") or 0)) or {}
        sl, tp = mk.bepaal_niveaus(pos, o.get("sl"), o.get("tp"), gezien)
        open_utc, dicht_utc = pos["open_ts"] - off, pos["dicht_ts"] - off
        a = _ams(open_utc)
        magic = magic_per_pos.get(int(pid), o.get("magic") or 0)
        bestond = con.execute("SELECT 1 FROM ftmo_trades WHERE positie_id=?", (pid,)).fetchone()
        con.execute("INSERT OR REPLACE INTO ftmo_trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            int(pid), bron_van(magic), int(magic or 0), pos["symbool"], pos["richting"], pos["lot"], open_utc, dicht_utc,
            a.strftime("%Y-%m-%d"), a.strftime("%H:%M"), pos["entry"], pos["exit"], sl, tp, pos["bruto"], pos["charges"], pos["netto"],
            r_van(pos["richting"], pos["entry"], pos["exit"], sl), REDEN.get(pos.get("reden"), str(pos.get("reden"))),
            datetime.now().isoformat(timespec="seconds")))
        nieuw += 0 if bestond else 1
    acc = data["acc"]
    vandaag = _ams(nu()).strftime("%Y-%m-%d")
    if not con.execute("SELECT 1 FROM ftmo_dag WHERE datum=?", (vandaag,)).fetchone():
        # eerste ronde van de dag: de stand van 00:00 = nu min wat er vandaag al gesloten is (bij een start halverwege de dag)
        al = sum(r[1] or 0 for r in con.execute("SELECT dicht_utc, netto FROM ftmo_trades WHERE dicht_utc IS NOT NULL")
                 if _ams(r[0]).strftime("%Y-%m-%d") == vandaag)
        start = round(acc["balans"] - float(al), 2)
        con.execute("INSERT INTO ftmo_dag VALUES(?,?,?,?)", (vandaag, start, start, datetime.now().isoformat(timespec="seconds")))
    t = int(nu()) // 300 * 300                           # één stand per 5 minuten
    con.execute("INSERT OR REPLACE INTO ftmo_stand VALUES(?,?,?,?)", (t, acc["balans"], acc["equity"], len(data["posities"])))
    con.commit()
    return {"nieuw": nieuw, "open": len(data["posities"])}


# ------------------------------------------------------------------ samenvatting voor de pagina

def _telling(rijen):
    r = [x["r"] for x in rijen if x["r"] is not None]
    win = [x for x in rijen if (x["netto"] or 0) > 0]
    return {"n": len(rijen), "winst_pct": round(100.0 * len(win) / len(rijen)) if rijen else None,
            "r_som": round(sum(r), 2) if r else 0.0, "r_gem": round(sum(r) / len(r), 2) if r else None, "n_met_r": len(r),
            "marge": round(1.96 * (sum((x - sum(r) / len(r)) ** 2 for x in r) / (len(r) - 1)) ** 0.5 / len(r) ** 0.5, 2) if len(r) > 1 else None,
            "netto": round(sum(x["netto"] or 0 for x in rijen), 2)}


def samenvatting(con, status=None, nu=time.time):
    zorg_schema(con)
    con.row_factory = __import__("sqlite3").Row
    trades = [dict(r) for r in con.execute("SELECT * FROM ftmo_trades ORDER BY dicht_utc DESC")]
    stand = con.execute("SELECT * FROM ftmo_stand ORDER BY ts_utc DESC LIMIT 1").fetchone()
    vandaag = _ams(nu()).strftime("%Y-%m-%d")
    dag = con.execute("SELECT * FROM ftmo_dag WHERE datum=?", (vandaag,)).fetchone()
    uit = {"status": status or {}, "account": {"login": "...%s" % str(FTMO_LOGIN)[-4:], "server": FTMO_SERVER, "startkapitaal": STARTKAPITAAL},
           "per_bron": {b: _telling([t for t in trades if t["bron"] == b]) for b in ("bot", "zelf")},
           "trades": trades[:300]}
    uit["per_bron"]["alles"] = _telling(trades)
    if stand:
        balans, equity = stand["balans"], stand["equity"]
        uit["stand"] = {"balans": balans, "equity": equity, "open_n": stand["open_n"],
                        "ts": datetime.fromtimestamp(stand["ts_utc"]).strftime("%d-%m %H:%M")}
        grens_dag = STARTKAPITAAL * DAG_PCT / 100.0
        if dag:
            verlies = round(max(0.0, dag["start_balans"] - equity), 2)
            uit["vandaag"] = {"datum": vandaag, "start": dag["start_balans"], "verlies": verlies, "grens": grens_dag,
                              "ruimte": round(grens_dag - verlies, 2), "pct": round(100.0 * verlies / grens_dag, 1),
                              "trades": _telling([t for t in trades if t["datum"] == vandaag])}
        vloer = STARTKAPITAAL * (1 - MAX_PCT / 100.0)
        uit["totaal"] = {"winst": round(balans - STARTKAPITAAL, 2), "winst_pct": round(100.0 * (balans - STARTKAPITAAL) / STARTKAPITAAL, 2),
                         "vloer": vloer, "ruimte": round(equity - vloer, 2)}
    kromme, saldo = [], STARTKAPITAAL
    for t in sorted(trades, key=lambda x: x["dicht_utc"] or 0):
        saldo += t["netto"] or 0
        kromme.append([t["datum"], round(saldo, 2), t["bron"]])
    uit["kromme"] = kromme
    return uit


# ------------------------------------------------------------------ achtergrond in het journal

_STATUS = {"laatste": None, "fout": None, "nieuw": 0}
_GESTART = False


def ronde(db_pad=None):
    data = lees_apart()
    if not data.get("ok"):
        _STATUS.update(fout=data.get("fout"), laatste=datetime.now().strftime("%H:%M:%S"))
        return _STATUS
    con = mk.verbind_db(db_pad)
    try:
        uit = verwerk(con, data)
    finally:
        con.close()
    _STATUS.update(fout=None, laatste=datetime.now().strftime("%H:%M:%S"), nieuw=_STATUS["nieuw"] + uit["nieuw"], open=uit["open"])
    if uit["nieuw"]:
        mk.log("FTMO: %d nieuwe gesloten trade(s) opgeslagen" % uit["nieuw"])
    return _STATUS


def _loop():
    time.sleep(10)
    while True:
        try:
            ronde()
        except Exception as e:                      # nooit de journal laten vallen
            _STATUS.update(fout="fout: %s" % e, laatste=datetime.now().strftime("%H:%M:%S"))
        time.sleep(INTERVAL_S)


def start_achtergrond():
    """Eén keer vanuit app/main.py. CBR_GEEN_MT5=1 zet hem uit (tests)."""
    global _GESTART
    if _GESTART or os.environ.get("CBR_GEEN_MT5"):
        return
    _GESTART = True
    threading.Thread(target=_loop, name="ftmo-journal", daemon=True).start()


if APIRouter is not None:
    router = APIRouter()

    @router.get("/api/ftmo")
    def api_ftmo():
        con = mk.verbind_db()
        try:
            return samenvatting(con, dict(_STATUS))
        finally:
            con.close()


if __name__ == "__main__" and "--lees" in sys.argv:
    try:
        import MetaTrader5 as _mt5
        print(json.dumps(lees_mt5(_mt5)))
    except Exception as e:
        print(json.dumps({"ok": False, "fout": "%s: %s" % (type(e).__name__, e)}))
