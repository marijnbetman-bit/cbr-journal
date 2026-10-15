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
            # voorstel 6: kosten en spread in R; voorstel 8: diepste zwevende stand tijdens de trade (uit de MT5-ticks)
            "risico_eur": t.get("risico_eur") or t.get("risk_eur"),
            "kosten_r": round(-(t.get("charges") or 0) / (t.get("risico_eur") or t.get("risk_eur")), 3) if (t.get("risico_eur") or t.get("risk_eur")) else None,
            # spread_entry staat in MT5-punten (0,01), sl_afstand_points in jouw points (0,10)
            "spread_r": round((t.get("spread_entry") or 0) * 0.01 / (slp * POINT), 3) if slp and t.get("spread_entry") else None,
            "zwevend_min_eur": min((e["winst"] for e in events.get(t.get("positie_id"), []) if e.get("winst") is not None), default=None),
            "zwevend_max_eur": max((e["winst"] for e in events.get(t.get("positie_id"), []) if e.get("winst") is not None), default=None),
            "expansie_begin": t.get("expansie_begin"), "proces_score": t.get("proces_score"),
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


# ------------------------------------------------------------------ simulaties op de candles (voorstellen 1-3)
# Regel bij twijfel: raakt één candle zowel SL als TP, dan telt de SL (voorzichtig). Horizon: tot 240 min na de entry.

def _candles_per_dag(datums):
    if not os.path.exists(MARKT_DB) or not datums:
        return {}
    m = sqlite3.connect("file:%s?mode=ro" % MARKT_DB, uri=True)
    uit = {}
    try:
        for d in sorted(set(datums)):
            uit[d] = [tuple(r) for r in m.execute("SELECT tijd_ams, ts_utc, h, l, c FROM candles_m1 WHERE tijd_ams BETWEEN ? AND ? ORDER BY ts_utc",
                                                  (d + " 00:00", d + " 23:59"))]
    finally:
        m.close()
    return uit


def sim(candles, i0, short, entry, sl, tp, be_bij_r=None, horizon=240):
    """(r, uitkomst, minuten). Vanaf candle i0 (de entry-minuut, inclusief). be_bij_r: SL naar entry zodra +be_bij_r R."""
    risico = abs(entry - sl)
    if not risico or i0 is None:
        return None, "geen data", None
    stop = sl
    for j in range(i0, min(len(candles), i0 + horizon)):
        _, _, h, l, c = candles[j]
        geraakt_sl = (h >= stop) if short else (l <= stop)
        geraakt_tp = tp is not None and ((l <= tp) if short else (h >= tp))
        if geraakt_sl:
            return round(((entry - stop) if short else (stop - entry)) / risico, 2), ("BE" if stop == entry else "SL"), j - i0
        if geraakt_tp:
            return round(abs(tp - entry) / risico, 2), "TP", j - i0
        if be_bij_r and stop != entry and (((entry - l) if short else (h - entry)) >= be_bij_r * risico):
            stop = entry
    if i0 + 1 >= len(candles):
        return None, "geen data", None
    c = candles[min(len(candles), i0 + horizon) - 1][4]
    return round(((entry - c) if short else (c - entry)) / risico, 2), "open", horizon


def _index(candles, hhmm, datum):
    sleutel = "%s %s" % (datum, hhmm)
    for j, c in enumerate(candles):
        if c[0] >= sleutel:
            return j
    return None


@router.get("/api/game/simulatie")
def api_simulatie():
    """1. wat als je niets had aangeraakt (plan-SL/TP vanaf de entry) en 2. exit-varianten met je oorspronkelijke SL."""
    with db.get_conn() as conn:
        trades = _trades(conn)
        extra = {r["id"]: dict(r) for r in conn.execute("SELECT id, sl_start, tp_start, expansie_begin FROM trades")}
    C = _candles_per_dag([t["datum"] for t in trades])
    VAR = [("1R", 1.0), ("1,5R", 1.5), ("2R", 2.0), ("3R", 3.0)]
    uit, tot = [], {"plan": 0.0, "echt": 0.0, "n": 0, "var": {}}
    for t in trades:
        cs, e = C.get(t["datum"]) or [], extra.get(t["id"], {})
        entry, short = t.get("entry"), t.get("richting") == "short"
        sl, tp = e.get("sl_start") or t.get("sl"), e.get("tp_start") or t.get("tp")
        if not (cs and entry and sl):
            continue
        i0 = _index(cs, t["tijd"], t["datum"])
        if i0 is None:
            continue
        risico = abs(entry - sl)
        plan = sim(cs, i0, short, entry, sl, tp)
        if plan[0] is None:
            continue
        rij = {"id": t["id"], "datum": t["datum"], "tijd": t["tijd"], "richting": t["richting"], "r": t["r"], "plan_r": plan[0], "plan_uitkomst": plan[1],
               "plan_min": plan[2], "delta": round(t["r"] - plan[0], 2), "var": {}}
        for naam, mult in VAR:
            doel = entry - mult * risico if short else entry + mult * risico
            rij["var"][naam] = sim(cs, i0, short, entry, sl, doel)[0]
        rij["var"]["BE na 1R, TP 3R"] = sim(cs, i0, short, entry, sl, entry - 3 * risico if short else entry + 3 * risico, be_bij_r=1.0)[0]
        if e.get("expansie_begin"):
            top = sl + (-0.1 if short else 0.1)                         # SL staat 1 point voorbij de sweep
            half = (e["expansie_begin"] + top) / 2
            if (half < entry) if short else (half > entry):
                rij["var"]["50% expansie"] = sim(cs, i0, short, entry, sl, half)[0]
        uit.append(rij)
        tot["plan"] += plan[0]; tot["echt"] += t["r"]; tot["n"] += 1
        for k, v in rij["var"].items():
            if v is not None:
                x = tot["var"].setdefault(k, {"r": 0.0, "n": 0, "w": 0}); x["r"] += v; x["n"] += 1; x["w"] += v > 0
    for x in tot["var"].values():
        x["r"] = round(x["r"], 2)
    tot["plan"], tot["echt"] = round(tot["plan"], 2), round(tot["echt"], 2)
    return {"trades": uit, "totaal": tot, "regel": "Plan = je eerste SL en TP vanaf de entry-minuut, niets aangeraakt. Raakt één candle SL én TP, dan telt de SL. "
            "Na 240 min zonder SL/TP: afgerekend op de slotkoers."}


@router.get("/api/game/gemist")
def api_gemist(dagen: int = 30):
    """3. Setups die de bots in jouw venster zagen en die jij niet nam (met de afloop op 1:1), trades zonder setup, en je niet-gevulde orders."""
    from datetime import timedelta, timezone
    with db.get_conn() as conn:
        s = db.get_settings(conn)
        trades = _trades(conn)
        try:
            orders = [dict(r) for r in conn.execute("SELECT * FROM mt5_orders WHERE geplaatst >= date('now', ?) ORDER BY geplaatst",
                                                    ("-%d day" % dagen,))]
        except sqlite3.Error:
            orders = []
    venster = (s.get("venster_van") or "09:00", s.get("venster_tot") or "15:00")
    van = (datetime.now() - timedelta(days=dagen)).strftime("%Y-%m-%d")
    v = api_station("vergelijk", van, datetime.now().strftime("%Y-%m-%d"))
    setups = (v or {}).get("setups") or {}
    genomen = {t["v3_sleutel"] for t in trades if t.get("v3_sleutel")}
    kand = []
    for sleutel, teams in setups.items():
        b = teams.get("uitdager") or teams.get("kampioen")
        if not b or not b.get("entry") or not b.get("sl") or not b.get("besloten"):
            continue
        t_utc = datetime.fromisoformat(b["besloten"][:19]).replace(tzinfo=timezone.utc)
        kand.append((sleutel, b, int(t_utc.timestamp())))
    C = {}
    if kand and os.path.exists(MARKT_DB):
        m = sqlite3.connect("file:%s?mode=ro" % MARKT_DB, uri=True)
        try:
            for sleutel, b, ts in kand:
                C[sleutel] = [tuple(r) for r in m.execute("SELECT tijd_ams, ts_utc, h, l, c FROM candles_m1 WHERE ts_utc BETWEEN ? AND ? ORDER BY ts_utc",
                                                          (ts - 60, ts + 300 * 60))]
        finally:
            m.close()
    gemist = []
    for sleutel, b, ts in kand:
        cs = C.get(sleutel) or []
        if not cs:
            continue
        tijd = cs[0][0][11:16]
        if not (venster[0] <= tijd < venster[1]) or sleutel in genomen:
            continue
        short = sleutel.startswith("short")
        entry, sl = b["entry"], b["sl"]
        tp = entry - abs(entry - sl) if short else entry + abs(entry - sl)
        vul = next((j for j, c in enumerate(cs[:31]) if ((c[2] >= entry) if short else (c[3] <= entry))), None)   # limiet: binnen 30 min gevuld?
        uitkomst = sim(cs, vul, short, entry, sl, tp) if vul is not None else (None, "niet gevuld", None)
        gemist.append({"sleutel": sleutel, "datum": cs[0][0][:10], "tijd": tijd, "richting": "short" if short else "long", "entry": entry, "sl": sl,
                       "bots": {k: x["status"] for k, x in setups[sleutel].items()}, "kans": b.get("kans"), "r": uitkomst[0], "uitkomst": uitkomst[1]})
    sinds = min((t["datum"] for t in trades if t.get("v3_sleutel")), default=None)      # de koppeling met setups bestaat pas sinds dan
    zonder = [{"id": t["id"], "datum": t["datum"], "tijd": t["tijd"], "r": t["r"]} for t in trades
              if not t.get("v3_sleutel") and sinds and t["datum"] >= max(van, sinds)]
    # niet-gevulde orders: binnen 3 min gevolgd door een trade in dezelfde richting = 'limiet weggehaald en toch ingestapt'
    for o in orders:
        o["gevolgd_door"] = None
        for t in trades:
            if t["datum"] == (o["geplaatst"] or "")[:10] and t["richting"] == o["richting"] and t["tijd"] and o["klaar"]:
                dt = (datetime.strptime(t["datum"] + " " + t["tijd"], "%Y-%m-%d %H:%M") - datetime.strptime(o["klaar"], "%Y-%m-%d %H:%M")).total_seconds() / 60
                if 0 <= dt <= 3:
                    o["gevolgd_door"] = {"id": t["id"], "entry": t["entry"], "r": t["r"],
                                         "verschil_points": round(((t["entry"] - o["prijs"]) if t["richting"] == "long" else (o["prijs"] - t["entry"])) / POINT, 1) if t["entry"] and o["prijs"] else None}
                    break
    return {"venster": venster, "dagen": dagen, "station": not (v or {}).get("error"), "gemist": gemist, "zonder_setup": zonder, "orders": orders}


TOEGESTAAN = {"teams": "/api/teams", "doelen": "/api/doelen", "vergelijk": "/api/vergelijk", "markt": "/api/markt", "nieuws": "/api/nieuws",
              "rapporten": "/api/rapporten"}


@router.get("/api/game/station/{naam}")
def api_station(naam: str, van: str = "", tot: str = ""):
    """Alleen-lezen doorgeefluik naar CBR Station op deze computer. Station uit = {}: de pagina laat dat deel dan weg."""
    pad = TOEGESTAAN.get(naam)
    if not pad:
        return {"error": "onbekend"}
    if naam in ("vergelijk", "nieuws"):
        pad += "?van=%s&tot=%s" % (van[:10], tot[:10])
    try:
        with urllib.request.urlopen(STATION + pad, timeout=3) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": "station niet bereikbaar (%s)" % type(e).__name__}
