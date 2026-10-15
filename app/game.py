# -*- coding: utf-8 -*-
"""Game mode (journal v2, 15 okt 2026). Dezelfde informatie als het overzicht, in de stijl van de CBR Station-game, met
filters, groeperen, trade-replay en de vergelijking met de bots. Alleen lezen: deze module schrijft niets in het journal.

    GET /api/game/trades          per trade alles wat je wilt filteren of groeperen (fase 2, live, genomen), incl. trade-beheer uit MT5
    GET /api/game/account         MT5-balans en equity door de tijd (mt5_account_log)
    GET /api/game/replay/{id}     candles rond een trade + het verloop van de positie (SL/TP-wijzigingen, winst per minuut)
    GET /api/game/station/{naam}  doorgeefluik naar CBR Station (teams, vergelijk, doelen); leeg als het station niet draait
"""
import json
import os
import sqlite3
import urllib.request
from datetime import datetime

from fastapi import APIRouter

from . import db, edge

router = APIRouter()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKT_DB = os.path.join(BASE_DIR, "marktdata.db")
STATION = os.environ.get("CBR_STATION_URL", "http://127.0.0.1:8020")
POINT = 0.1                                   # 1 point = 0,10 in de koers (zoals sl_afstand_points)
WD = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]


def _beheer(events, t):
    """Trade-beheer uit de MT5-events van één positie: SL naar break-even (wanneer), SL/TP verplaatst, R-verloop per minuut."""
    if not events:
        return {}
    entry, sl0 = t.get("entry_prijs"), t.get("sl_prijs")
    short = t.get("richting") == "short"
    open_ts = events[0]["ts"]
    uit = {"sl_moves": 0, "tp_moves": 0, "be_min": None, "sl_verruimd": 0, "pad": []}
    vorige = events[0]
    risico = abs(entry - sl0) if entry and sl0 else None
    for e in events:
        try:
            m = (datetime.fromisoformat(e["ts"]) - datetime.fromisoformat(open_ts)).total_seconds() / 60
        except (TypeError, ValueError):
            m = None
        if e["soort"] == "sl_tp" and e is not vorige:
            if e["sl"] is not None and vorige["sl"] is not None and abs(e["sl"] - vorige["sl"]) > 0.05:
                uit["sl_moves"] += 1
                if entry and abs(e["sl"] - entry) > abs(vorige["sl"] - entry) + 0.05:
                    uit["sl_verruimd"] += 1                          # SL verder van de entry gezet: meer risico dan gepland
                if uit["be_min"] is None and entry and ((e["sl"] <= entry + 0.3) if short else (e["sl"] >= entry - 0.3)):
                    uit["be_min"] = round(m, 1) if m is not None else None
            if e["tp"] is not None and vorige["tp"] is not None and abs(e["tp"] - vorige["tp"]) > 0.05:
                uit["tp_moves"] += 1
        if risico and e["prijs"] is not None and m is not None:
            r = ((entry - e["prijs"]) if short else (e["prijs"] - entry)) / risico
            uit["pad"].append([round(m, 1), round(r, 2)])
        vorige = e
    return uit


def _trades(conn):
    q = ("SELECT * FROM trades WHERE status='genomen' AND verwijderd_op IS NULL AND fase=2 "
         "AND (bron IS NULL OR bron='live') ORDER BY datum, tijd_entry, id")
    rijen = [dict(r) for r in conn.execute(q).fetchall()]
    events = {}
    try:
        for e in conn.execute("SELECT positie_id, ts, soort, sl, tp, prijs, winst FROM mt5_positie_events ORDER BY positie_id, ts, id"):
            events.setdefault(e["positie_id"], []).append(dict(e))
    except sqlite3.Error:
        pass
    shots = {}
    try:
        for s in conn.execute("SELECT trade_id, pad FROM screenshots WHERE trade_id IS NOT NULL ORDER BY id"):
            shots.setdefault(s["trade_id"], "/" + s["pad"].replace("\\", "/").lstrip("/"))
    except sqlite3.Error:
        pass
    uit = []
    for t in rijen:
        r, herkomst = edge.r_van_trade(t)
        netto = edge._netto(t)
        tijd = (t.get("tijd_entry") or "").strip()
        try:                                                     # oude trades staan soms als '7:05' in plaats van '07:05'
            uur, minuut = (int(x) for x in tijd.split(":")[:2])
            tijd = "%02d:%02d" % (uur, minuut)
        except ValueError:
            uur, tijd = None, tijd[:5]
        slp = t.get("sl_afstand_points")
        b = _beheer(events.get(t.get("positie_id")), t)
        try:
            fouten = json.loads(t.get("foutcodes") or "[]") if str(t.get("foutcodes") or "").startswith("[") else \
                [f for f in str(t.get("foutcodes") or "").split(",") if f.strip()]
        except ValueError:
            fouten = []
        exit_ = (t.get("exit_reden") or "").lower()
        uit.append({
            "id": t["id"], "datum": t["datum"], "tijd": tijd, "tijd_exit": t.get("tijd_exit"), "uur": uur,
            "weekdag": WD[datetime.strptime(t["datum"], "%Y-%m-%d").weekday()],
            "maand": t["datum"][:7], "sessie": t.get("sessie_markt") or t.get("sessie") or "-",
            "richting": t.get("richting") or "-", "grade": t.get("grade") or "?",
            "r": round(r, 2), "r_herkomst": herkomst, "netto": round(netto, 2), "kosten": t.get("charges"),
            "emotie": t.get("emotie_voor") or "-", "schoon": t.get("schoon"), "proces": t.get("proces_score"),
            "uitvoering": t.get("uitvoering"), "opnieuw": t.get("opnieuw"),
            "tp_type": t.get("tp_type") or "-", "exit": "TP" if "tp" in exit_ else "SL" if "sl" in exit_ else "handmatig" if "hand" in exit_ else (exit_ or "-"),
            "exit_reden": t.get("exit_reden"), "duur": t.get("duur_minuten"), "lot": t.get("lot"),
            "sl_points": slp, "rr": t.get("rr"),
            "mfe_r": round(t["mfe_points"] / slp, 2) if t.get("mfe_points") is not None and slp else None,
            "mae_r": round(t["mae_points"] / slp, 2) if t.get("mae_points") is not None and slp else None,
            "fouten": fouten, "les": t.get("les"), "v3_sleutel": t.get("v3_sleutel"), "signaal": bool(t.get("signaal_id")),
            "beoordeeld": t.get("beoordeeld"), "chart": shots.get(t["id"]),
            "sl_moves": b.get("sl_moves"), "tp_moves": b.get("tp_moves"), "be_min": b.get("be_min"), "sl_verruimd": b.get("sl_verruimd"),
            "entry": t.get("entry_prijs"), "sl": t.get("sl_prijs"), "tp": t.get("tp_prijs"), "exit_prijs": t.get("exit_prijs"),
        })
    return uit


@router.get("/api/game/trades")
def api_trades():
    with db.get_conn() as conn:
        trades = _trades(conn)
        kas = [dict(r) for r in conn.execute("SELECT datum, tijd, soort, bedrag FROM kasstromen ORDER BY datum, tijd").fetchall()]
        s = db.get_settings(conn)
    return {"trades": trades, "kasstromen": kas, "startkapitaal": float(s.get("startkapitaal") or 0),
            "max_trades_dag": s.get("max_trades_dag"), "venster": [s.get("venster_van"), s.get("venster_tot")]}


@router.get("/api/game/account")
def api_account(dagen: int = 30):
    with db.get_conn() as conn:
        rijen = conn.execute("SELECT ts, balance, equity FROM mt5_account_log WHERE ts >= date('now', ?) ORDER BY ts",
                             ("-%d day" % max(1, min(dagen, 365)),)).fetchall()
    return {"punten": [[r["ts"], r["balance"], r["equity"]] for r in rijen]}


@router.get("/api/game/replay/{tid}")
def api_replay(tid: int, voor: int = 45, na: int = 20):
    with db.get_conn() as conn:
        t = conn.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
        if not t:
            return {"error": "trade %d bestaat niet" % tid}
        t = dict(t)
        ev = [dict(e) for e in conn.execute("SELECT ts, soort, sl, tp, prijs, winst FROM mt5_positie_events WHERE positie_id=? ORDER BY ts, id",
                                            (t.get("positie_id"),))] if t.get("positie_id") else []
    candles = []
    if os.path.exists(MARKT_DB):
        try:
            start = datetime.strptime("%s %s" % (t["datum"], (t.get("tijd_entry") or "00:00")[:5]), "%Y-%m-%d %H:%M")
            eind = datetime.strptime("%s %s" % (t["datum"], (t.get("tijd_exit") or t.get("tijd_entry") or "00:00")[:5]), "%Y-%m-%d %H:%M")
            from datetime import timedelta
            van, tot = (start - timedelta(minutes=voor)).strftime("%Y-%m-%d %H:%M"), (eind + timedelta(minutes=na)).strftime("%Y-%m-%d %H:%M")
            m = sqlite3.connect("file:%s?mode=ro" % MARKT_DB, uri=True)
            candles = [list(r) for r in m.execute("SELECT tijd_ams, o, h, l, c FROM candles_m1 WHERE tijd_ams BETWEEN ? AND ? ORDER BY ts_utc", (van, tot))]
            m.close()
        except (sqlite3.Error, ValueError):
            candles = []
    return {"trade": {k: t.get(k) for k in ("id", "datum", "tijd_entry", "tijd_exit", "richting", "entry_prijs", "sl_prijs", "tp_prijs", "exit_prijs",
                                            "resultaat_r", "exit_reden", "grade", "emotie_voor", "les", "v3_sleutel", "sl_start", "tp_start", "expansie_begin")},
            "candles": candles, "events": [e for e in ev if e["soort"] != "tick"], "pad": _beheer(ev, t).get("pad", [])}


TOEGESTAAN = {"teams": "/api/teams", "doelen": "/api/doelen", "vergelijk": "/api/vergelijk"}


@router.get("/api/game/station/{naam}")
def api_station(naam: str, van: str = "", tot: str = ""):
    """Alleen-lezen doorgeefluik naar CBR Station op deze computer. Station uit = {}: de pagina laat dat deel dan weg."""
    pad = TOEGESTAAN.get(naam)
    if not pad:
        return {"error": "onbekend"}
    if naam == "vergelijk":
        pad += "?van=%s&tot=%s" % (van[:10], tot[:10])
    try:
        with urllib.request.urlopen(STATION + pad, timeout=3) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": "station niet bereikbaar (%s)" % type(e).__name__}
