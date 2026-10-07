"""
CBR Trading Journal -- lokale FastAPI-server.

Start via start.bat (uvicorn) en open http://localhost:8000 in de browser.
XAUUSD-only, 2e uur Londense sessie.
"""

import csv
import io
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import date, timedelta

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

from . import cbr, db, stats, fouten, edge, backup, kalender, adherentie, simulatie, inzicht, rapport, sweep, prestaties, proces, watals, saldo, weekrapport

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")

# Versiestempel. Staat rechtsboven in de app, zodat je in één blik ziet welke
# build je draait -- en dus of het uitpakken gelukt is.
VERSIE = "2026.09.29.1"
BUILD = "journal-v2-een-geheel"

app = FastAPI(title="CBR Trading Journal")

db.init_db()
backup.maak_backup()   # fase 12.1 -- automatische back-up bij elke start

# v2 (29 sep 2026): kasstromen-tabel + eenmalig saldo op €209 (€100 gestort).
try:
    with db.get_conn() as _conn:
        saldo.zorg_schema(_conn)
        saldo.eenmalige_seed(_conn)
except Exception as _e:  # pragma: no cover
    print("[journal] saldo-migratie mislukt:", _e)

# Het handelsvenster staat in journal_config.json (bron van waarheid -- ook
# gebruikt door signalen.py/pretrade.py/mt5_koppeling.py). Hier meesyncen naar
# de settings-tabel zodat het proces-rapport hetzelfde venster gebruikt (23 sep).
try:
    with open(os.path.join(BASE_DIR, "journal_config.json"), encoding="utf-8") as _f:
        _jc = json.load(_f)
    with db.get_conn() as _conn:
        if "venster_van" in _jc:
            db.set_setting(_conn, "venster_van", _jc["venster_van"])
        if "venster_tot" in _jc:
            db.set_setting(_conn, "venster_tot", _jc["venster_tot"])
        if _jc.get("venster"):
            db.set_setting(_conn, "venster", json.dumps(_jc["venster"]))   # blokken (Asia + 10-15)
except Exception as _e:  # pragma: no cover
    print("[journal] venster meesyncen mislukt:", _e)


# ---------- Pydantic-modellen ----------

class TradeIn(BaseModel):
    datum: str
    tijd_entry: Optional[str] = ""
    instrument: str = "XAUUSD"
    sessie: Optional[str] = "2e uur Londen"
    richting: Optional[str] = ""          # "long" | "short" | ""

    crit1_conditie: str = cbr.VAL_MAYBE
    crit2_sweep: str = cbr.VAL_MAYBE
    crit3_shift: str = cbr.VAL_MAYBE
    crit4_entry: str = cbr.VAL_MAYBE
    crit5_tp: str = cbr.VAL_MAYBE

    # Fase 2 -- bias eerst. Vijf kritische criteria, drie kwaliteitscriteria.
    fase: int = 2
    f2_bias: str = cbr.VAL_MAYBE
    f2_dxy: str = cbr.VAL_MAYBE
    f2_expansie: str = cbr.VAL_MAYBE
    f2_sweep: str = cbr.VAL_MAYBE
    f2_shift: str = cbr.VAL_MAYBE
    f2_entry: str = cbr.VAL_MAYBE
    f2_sl: str = cbr.VAL_MAYBE
    f2_tp: str = cbr.VAL_MAYBE
    bias_1hr: Optional[str] = ""          # bullish | bearish | onduidelijk
    dxy_richting: Optional[str] = ""      # invers | unison | onduidelijk
    expansie_minuten: Optional[int] = None
    fvg_waarschuwing: Optional[str] = ""  # ja | nee
    trigger_type: Optional[str] = ""      # sweep_1e_uur | rebalance
    poging_nr: Optional[int] = None       # 1 of 2 -- max twee per sessie
    rr: Optional[float] = None
    status: Optional[str] = "genomen"      # gepland | genomen | overgeslagen
    skip_reden: Optional[str] = ""         # waarom overgeslagen (fase 11.2)
    tags: Optional[str] = ""               # vrije tags (fase 12.4)
    bron: Optional[str] = "live"           # live | backtest
    zekerheid: Optional[int] = None        # 1..5

    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    risk_eur: Optional[float] = None

    resultaat_eur: Optional[float] = None
    charges: Optional[float] = -0.06
    exit_reden: Optional[str] = ""
    sl_nabijheid: Optional[str] = ""   # nooit | halverwege | bijna
    tp_verloop: Optional[str] = ""     # precies | liep_door | te_vroeg

    foutcodes: Optional[str] = ""      # komma-gescheiden, bv "E1,R1"
    mentale_staat: Optional[str] = ""
    les: Optional[str] = ""
    notities: Optional[str] = ""
    dxy_context: Optional[str] = ""

    # Ronde 2 -- de sweep meten (1 point = 0,10 in prijs). Invullen bij ELKE
    # trade, ook winnaars: alleen verliezers loggen geeft een scheve steekproef.
    sweep_overshoot_points: Optional[float] = None
    sl_afstand_points: Optional[float] = None
    tp_afstand_points: Optional[float] = None

    # Ronde 2 -- kwaliteit naast de checklist.
    shift_kwaliteit: Optional[str] = ""        # duidelijk | soft | onduidelijk
    volume_hoog: Optional[str] = ""            # ja | nee
    overextensie_kwaliteit: Optional[str] = ""  # goed | slecht
    minuten_in_hourly: Optional[int] = None
    sl_dan_tp: Optional[str] = ""          # ja | nee -- SL geraakt, daarna alsnog TP
    luck_flag: Optional[str] = ""          # ja = voelde als luck / geen duidelijke edge


class NoTradeIn(BaseModel):
    datum: str
    tijd: Optional[str] = ""
    reden: Optional[str] = ""
    wat_zag_ik: Optional[str] = ""


def _validate_crits(t: TradeIn):
    for key in cbr.ALL_CRIT_KEYS:
        v = getattr(t, key)
        if v not in cbr.VALID_VALUES:
            raise HTTPException(400, f"Ongeldige waarde voor {key}: {v}")


def _validate_ronde2(t: TradeIn):
    """Lege waarde blijft altijd toegestaan -- niet elk veld hoort verplicht."""
    keuzes = [
        ("shift_kwaliteit", cbr.SHIFT_KWALITEIT_KEYS),
        ("volume_hoog", cbr.VOLUME_KEYS),
        ("overextensie_kwaliteit", cbr.OVEREXTENSIE_KEYS),
        ("sl_dan_tp", {"ja", "nee"}),
        ("luck_flag", {"ja", "nee"}),
        ("bias_1hr", {"bullish", "bearish", "onduidelijk"}),
        ("dxy_richting", {"invers", "unison", "onduidelijk"}),
        ("fvg_waarschuwing", {"ja", "nee"}),
        ("trigger_type", {"sweep_1e_uur", "rebalance"}),
    ]
    for key, geldig in keuzes:
        v = (getattr(t, key) or "").strip()
        if v and v not in geldig:
            raise HTTPException(400, f"Ongeldige waarde voor {key}: {v}")
    for key in ("sweep_overshoot_points", "sl_afstand_points", "tp_afstand_points"):
        v = getattr(t, key)
        if v is not None and v < 0:
            raise HTTPException(400, f"{key} kan niet negatief zijn")
    if t.minuten_in_hourly is not None and not (0 <= t.minuten_in_hourly <= 59):
        raise HTTPException(400, "minuten_in_hourly hoort tussen 0 en 59 te liggen")


def _trade_payload(t: TradeIn) -> dict:
    data = t.model_dump()
    # Grade is ALTIJD berekend, nooit meegestuurd door de client.
    data["grade"] = cbr.grade_voor(data, data.get("fase"))
    data["tags"] = _schoon_tags(data.get("tags"))
    return data


# ---------- API: config ----------

@app.get("/api/config")
def get_config():
    """Criteria, foutcodes en waarden voor de frontend."""
    return {
        "criteria": cbr.CRITERIA,
        "critical_keys": cbr.CRITICAL_KEYS,
        "quality_keys": cbr.QUALITY_KEYS,
        "values": {"yes": cbr.VAL_YES, "maybe": cbr.VAL_MAYBE, "no": cbr.VAL_NO},
        "symbols": cbr.SYMBOL,
        "foutcodes": cbr.FOUTCODES,
        "correcties": cbr.CORRECTIES,
        "emoties": cbr.EMOTIES,
        "skip_redenen": adherentie.SKIP_REDENEN,
        "voorbereiding": cbr.VOORBEREIDING,
        # Ronde 2
        "shift_kwaliteit": cbr.SHIFT_KWALITEIT,
        "shift_tooltip": cbr.SHIFT_TOOLTIP,
        "volume_opties": cbr.VOLUME_OPTIES,
        "overextensie_opties": cbr.OVEREXTENSIE_OPTIES,
        "point": cbr.POINT,
        # Ronde 3
        "sessie_toggles": cbr.SESSIE_TOGGLES,
        "staten": cbr.STATEN,
    }


class SessieIn(BaseModel):
    in_venster: Optional[str] = ""      # ja | nee
    plan_gevolgd: Optional[str] = ""    # ja | nee
    staat: Optional[str] = ""           # rustig | gehaast | moe
    les: Optional[str] = ""


@app.get("/api/sessie/{datum}")
def api_get_sessie(datum: str):
    with db.get_conn() as conn:
        return db.get_sessie(conn, datum)


@app.put("/api/sessie/{datum}")
def api_save_sessie(datum: str, s: SessieIn):
    for veld in ("in_venster", "plan_gevolgd"):
        v = (getattr(s, veld) or "").strip()
        if v and v not in {"ja", "nee"}:
            raise HTTPException(400, f"Ongeldige waarde voor {veld}: {v}")
    staat = (s.staat or "").strip()
    if staat and staat not in cbr.STAAT_KEYS:
        raise HTTPException(400, f"Ongeldige staat: {staat}")
    with db.get_conn() as conn:
        db.save_sessie(conn, datum, (s.in_venster or "").strip(),
                       (s.plan_gevolgd or "").strip(), staat, (s.les or "").strip())
        return db.get_sessie(conn, datum)


class VoorbereidingIn(BaseModel):
    punten: List[str] = []
    notitie: Optional[str] = ""


@app.get("/api/voorbereiding/{datum}")
def api_get_voorbereiding(datum: str):
    with db.get_conn() as conn:
        v = db.get_voorbereiding(conn, datum)
    return _voorbereiding_uit(datum, v)


@app.put("/api/voorbereiding/{datum}")
def api_put_voorbereiding(datum: str, v: VoorbereidingIn):
    geldig = [k for k in v.punten if k in cbr.VOORBEREIDING_KEYS]
    with db.get_conn() as conn:
        db.save_voorbereiding(conn, datum, ",".join(geldig), (v.notitie or "").strip())
        opnieuw = db.get_voorbereiding(conn, datum)
    return _voorbereiding_uit(datum, opnieuw)


def _voorbereiding_uit(datum, rij):
    punten = [p.strip() for p in ((rij or {}).get("punten") or "").split(",") if p.strip()]
    ontbreekt = [v for v in cbr.VOORBEREIDING if v["key"] not in punten]
    return {
        "datum": datum,
        "punten": punten,
        "notitie": (rij or {}).get("notitie") or "",
        "compleet": len(punten) == len(cbr.VOORBEREIDING),
        "n": len(punten),
        "totaal": len(cbr.VOORBEREIDING),
        "ontbreekt": ontbreekt,
        "codes": [v["code"] for v in ontbreekt if v["code"]],
    }


@app.get("/api/tags")
def api_tags():
    with db.get_conn() as conn:
        return {"lijst": db.alle_tags(conn)}


@app.get("/api/laatste_trade")
def api_laatste_trade():
    """
    Fase 9.1 -- slimme defaults. Geeft de velden terug die bij een volgende trade
    vrijwel altijd hetzelfde zijn, zodat "kopieer vorige" en de voorinvulling
    kloppen zonder dat je iets overtypt.
    """
    with db.get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM trades WHERE status='genomen' AND verwijderd_op IS NULL AND fase=2 "
            "ORDER BY datum DESC, id DESC LIMIT 1").fetchone()
    if not r:
        return {"gevonden": False}
    t = dict(r)
    velden = ["instrument", "sessie", "richting", "bron", "risk_eur", "charges",
              "tijd_entry", "zekerheid", "mentale_staat"]
    return {"gevonden": True, "datum": t["datum"], "id": t["id"],
            "waarden": {k: t.get(k) for k in velden}}


@app.post("/api/grade")
def grade_preview(t: TradeIn):
    """Server-autoritatieve grade voor een gegeven checklist (dubbelcheck)."""
    _validate_crits(t)
    data = t.model_dump()
    graad = cbr.grade_voor(data, data.get("fase"))

    # Grade-integriteit: staat een KRITISCH criterium op V terwijl je er in je
    # eigen woorden aan twijfelt? Dan is het feitelijk een ?. Geen blokkade --
    # jij beslist -- maar wel een vraag, want twijfel telt als ?.
    woorden = cbr.twijfel_in_tekst(data.get("notities"), data.get("les"),
                                   data.get("exit_reden"))
    verdacht = [k for k in cbr.CRITICAL_KEYS if data.get(k) == cbr.VAL_YES] if woorden else []
    if data.get("shift_kwaliteit") in ("soft", "onduidelijk") and \
            data.get("crit3_shift") == cbr.VAL_YES and "crit3_shift" not in verdacht:
        verdacht.append("crit3_shift")

    return {
        "grade": graad,
        "geen_trade": cbr.is_no_trade(graad),
        "twijfel": {"woorden": woorden, "criteria": verdacht},
    }


# ---------- API: trades ----------

@app.get("/api/trade/{trade_id}")
def api_get_trade(trade_id: int):
    with db.get_conn() as conn:
        trade = db.get_trade(conn, trade_id)
        if not trade:
            raise HTTPException(404, "Trade niet gevonden")
        trade["screenshots"] = db.get_screenshots_for_trade(conn, trade_id)
    trade["sl_marge"] = cbr.sl_marge(trade)   # afgeleid, niet opgeslagen
    return trade


@app.post("/api/trade")
def api_create_trade(t: TradeIn):
    _validate_crits(t)
    _validate_ronde2(t)
    payload = _trade_payload(t)
    with db.get_conn() as conn:
        new_id = db._insert_trade(conn, payload)
    return {"id": new_id, "grade": payload["grade"]}


@app.put("/api/trade/{trade_id}")
def api_update_trade(trade_id: int, t: TradeIn):
    _validate_crits(t)
    _validate_ronde2(t)
    payload = _trade_payload(t)
    with db.get_conn() as conn:
        if not db.get_trade(conn, trade_id):
            raise HTTPException(404, "Trade niet gevonden")
        cols = db.TRADE_FIELDS
        set_clause = ",".join(f"{c}=?" for c in cols) + ", updated_at=datetime('now')"
        values = [payload.get(c) for c in cols] + [trade_id]
        conn.execute(f"UPDATE trades SET {set_clause} WHERE id=?", values)
        model = conn.execute("SELECT model FROM trades WHERE id=?", (trade_id,)).fetchone()
    # v2: trades in het bias-vrije model houden hun grade uit de nieuwe checklist
    if model and model[0] == "biasvrij":
        try:
            import beoordelen as _b
            with db.get_conn() as conn:
                v = _b.herbereken(conn, trade_id)
            return {"id": trade_id, "grade": (v or {}).get("grade", payload["grade"])}
        except Exception as _e:  # pragma: no cover
            print("[journal] herbereken mislukt:", _e)
    return {"id": trade_id, "grade": payload["grade"]}


class StatusIn(BaseModel):
    status: str                        # genomen | overgeslagen | gepland
    skip_reden: Optional[str] = None   # fase 11.2: waarom bleef je weg?


@app.put("/api/trade/{trade_id}/status")
def api_set_status(trade_id: int, s: StatusIn):
    """Een gepland plan afronden: genomen of toch overgeslagen."""
    if s.status not in ("gepland", "genomen", "overgeslagen"):
        raise HTTPException(400, f"Ongeldige status: {s.status}")
    with db.get_conn() as conn:
        t = db.get_trade(conn, trade_id)
        if not t:
            raise HTTPException(404, "Trade niet gevonden")
        foutcodes = t.get("foutcodes") or ""
        # Een C-plan dat je tóch neemt is per definitie E5 (C-setup geforceerd).
        if s.status == "genomen" and t["grade"] == "C" and "E5" not in foutcodes:
            codes = [c.strip() for c in foutcodes.split(",") if c.strip()]
            codes.append("E5")
            foutcodes = ",".join(codes)
        skip = s.skip_reden if s.skip_reden is not None else (t.get("skip_reden") or "")
        if s.status != "overgeslagen":
            skip = ""
        conn.execute(
            "UPDATE trades SET status=?, foutcodes=?, skip_reden=?, "
            "updated_at=datetime('now') WHERE id=?",
            (s.status, foutcodes, skip, trade_id))
    return {"id": trade_id, "status": s.status, "foutcodes": foutcodes, "skip_reden": skip}


@app.delete("/api/trade/{trade_id}")
def api_delete_trade(trade_id: int):
    """Fase 16.1 -- naar de prullenbak, niet weg. Eén misklik hoort geen trade te kosten."""
    with db.get_conn() as conn:
        conn.execute("UPDATE trades SET verwijderd_op=datetime('now') WHERE id=?", (trade_id,))
    return {"ok": True, "prullenbak": True}


# ---------- API: no-trades ----------

@app.get("/api/no_trade/{no_trade_id}")
def api_get_no_trade(no_trade_id: int):
    with db.get_conn() as conn:
        nt = db.get_no_trade(conn, no_trade_id)
        if not nt:
            raise HTTPException(404, "No-trade niet gevonden")
        nt["screenshots"] = db.get_screenshots_for_no_trade(conn, no_trade_id)
    return nt


@app.post("/api/no_trade")
def api_create_no_trade(nt: NoTradeIn):
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO no_trades (datum, tijd, reden, wat_zag_ik, fase) "
            "VALUES (?,?,?,?,2)",
            (nt.datum, nt.tijd, nt.reden, nt.wat_zag_ik),
        )
        return {"id": cur.lastrowid}


@app.put("/api/no_trade/{no_trade_id}")
def api_update_no_trade(no_trade_id: int, nt: NoTradeIn):
    with db.get_conn() as conn:
        if not db.get_no_trade(conn, no_trade_id):
            raise HTTPException(404, "No-trade niet gevonden")
        conn.execute(
            "UPDATE no_trades SET datum=?, tijd=?, reden=?, wat_zag_ik=? WHERE id=?",
            (nt.datum, nt.tijd, nt.reden, nt.wat_zag_ik, no_trade_id),
        )
    return {"id": no_trade_id}


@app.delete("/api/no_trade/{no_trade_id}")
def api_delete_no_trade(no_trade_id: int):
    with db.get_conn() as conn:
        conn.execute("UPDATE no_trades SET verwijderd_op=datetime('now') WHERE id=?", (no_trade_id,))
    return {"ok": True, "prullenbak": True}


# ---------- API: dag ----------

@app.get("/api/dates")
def api_dates():
    with db.get_conn() as conn:
        return {"dates": db.list_dates(conn)}


@app.get("/api/day/{datum}")
def api_day(datum: str):
    with db.get_conn() as conn:
        trade_rows = conn.execute(
            "SELECT * FROM trades WHERE datum=? AND verwijderd_op IS NULL AND fase=2 ORDER BY id", (datum,)
        ).fetchall()
        trades = []
        for r in trade_rows:
            t = dict(r)
            t["screenshots"] = db.get_screenshots_for_trade(conn, t["id"])
            trades.append(t)

        nt_rows = conn.execute(
            "SELECT * FROM no_trades WHERE datum=? AND verwijderd_op IS NULL AND fase=2 ORDER BY id", (datum,)
        ).fetchall()
        no_trades = []
        for r in nt_rows:
            nt = dict(r)
            nt["screenshots"] = db.get_screenshots_for_no_trade(conn, nt["id"])
            no_trades.append(nt)

    summary = _day_summary(trades, no_trades)
    with db.get_conn() as conn:
        regels = _dagregels(db.get_settings(conn), trades)
        voorbereiding = _voorbereiding_uit(datum, db.get_voorbereiding(conn, datum))
        review = db.get_review(conn, "dag", datum)
        try:
            wk = db.get_review(conn, "week", _maandag(datum))
        except ValueError:
            wk = None
    return {"datum": datum, "trades": trades, "no_trades": no_trades, "summary": summary,
            "dagregels": regels,
            "voorbereiding": voorbereiding,
            "review": review or {"goed": "", "beter": "", "focus": ""},
            "week_focus": (wk or {}).get("focus") or "",
            "week_focus_af": (wk or {}).get("focus_af") or "",
            "week_maandag": _maandag(datum)}


def _int_setting(settings, key, standaard):
    try:
        return int(float(settings.get(key, standaard)))
    except (TypeError, ValueError):
        return standaard


def _dagregels(settings, alle_trades):
    """
    Fase 9.4 -- de vangrail. Niet blokkeren, wel hardop zeggen wat je eigen
    regels zeggen. Twee grenzen: hoeveel trades per dag, en stoppen na N verliezers.
    """
    max_trades = _int_setting(settings, "max_trades_dag", 3)
    stop_na = _int_setting(settings, "stop_na_verliezen", 2)

    genomen = [t for t in alle_trades if (t.get("status") or "genomen") == "genomen"]
    genomen.sort(key=lambda t: (t.get("tijd_entry") or "", t.get("id") or 0))

    n = len(genomen)
    verliezers = 0
    op_rij = 0
    max_op_rij = 0
    for t in genomen:
        netto = (t.get("resultaat_eur") or 0) + (t.get("charges") or 0)
        if netto < 0:
            verliezers += 1
            op_rij += 1
            max_op_rij = max(max_op_rij, op_rij)
        elif netto > 0:
            op_rij = 0

    over_limiet = bool(max_trades) and n > max_trades
    op_limiet = bool(max_trades) and n == max_trades
    na_stop = bool(stop_na) and max_op_rij >= stop_na

    boodschap = ""
    if over_limiet:
        boodschap = (f"Je zit op {n} trades vandaag, je eigen limiet is {max_trades}. "
                     "Dat is overtrading (P2) — noteer het eerlijk.")
    elif na_stop and not op_limiet:
        boodschap = (f"{max_op_rij} verliezers op rij. Je eigen regel zegt: stoppen. "
                     "Wat hierna komt is revenge (P1), geen setup.")
    elif op_limiet:
        boodschap = f"Je zit op je dagmaximum van {max_trades} trades. Vandaag klaar."

    return {
        "max_trades": max_trades,
        "stop_na": stop_na,
        "n_genomen": n,
        "verliezers": verliezers,
        "verliezers_op_rij": max_op_rij,
        "over_limiet": over_limiet,
        "op_limiet": op_limiet,
        "na_stop": na_stop,
        "boodschap": boodschap,
    }


def _day_summary(alle_trades, no_trades):
    """Dagsamenvatting. Geplande trades tellen niet mee in de cijfers."""
    trades = [t for t in alle_trades if t.get("status", "genomen") == "genomen"]
    n_gepland = sum(1 for t in alle_trades if t.get("status") == "gepland")
    n_overgeslagen = sum(1 for t in alle_trades if t.get("status") == "overgeslagen")
    n_trades = len(trades)
    valide = [t for t in trades if t["grade"] in ("A", "B")]
    n_valide = len(valide)
    valide_pct = round(100 * n_valide / n_trades) if n_trades else 0

    netto = 0.0
    for t in trades:
        res = t.get("resultaat_eur") or 0.0
        charges = t.get("charges") or 0.0
        netto += res + charges

    fout_set = []
    for t in trades:
        for code in (t.get("foutcodes") or "").split(","):
            code = code.strip()
            if code:
                fout_set.append(code)

    winners = [t for t in trades if (t.get("resultaat_eur") or 0) > 0]
    winrate = round(100 * len(winners) / n_trades) if n_trades else 0

    return {
        "n_trades": n_trades,
        "n_no_trades": len(no_trades),
        "n_valide": n_valide,
        "valide_pct": valide_pct,
        "netto_eur": round(netto, 2),
        "winrate": winrate,
        "foutcodes": fout_set,
        "n_fouten": len(fout_set),
        "n_gepland": n_gepland,
        "n_overgeslagen": n_overgeslagen,
    }


# ---------- API: screenshots ----------

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _safe_name(name: str) -> str:
    name = os.path.basename(name or "shot.png")
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    return name[:80] or "shot.png"


@app.post("/api/screenshot")
async def api_upload_screenshot(
    file: UploadFile = File(...),
    datum: str = Form(...),
    trade_id: Optional[int] = Form(None),
    no_trade_id: Optional[int] = Form(None),
    beschrijving: str = Form(""),
    type: str = Form("entry"),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Bestandstype niet toegestaan: {ext}")
    safe_datum = re.sub(r"[^0-9-]", "", datum) or "onbekend"
    daydir = os.path.join(SCREENSHOTS_DIR, safe_datum)
    os.makedirs(daydir, exist_ok=True)
    fname = f"{uuid.uuid4().hex[:10]}_{_safe_name(file.filename)}"
    abspath = os.path.join(daydir, fname)
    with open(abspath, "wb") as out:
        out.write(await file.read())
    pad = f"screenshots/{safe_datum}/{fname}"

    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO screenshots (trade_id, no_trade_id, pad, beschrijving, type) "
            "VALUES (?,?,?,?,?)",
            (trade_id, no_trade_id, pad, beschrijving, type),
        )
        sid = cur.lastrowid
    return {"id": sid, "pad": pad, "beschrijving": beschrijving, "type": type}


@app.put("/api/screenshot/{sid}")
def api_update_screenshot(sid: int, beschrijving: str = Form(None), type: str = Form(None)):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM screenshots WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404, "Screenshot niet gevonden")
        b = beschrijving if beschrijving is not None else row["beschrijving"]
        t = type if type is not None else row["type"]
        conn.execute("UPDATE screenshots SET beschrijving=?, type=? WHERE id=?", (b, t, sid))
    return {"id": sid, "beschrijving": b, "type": t}


@app.delete("/api/screenshot/{sid}")
def api_delete_screenshot(sid: int):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM screenshots WHERE id=?", (sid,)).fetchone()
        if row:
            abspath = os.path.join(BASE_DIR, row["pad"])
            if os.path.commonpath([os.path.abspath(abspath), SCREENSHOTS_DIR]) == SCREENSHOTS_DIR:
                try:
                    os.remove(abspath)
                except OSError:
                    pass
            conn.execute("DELETE FROM screenshots WHERE id=?", (sid,))
    return {"ok": True}


# ---------- API: instellingen ----------

class SettingsIn(BaseModel):
    startkapitaal: Optional[float] = None
    valuta: Optional[str] = None
    werkelijke_balans: Optional[float] = None
    max_trades_dag: Optional[int] = None
    stop_na_verliezen: Optional[int] = None


@app.get("/api/settings")
def api_get_settings():
    with db.get_conn() as conn:
        return db.get_settings(conn)


@app.put("/api/settings")
def api_put_settings(s: SettingsIn):
    with db.get_conn() as conn:
        if s.startkapitaal is not None:
            db.set_setting(conn, "startkapitaal", s.startkapitaal)
        if s.valuta is not None:
            db.set_setting(conn, "valuta", s.valuta)
        if s.werkelijke_balans is not None:
            db.set_setting(conn, "werkelijke_balans", s.werkelijke_balans)
        if s.max_trades_dag is not None:
            db.set_setting(conn, "max_trades_dag", max(0, s.max_trades_dag))
        if s.stop_na_verliezen is not None:
            db.set_setting(conn, "stop_na_verliezen", max(0, s.stop_na_verliezen))
        return db.get_settings(conn)


# ---------- API: statistiek / dashboard ----------

# Fase 16.2 -- welke zware analyse hoort bij welk tabblad. Wat je niet opent,
# wordt niet berekend. De Monte-Carlo alleen al is 10.000 trekkingen per lading.
DEEL_MODULES = {
    "vandaag":    {"dubbels", "backup", "proces"},
    "edge":       {"edge", "simulatie", "sweep"},
    "discipline": {"adherentie", "gemist", "discipline", "backup", "proces"},
    "patronen":   {"timing", "kalibratie", "tags", "kwaliteit"},
    "alles":      {"edge", "simulatie", "sweep", "adherentie", "gemist", "discipline",
                   "timing", "kalibratie", "tags", "kwaliteit", "dubbels", "backup", "proces"},
}


@app.get("/api/stats")
def api_stats(van: Optional[str] = None, tot: Optional[str] = None, bron: str = "live",
              sinds_regel: bool = False, deel: str = "alles",
              sl_points: Optional[float] = None):
    with db.get_conn() as conn:
        if sinds_regel:
            laatste = db.laatste_regelwijziging(conn)
            if laatste:
                van = max(van, laatste["datum"]) if van else laatste["datum"]
        q = "SELECT * FROM trades"
        clauses, params = ["status = 'genomen'", "verwijderd_op IS NULL AND fase=2"], []
        bc = _bron_clause(bron)
        if bc:
            clauses.append(bc)
        if van:
            clauses.append("datum >= ?"); params.append(van)
        if tot:
            clauses.append("datum <= ?"); params.append(tot)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY datum, id"
        trades = [dict(r) for r in conn.execute(q, params).fetchall()]

        # no_trades kent geen status- of bron-kolom
        nt_clauses = [c for c in clauses
                      if not c.startswith("status") and not c.startswith("bron")]
        ntq = "SELECT COUNT(*) AS c FROM no_trades"
        if nt_clauses:
            ntq += " WHERE " + " AND ".join(nt_clauses)
        n_no = conn.execute(ntq, params).fetchone()["c"]

        overgeslagen_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE status='overgeslagen' AND verwijderd_op IS NULL AND fase=2 ORDER BY datum, id").fetchall()]
        n_overgeslagen = len(overgeslagen_rows)
        n_backtest = conn.execute(
            "SELECT COUNT(*) AS c FROM trades WHERE bron='backtest' AND status='genomen' AND verwijderd_op IS NULL AND fase=2").fetchone()["c"]
        n_live = conn.execute(
            "SELECT COUNT(*) AS c FROM trades WHERE bron='live' AND status='genomen' AND verwijderd_op IS NULL AND fase=2").fetchone()["c"]

        n_shots = conn.execute("SELECT COUNT(*) AS c FROM screenshots").fetchone()["c"]

        # Welke trades hebben een screenshot? Nodig voor de discipline-meter (10.4).
        met_shot = {r["trade_id"] for r in conn.execute(
            "SELECT DISTINCT trade_id FROM screenshots WHERE trade_id IS NOT NULL")}
        for t in trades:
            t["heeft_screenshot"] = t["id"] in met_shot

        settings = db.get_settings(conn)
        startkapitaal = float(settings.get("startkapitaal") or 0)

    wil = DEEL_MODULES.get(deel, DEEL_MODULES["alles"])

    data = stats.compute_stats(trades, n_no, startkapitaal)
    data["r_liggen"] = prestaties.r_laten_liggen(trades)
    if "edge" in wil:
        data["edge"] = edge.analyse(trades, startkapitaal)
    data["kpi"]["n_overgeslagen"] = n_overgeslagen
    data["bron"] = {"gekozen": bron, "n_live": n_live, "n_backtest": n_backtest}
    if "adherentie" in wil or "gemist" in wil:
        adh = adherentie.analyse(trades)
        if "adherentie" in wil:
            data["adherentie"] = adh
        if "gemist" in wil:
            data["gemist"] = adherentie.gemist(
                overgeslagen_rows, adh["gevolgd"]["expectancy_r"])
    if "simulatie" in wil:
        data["simulatie"] = simulatie.analyse(trades)
    if "sweep" in wil:
        data["sweep"] = sweep.analyse(trades, sl_points)
    if "proces" in wil:
        with db.get_conn() as conn:
            sessie_rijen = db.alle_sessies(conn)
        data["proces"] = proces.analyse(
            trades, sessie_rijen,
            settings.get("venster_van", "10:00"), settings.get("venster_tot", "11:00"))
    if "tags" in wil:
        data["terugkerend"] = rapport.terugkerend(trades)
    if "kwaliteit" in wil:
        data["kwaliteit"] = sweep.kwaliteit(trades)
        data["in_hourly"] = sweep.timing_in_hourly(trades)
    if "tags" in wil:
        data["tags"] = rapport.tag_stats(trades)
    if "timing" in wil:
        data["timing"] = inzicht.timing(trades)
    if "kalibratie" in wil:
        data["kalibratie"] = inzicht.kalibratie(trades)
    if "discipline" in wil:
        with db.get_conn() as conn:
            voorbereid = db.voorbereiding_per_dag(conn)
        data["discipline"] = inzicht.discipline(
            trades, overgeslagen_rows,
            _int_setting(settings, "max_trades_dag", 3),
            _int_setting(settings, "stop_na_verliezen", 2),
            voorbereid, len(cbr.VOORBEREIDING))
    if "backup" in wil:
        data["backup"] = backup.status()
    if "dubbels" in wil:
        data["dubbels"] = backup.mogelijke_dubbels(trades)
    with db.get_conn() as conn:
        data["regelwijzigingen"] = db.list_regelwijzigingen(conn)
    data["sinds_regel"] = sinds_regel

    # Balans-check: klopt de journal met wat je broker laat zien?
    werkelijk_raw = (settings.get("werkelijke_balans") or "").strip()
    balans = {"werkelijk": None, "journaal": data["kpi"]["eindkapitaal"], "verschil": None}
    if werkelijk_raw:
        try:
            werkelijk = float(werkelijk_raw)
            balans["werkelijk"] = round(werkelijk, 2)
            balans["verschil"] = round(werkelijk - data["kpi"]["eindkapitaal"], 2)
        except ValueError:
            pass
    data["balans"] = balans
    data["kpi"]["n_screenshots"] = n_shots
    data["valuta"] = settings.get("valuta", "€")
    data["van"] = van
    data["tot"] = tot
    data["deel"] = deel
    return data


# ---------- API: reviews (dag en week) ----------

class ReviewIn(BaseModel):
    goed: Optional[str] = ""
    beter: Optional[str] = ""
    focus: Optional[str] = ""


def _maandag(datum_str: str) -> str:
    """De maandag van de week waarin deze datum valt."""
    d = date.fromisoformat(datum_str)
    return (d - timedelta(days=d.weekday())).isoformat()


@app.get("/api/review/{soort}/{sleutel}")
def api_get_review(soort: str, sleutel: str):
    if soort not in ("dag", "week"):
        raise HTTPException(400, "soort moet 'dag' of 'week' zijn")
    with db.get_conn() as conn:
        r = db.get_review(conn, soort, sleutel)
    return r or {"soort": soort, "sleutel": sleutel, "goed": "", "beter": "", "focus": ""}


@app.put("/api/review/{soort}/{sleutel}")
def api_save_review(soort: str, sleutel: str, r: ReviewIn):
    if soort not in ("dag", "week"):
        raise HTTPException(400, "soort moet 'dag' of 'week' zijn")
    with db.get_conn() as conn:
        db.save_review(conn, soort, sleutel, r.goed, r.beter, r.focus)
        return db.get_review(conn, soort, sleutel)


@app.get("/api/week/{datum}")
def api_week(datum: str):
    """Weekoverzicht met automatische samenvatting, plus de vorige week erbij."""
    try:
        maandag = _maandag(datum)
    except ValueError:
        raise HTTPException(400, "Ongeldige datum")
    zondag = (date.fromisoformat(maandag) + timedelta(days=6)).isoformat()
    vorige_ma = (date.fromisoformat(maandag) - timedelta(days=7)).isoformat()
    vorige_zo = (date.fromisoformat(maandag) - timedelta(days=1)).isoformat()

    with db.get_conn() as conn:
        deze = _trades_in_range(conn, maandag, zondag)
        vorige = _trades_in_range(conn, vorige_ma, vorige_zo)
        n_no = conn.execute(
            "SELECT COUNT(*) AS c FROM no_trades WHERE datum BETWEEN ? AND ? AND verwijderd_op IS NULL AND fase=2",
            (maandag, zondag)).fetchone()["c"]
        n_over = conn.execute(
            "SELECT COUNT(*) AS c FROM trades WHERE status='overgeslagen' AND datum BETWEEN ? AND ? AND verwijderd_op IS NULL AND fase=2",
            (maandag, zondag)).fetchone()["c"]
        review = db.get_review(conn, "week", maandag)
        vorige_review = db.get_review(conn, "week", vorige_ma)
        settings = db.get_settings(conn)

    start = float(settings.get("startkapitaal") or 0)
    st = stats.compute_stats(deze, n_no, start)
    ed = edge.analyse(deze, start)
    ft = fouten.analyse(deze)

    def _netto(ts):
        return round(sum((t.get("resultaat_eur") or 0) + (t.get("charges") or 0) for t in ts), 2)

    def _beste_a(ts):
        """De setup van de week om nog eens terug te kijken -- niet de grootste
        winst, maar de beste uitvoering die ook geld opleverde."""
        kandidaten = [t for t in ts if t.get("grade") == "A"
                      and ((t.get("resultaat_eur") or 0) + (t.get("charges") or 0)) > 0]
        if not kandidaten:
            return None
        beste = max(kandidaten, key=lambda t: (t.get("resultaat_eur") or 0) + (t.get("charges") or 0))
        return {
            "id": beste.get("id"), "datum": beste.get("datum"),
            "richting": beste.get("richting"), "rr": beste.get("rr"),
            "netto": round((beste.get("resultaat_eur") or 0) + (beste.get("charges") or 0), 2),
            "les": (beste.get("les") or "").strip(),
        }

    def _valide_pct(ts):
        return round(100 * sum(1 for t in ts if t["grade"] in ("A", "B")) / len(ts)) if ts else 0

    hoogte = []
    n = len(deze)
    if n:
        n_a = sum(1 for t in deze if t["grade"] == "A")
        if n_a:
            hoogte.append(f"{n_a}× een perfecte setup (grade A) — dat is het doel.")
        if n_over:
            hoogte.append(f"{n_over}× een setup bewust overgeslagen. Dat is discipline, geen gemiste kans.")
        if n_no:
            hoogte.append(f"{n_no} bewuste no-trades vastgelegd.")
        vp, vvp = _valide_pct(deze), _valide_pct(vorige)
        if vorige:
            if vp > vvp:
                hoogte.append(f"Je valide-setup-percentage ging van {vvp}% naar {vp}%.")
            elif vp < vvp:
                hoogte.append(f"Let op: je valide-setup-percentage zakte van {vvp}% naar {vp}%.")
        if ft["patronen"]:
            p = ft["patronen"][0]
            hoogte.append(f"Patroon: {p['code']} ({p['omschrijving']}) kwam {p['aantal']}× terug.")
        elif ft["totaal_fouten"] == 0:
            hoogte.append("Geen enkele foutcode deze week.")

    return {
        "maandag": maandag, "zondag": zondag,
        "n_trades": n, "n_no_trades": n_no, "n_overgeslagen": n_over,
        "netto": _netto(deze), "valide_pct": _valide_pct(deze),
        "grade_dist": st["grade_dist"],
        "expectancy_r": ed["expectancy_r"],
        "winrate": ed["winrate"],
        "foutcodes": ft["alle"][:5],
        "patronen": ft["patronen"],
        "hoogtepunten": hoogte,
        "vorige": {"n_trades": len(vorige), "netto": _netto(vorige), "valide_pct": _valide_pct(vorige)},
        "review": review or {"goed": "", "beter": "", "focus": "", "focus_af": ""},
        "vorige_focus": (vorige_review or {}).get("focus") or "",
        "vorige_focus_af": (vorige_review or {}).get("focus_af") or "",
        "beste_a": _beste_a(deze),
        "terugkerend": rapport.terugkerend(deze),
    }


class FocusAfIn(BaseModel):
    af: bool = True


@app.put("/api/review/{soort}/{sleutel}/focus_af")
def api_focus_af(soort: str, sleutel: str, body: FocusAfIn):
    """Je focus blijft bovenaan staan tot je 'm hier afvinkt."""
    if soort not in ("dag", "week"):
        raise HTTPException(400, "Ongeldig soort")
    with db.get_conn() as conn:
        db.zet_focus_af(conn, soort, sleutel, body.af)
        return db.get_review(conn, soort, sleutel)


# ---------- API: foutenanalyse ----------

def _bron_clause(bron):
    """live (standaard), backtest of alles."""
    if bron == "backtest":
        return "bron = 'backtest'"
    if bron == "alles":
        return None
    return "bron = 'live'"


def _trades_in_range(conn, van, tot, bron="live"):
    q = "SELECT * FROM trades"
    clauses, params = ["status = 'genomen'", "verwijderd_op IS NULL AND fase=2"], []
    bc = _bron_clause(bron)
    if bc:
        clauses.append(bc)
    if van:
        clauses.append("datum >= ?"); params.append(van)
    if tot:
        clauses.append("datum <= ?"); params.append(tot)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY datum, id"
    return [dict(r) for r in conn.execute(q, params).fetchall()]


@app.get("/api/fouten")
def api_fouten(van: Optional[str] = None, tot: Optional[str] = None, bron: str = "live"):
    import json as _json, os as _os
    with db.get_conn() as conn:
        trades = _trades_in_range(conn, van, tot, bron)
        verschoven = {}
        for r in conn.execute("SELECT positie_id, eerste_sl, laatste_sl FROM mt5_posities"):
            verschoven[r["positie_id"]] = (
                r["eerste_sl"] is not None and r["laatste_sl"] is not None
                and abs(r["eerste_sl"] - r["laatste_sl"]) > 0.5, False)
        settings = db.get_settings(conn)
    # venster + handelsdagen komen uit journal_config.json (bron van waarheid)
    cfg = {"venster_van": settings.get("venster_van", "10:00"),
           "venster_tot": settings.get("venster_tot", "15:00"),
           "max_trades_dag": settings.get("max_trades_dag")}
    try:
        with open(_os.path.join(BASE_DIR, "journal_config.json"), encoding="utf-8") as _f:
            _jc = _json.load(_f)
        cfg["venster_van"] = _jc.get("venster_van", cfg["venster_van"])
        cfg["venster_tot"] = _jc.get("venster_tot", cfg["venster_tot"])
        cfg["handelsdagen"] = _jc.get("handelsdagen")
        cfg["venster"] = _jc.get("venster")
        cfg["max_trades_dag"] = _jc.get("dagmaximum", cfg["max_trades_dag"])
    except Exception:  # pragma: no cover
        pass
    data = fouten.auto_analyse(trades, cfg, verschoven)
    return data


# ---------- API: trading log (mappen per dag) ----------

@app.get("/api/log")
def api_log(bron: str = "live"):
    """Eén map per handelsdag, met wat er die dag gebeurd is."""
    bc = _bron_clause(bron)
    extra = (" AND " + bc) if bc else ""
    with db.get_conn() as conn:
        rijen = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE verwijderd_op IS NULL AND fase=2 AND status='genomen'" + extra +
            " ORDER BY datum DESC, tijd_entry, id").fetchall()]
        for t in rijen:
            t["screenshots"] = db.get_screenshots_for_trade(conn, t["id"])
        no_trades = [dict(r) for r in conn.execute(
            "SELECT datum, COUNT(*) c FROM no_trades WHERE verwijderd_op IS NULL AND fase=2 "
            "GROUP BY datum").fetchall()]
        skips = [dict(r) for r in conn.execute(
            "SELECT datum, COUNT(*) c FROM trades WHERE verwijderd_op IS NULL AND fase=2 "
            "AND status='overgeslagen' GROUP BY datum").fetchall()]
        reviews = {r["sleutel"]: dict(r) for r in conn.execute(
            "SELECT * FROM reviews WHERE soort='dag'").fetchall()}

    nt_map = {r["datum"]: r["c"] for r in no_trades}
    skip_map = {r["datum"]: r["c"] for r in skips}

    dagen = {}
    for t in rijen:
        d = dagen.setdefault(t["datum"], {
            "datum": t["datum"], "trades": [], "netto_eur": 0.0, "netto_r": 0.0,
            "grades": {"A": 0, "B": 0, "C": 0},
            "n_no_trades": nt_map.get(t["datum"], 0),
            "n_overgeslagen": skip_map.get(t["datum"], 0),
            "n_shots": 0,
            "review": reviews.get(t["datum"]) or None,
        })
        d["trades"].append(t)
        d["netto_eur"] += edge._netto(t)
        d["netto_r"] += edge.r_van_trade(t)[0]
        d["grades"][t.get("grade", "C")] = d["grades"].get(t.get("grade", "C"), 0) + 1
        d["n_shots"] += len(t["screenshots"])

    # dagen zonder trades maar mét no-trades of skips horen er ook bij
    for datum in set(list(nt_map) + list(skip_map)):
        if datum not in dagen:
            dagen[datum] = {"datum": datum, "trades": [], "netto_eur": 0.0, "netto_r": 0.0,
                            "grades": {"A": 0, "B": 0, "C": 0},
                            "n_no_trades": nt_map.get(datum, 0),
                            "n_overgeslagen": skip_map.get(datum, 0), "n_shots": 0,
                            "review": reviews.get(datum) or None}

    lijst = sorted(dagen.values(), key=lambda d: d["datum"], reverse=True)
    for d in lijst:
        d["netto_eur"] = round(d["netto_eur"], 2)
        d["netto_r"] = round(d["netto_r"], 2)
        d["n"] = len(d["trades"])

    return {
        "dagen": lijst,
        "totaal": {
            "dagen": len(lijst),
            "trades": len(rijen),
            "netto_eur": round(sum(edge._netto(t) for t in rijen), 2),
            "netto_r": round(sum(edge.r_van_trade(t)[0] for t in rijen), 2),
            "perfect": sum(1 for t in rijen if t.get("grade") == "A"),
        },
        "criteria": cbr.CRITERIA,
    }


# ---------- API: prullenbak (fase 16.1) ----------

PRULLENBAK_DAGEN = 30


@app.get("/api/prullenbak")
def api_prullenbak():
    with db.get_conn() as conn:
        trades = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE verwijderd_op IS NOT NULL "
            "ORDER BY verwijderd_op DESC").fetchall()]
        no_trades = [dict(r) for r in conn.execute(
            "SELECT * FROM no_trades WHERE verwijderd_op IS NOT NULL "
            "ORDER BY verwijderd_op DESC").fetchall()]
    return {"trades": trades, "no_trades": no_trades, "dagen": PRULLENBAK_DAGEN,
            "aantal": len(trades) + len(no_trades)}


@app.post("/api/prullenbak/herstel/{soort}/{item_id}")
def api_herstel(soort: str, item_id: int):
    tabel = {"trade": "trades", "no_trade": "no_trades"}.get(soort)
    if not tabel:
        raise HTTPException(400, "soort moet 'trade' of 'no_trade' zijn")
    with db.get_conn() as conn:
        conn.execute(f"UPDATE {tabel} SET verwijderd_op=NULL WHERE id=?", (item_id,))
    return {"ok": True}


@app.delete("/api/prullenbak/{soort}/{item_id}")
def api_definitief_weg(soort: str, item_id: int):
    """Definitief verwijderen -- alleen als je daar in de prullenbak zelf om vraagt."""
    tabel = {"trade": "trades", "no_trade": "no_trades"}.get(soort)
    if not tabel:
        raise HTTPException(400, "soort moet 'trade' of 'no_trade' zijn")
    with db.get_conn() as conn:
        conn.execute(f"DELETE FROM {tabel} WHERE id=? AND verwijderd_op IS NOT NULL", (item_id,))
    return {"ok": True}


@app.delete("/api/prullenbak")
def api_prullenbak_legen():
    with db.get_conn() as conn:
        for tabel in ("trades", "no_trades"):
            conn.execute(f"DELETE FROM {tabel} WHERE verwijderd_op IS NOT NULL")
    return {"ok": True}


def _prullenbak_opruimen():
    """Bij de start: alles ouder dan 30 dagen echt weg."""
    try:
        with db.get_conn() as conn:
            for tabel in ("trades", "no_trades"):
                conn.execute(
                    f"DELETE FROM {tabel} WHERE verwijderd_op IS NOT NULL "
                    f"AND verwijderd_op < datetime('now', '-{PRULLENBAK_DAGEN} days')")
    except Exception:
        pass


# ---------- API: prestatie-tracker ----------

@app.get("/api/prestaties")
def api_prestaties(van: Optional[str] = None, tot: Optional[str] = None,
                   bron: str = "live", sinds_regel: bool = False):
    with db.get_conn() as conn:
        if sinds_regel:
            laatste = db.laatste_regelwijziging(conn)
            if laatste:
                van = max(van, laatste["datum"]) if van else laatste["datum"]
        clauses, params = ["status = 'genomen'", "verwijderd_op IS NULL AND fase=2"], []
        bc = _bron_clause(bron)
        if bc:
            clauses.append(bc)
        if van:
            clauses.append("datum >= ?"); params.append(van)
        if tot:
            clauses.append("datum <= ?"); params.append(tot)
        q = "SELECT * FROM trades WHERE " + " AND ".join(clauses) + " ORDER BY datum, id"
        trades = [dict(r) for r in conn.execute(q, params).fetchall()]
        settings = db.get_settings(conn)
        # Stop/TP verschoven tijdens de trade (uit MT5): eerste vs laatste niveau.
        verschoven = {}
        for r in conn.execute("SELECT positie_id, eerste_sl, laatste_sl, eerste_tp, laatste_tp FROM mt5_posities"):
            sl_m = (r["eerste_sl"] is not None and r["laatste_sl"] is not None
                    and abs(r["eerste_sl"] - r["laatste_sl"]) > 0.5)
            tp_m = (r["eerste_tp"] is not None and r["laatste_tp"] is not None
                    and abs(r["eerste_tp"] - r["laatste_tp"]) > 0.5)
            verschoven[r["positie_id"]] = (sl_m, tp_m)

    # Het startkapitaal hoort bij het HELE account, niet bij de gefilterde
    # periode. Filter je op één maand, dan is een percentage over dat
    # startkapitaal misleidend -- daarom geven we mee of er gefilterd is.
    startkapitaal = float(settings.get("startkapitaal") or 0)
    with db.get_conn() as conn:
        kas = saldo.lijst(conn)
        saldo_info = saldo.overzicht(conn)
        n_te_loggen = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE beoordeeld=0 AND verwijderd_op IS NULL"
        ).fetchone()[0]
    if van or tot:
        kas = [k for k in kas if (not van or k["datum"] >= van) and (not tot or k["datum"] <= tot)]
    data = prestaties.analyse(trades, startkapitaal, kasstromen=kas)
    data["saldo_info"] = saldo_info
    data["n_te_loggen"] = n_te_loggen
    data["gefilterd"] = bool(van or tot or sinds_regel)
    data["bron"] = bron
    met_pos = [t for t in trades if t.get("positie_id")]
    data["discipline_mt5"] = {
        "n_met_positie": len(met_pos),
        "sl_verschoven": sum(1 for t in met_pos if verschoven.get(t["positie_id"], (0, 0))[0]),
        "tp_verschoven": sum(1 for t in met_pos if verschoven.get(t["positie_id"], (0, 0))[1]),
    }
    # Recente trades voor de homepage (nieuwste eerst).
    def _rr(t):
        return t["resultaat_r"] if t.get("resultaat_r") is not None else edge.r_van_trade(t)[0]
    data["recent"] = [{
        "id": t.get("id"), "datum": t.get("datum"), "tijd": t.get("tijd_entry") or "",
        "richting": t.get("richting") or "", "grade": t.get("grade") or "",
        "netto": round((t.get("resultaat_eur") or 0) + (t.get("charges") or 0), 2),
        "r": round(_rr(t), 2), "beoordeeld": t.get("beoordeeld"),
        "schoon": t.get("schoon"), "emotie": t.get("emotie_voor") or "",
        "exit_reden": t.get("exit_reden") or "",
        "sessie": prestaties.sessie_van(t.get("tijd_entry")) or "",
    } for t in trades[-25:][::-1]]
    return data


# ---------- API: weekrapport / progressie (v2.1) ----------

def _auto_cfg(settings):
    cfg = {"venster_van": settings.get("venster_van", "10:00"),
           "venster_tot": settings.get("venster_tot", "15:00"),
           "max_trades_dag": settings.get("max_trades_dag")}
    try:
        with open(os.path.join(BASE_DIR, "journal_config.json"), encoding="utf-8") as _f:
            _jc = json.load(_f)
        cfg["venster_van"] = _jc.get("venster_van", cfg["venster_van"])
        cfg["venster_tot"] = _jc.get("venster_tot", cfg["venster_tot"])
        cfg["handelsdagen"] = _jc.get("handelsdagen")
        cfg["venster"] = _jc.get("venster")
        cfg["max_trades_dag"] = _jc.get("dagmaximum", cfg["max_trades_dag"])
    except Exception:  # pragma: no cover
        pass
    return cfg


def _week_data(datum: Optional[str]):
    ma = weekrapport.maandag_van(datum or date.today().isoformat())
    zo = ma + timedelta(days=6)
    vma, vzo = ma - timedelta(days=7), ma - timedelta(days=1)
    with db.get_conn() as conn:
        alles = _trades_in_range(conn, None, None)
        settings = db.get_settings(conn)
        verschoven = {}
        for r in conn.execute("SELECT positie_id, eerste_sl, laatste_sl FROM mt5_posities"):
            verschoven[r["positie_id"]] = (
                r["eerste_sl"] is not None and r["laatste_sl"] is not None
                and abs(r["eerste_sl"] - r["laatste_sl"]) > 0.5, False)
        charts = {}
        for r in conn.execute("SELECT trade_id, pad FROM screenshots WHERE trade_id IS NOT NULL ORDER BY id"):
            charts.setdefault(r["trade_id"], "/" + r["pad"])
    cfg = _auto_cfg(settings)
    deze = [t for t in alles if ma.isoformat() <= t["datum"] <= zo.isoformat()]
    vorig = [t for t in alles if vma.isoformat() <= t["datum"] <= vzo.isoformat()]
    data = weekrapport.rapport(deze, vorig, alles, cfg, verschoven)
    for t in data["trades"]:
        t["chart"] = charts.get(t["id"])
    data.update({"maandag": ma.isoformat(), "zondag": zo.isoformat(), **weekrapport.week_label(ma),
                 "vorige_maandag": vma.isoformat(),
                 "volgende_maandag": (ma + timedelta(days=7)).isoformat()})
    return data


@app.get("/api/weekrapport")
def api_weekrapport(datum: Optional[str] = None):
    try:
        return _week_data(datum)
    except ValueError:
        raise HTTPException(400, "Ongeldige datum")


@app.get("/api/weken")
def api_weken(aantal: int = 12):
    with db.get_conn() as conn:
        alles = _trades_in_range(conn, None, None)
        settings = db.get_settings(conn)
    return {"weken": weekrapport.weken(alles, _auto_cfg(settings), aantal=aantal)}


@app.get("/api/weekrapport.pdf")
def api_weekrapport_pdf(datum: Optional[str] = None):
    data = _week_data(datum)
    try:
        import pdf_week
    except Exception as e:  # pragma: no cover
        raise HTTPException(500, f"PDF-module niet beschikbaar: {e}")
    pdf = pdf_week.bouw(data, BASE_DIR)
    naam = f"cbr-week-{data['jaar']}-{data['week']:02d}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{naam}"'})


# ---------- API: saldo en kasstromen (v2, 29 sep 2026) ----------

class KasstroomIn(BaseModel):
    datum: str
    soort: str
    bedrag: float
    notitie: Optional[str] = ""


class SaldoZetIn(BaseModel):
    saldo: float
    datum: Optional[str] = None
    notitie: Optional[str] = ""


class StartkapitaalIn(BaseModel):
    startkapitaal: float


class VolgenIn(BaseModel):
    aan: bool


def _mt5_cfg_volgen():
    try:
        with open(os.path.join(BASE_DIR, "journal_config.json"), encoding="utf-8") as f:
            return bool((json.load(f).get("mt5") or {}).get("saldo_volgen", True))
    except Exception:
        return True


@app.get("/api/saldo")
def api_saldo():
    with db.get_conn() as conn:
        o = saldo.overzicht(conn)
    o["mt5_volgen"] = _mt5_cfg_volgen()
    return o


@app.post("/api/kasstroom")
def api_kasstroom(k: KasstroomIn):
    if k.soort not in ("storting", "opname", "correctie"):
        raise HTTPException(400, "soort moet storting, opname of correctie zijn")
    try:
        with db.get_conn() as conn:
            kid = saldo.voeg_toe(conn, k.datum, k.soort, k.bedrag, k.notitie or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "id": kid}


@app.delete("/api/kasstroom/{kid}")
def api_kasstroom_weg(kid: int):
    with db.get_conn() as conn:
        saldo.verwijder(conn, kid)
    return {"ok": True}


@app.post("/api/saldo/zet")
def api_saldo_zet(z: SaldoZetIn):
    with db.get_conn() as conn:
        kid, verschil = saldo.zet_saldo(conn, z.saldo, z.datum, z.notitie or "")
    return {"ok": True, "id": kid, "verschil": verschil}


@app.put("/api/startkapitaal")
def api_startkapitaal(s: StartkapitaalIn):
    with db.get_conn() as conn:
        db.set_setting(conn, "startkapitaal", str(round(s.startkapitaal, 2)))
    return {"ok": True}


@app.put("/api/saldo/volgen")
def api_saldo_volgen(v: VolgenIn):
    pad = os.path.join(BASE_DIR, "journal_config.json")
    with open(pad, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("mt5", {})["saldo_volgen"] = bool(v.aan)
    tmp = pad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)
    os.replace(tmp, pad)
    return {"ok": True, "aan": bool(v.aan)}


@app.get("/api/rapport.pdf")
def api_rapport_pdf(van: Optional[str] = None, tot: Optional[str] = None, bron: str = "live"):
    """Kerncijfers van de gekozen periode als 1-pagina PDF. Alles automatisch."""
    with db.get_conn() as conn:
        clauses, params = ["status = 'genomen'", "verwijderd_op IS NULL AND fase=2"], []
        bc = _bron_clause(bron)
        if bc:
            clauses.append(bc)
        if van:
            clauses.append("datum >= ?"); params.append(van)
        if tot:
            clauses.append("datum <= ?"); params.append(tot)
        q = "SELECT * FROM trades WHERE " + " AND ".join(clauses) + " ORDER BY datum, id"
        trades = [dict(r) for r in conn.execute(q, params).fetchall()]
        settings = db.get_settings(conn)
    start = float(settings.get("startkapitaal") or 0)
    data = prestaties.analyse(trades, start)
    ed = edge.analyse(trades, start)
    periode = "alles" if not (van or tot) else f"{van or 'begin'} t/m {tot or 'nu'}"
    try:
        import pdf_rapport
    except Exception as e:  # pragma: no cover
        raise HTTPException(500, f"PDF-module niet beschikbaar: {e}")
    pdf = pdf_rapport.bouw_pdf(periode, bron, data["kern"], ed, data["equity"],
                              data["per_uur"]["beste"], data["r_liggen"])
    naam = f"cbr-rapport-{van or 'alles'}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{naam}"'})


@app.get("/prestaties")
def prestaties_pagina():
    # v2: prestaties staat nu op de homepage
    return RedirectResponse("/#prestaties", status_code=307)


@app.get("/hoe-sta-ik-ervoor")
def hoe_sta_ik_ervoor_weg():
    return RedirectResponse("/", status_code=307)


# ---------- API: wat-als-scenario's ----------

@app.get("/api/watals")
def api_watals(van: Optional[str] = None, tot: Optional[str] = None,
               bron: str = "live", sinds_regel: bool = False,
               sl_points: Optional[float] = None, tp_factor: Optional[float] = None,
               aanname: str = "grade", eigen_winrate: float = 50.0):
    """
    Scenario's over je eigen trades. De overgeslagen setups komen hier bewust
    apart binnen: die horen NIET in de gewone cijfers thuis, maar zijn wel het
    hele punt van de projectie-blokken.
    """
    with db.get_conn() as conn:
        if sinds_regel:
            laatste = db.laatste_regelwijziging(conn)
            if laatste:
                van = max(van, laatste["datum"]) if van else laatste["datum"]
        clauses, params = ["status = 'genomen'", "verwijderd_op IS NULL AND fase=2"], []
        bc = _bron_clause(bron)
        if bc:
            clauses.append(bc)
        if van:
            clauses.append("datum >= ?"); params.append(van)
        if tot:
            clauses.append("datum <= ?"); params.append(tot)
        q = "SELECT * FROM trades WHERE " + " AND ".join(clauses) + " ORDER BY datum, id"
        trades = [dict(r) for r in conn.execute(q, params).fetchall()]

        over_clauses = ["status = 'overgeslagen'", "verwijderd_op IS NULL AND fase=2"]
        over_params = []
        if van:
            over_clauses.append("datum >= ?"); over_params.append(van)
        if tot:
            over_clauses.append("datum <= ?"); over_params.append(tot)
        overgeslagen = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE " + " AND ".join(over_clauses) + " ORDER BY datum, id",
            over_params).fetchall()]

        settings = db.get_settings(conn)

    startkapitaal = float(settings.get("startkapitaal") or 0)
    data = watals.analyse(
        trades, overgeslagen, startkapitaal,
        van=settings.get("venster_van", "11:00"),
        tot=settings.get("venster_tot", "12:00"),
        sl_points=sl_points, tp_factor=tp_factor,
        aanname=aanname, eigen_winrate=eigen_winrate,
    )
    data["gefilterd"] = bool(van or tot or sinds_regel)
    data["bron"] = bron
    return data


@app.get("/watals")
def watals_pagina():
    # v2: wat-als is eruit (had geen nut); code blijft in app/watals.py
    return RedirectResponse("/", status_code=307)


# ---------- API: setup-bibliotheek (fase 13.2) ----------

@app.get("/api/setups")
def api_setups(grade: str = "A", bron: str = "live"):
    """
    Je beste setups als beeldmateriaal. Vijf minuten hierdoor bladeren vóór de
    sessie kalibreert je oog beter dan welke tabel dan ook.
    """
    grades = ["A", "B"] if grade == "AB" else [grade]
    bc = _bron_clause(bron)
    extra = (" AND " + bc) if bc else ""
    with db.get_conn() as conn:
        rijen = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE status='genomen' AND verwijderd_op IS NULL AND fase=2 AND grade IN (%s)%s "
            "ORDER BY datum DESC, id DESC" % (",".join("?" * len(grades)), extra),
            grades).fetchall()]
        for t in rijen:
            t["screenshots"] = db.get_screenshots_for_trade(conn, t["id"])
        n_a = conn.execute("SELECT COUNT(*) c FROM trades WHERE grade='A' AND status='genomen' AND verwijderd_op IS NULL AND fase=2").fetchone()["c"]
        n_b = conn.execute("SELECT COUNT(*) c FROM trades WHERE grade='B' AND status='genomen' AND verwijderd_op IS NULL AND fase=2").fetchone()["c"]

    met_beeld = [t for t in rijen if t["screenshots"]]
    return {
        "grade": grade,
        "setups": rijen,
        "n_a": n_a, "n_b": n_b,
        "n_met_beeld": len(met_beeld),
        "n_zonder_beeld": len(rijen) - len(met_beeld),
        "criteria": cbr.CRITERIA,
    }


# ---------- API: zoeken over alles (fase 13.4) ----------

@app.get("/api/zoek")
def api_zoek(q: str = "", limiet: int = 20):
    """Eén veld dat trades, lessen, notities, reviews en regelwijzigingen doorzoekt."""
    q = (q or "").strip()
    if len(q) < 2:
        return {"q": q, "resultaten": []}
    pat = f"%{q}%"
    uit = []
    with db.get_conn() as conn:
        for r in conn.execute(
            "SELECT id, datum, tijd_entry, grade, les, notities, foutcodes, tags, richting "
            "FROM trades WHERE verwijderd_op IS NULL AND fase=2 AND (les LIKE ? OR notities LIKE ? OR foutcodes LIKE ? OR tags LIKE ? "
            "OR exit_reden LIKE ? OR mentale_staat LIKE ?) ORDER BY datum DESC, id DESC LIMIT ?",
                (pat, pat, pat, pat, pat, pat, limiet)):
            uit.append({"soort": "trade", "id": r["id"], "datum": r["datum"],
                        "titel": f"{r['datum']} · grade {r['grade']}" +
                                 (f" · {r['richting']}" if r["richting"] else ""),
                        "tekst": (r["les"] or r["notities"] or "")[:140],
                        "extra": " ".join(x for x in (r["foutcodes"], r["tags"]) if x),
                        "url": f"/trade?id={r['id']}"})
        for r in conn.execute(
            "SELECT id, datum, titel, tekst, tags FROM notities "
            "WHERE titel LIKE ? OR tekst LIKE ? OR tags LIKE ? ORDER BY datum DESC LIMIT ?",
                (pat, pat, pat, limiet)):
            uit.append({"soort": "notitie", "id": r["id"], "datum": r["datum"],
                        "titel": r["titel"], "tekst": (r["tekst"] or "")[:140],
                        "extra": r["tags"] or "", "url": "/notities"})
        for r in conn.execute(
            "SELECT soort, sleutel, goed, beter, focus FROM reviews "
            "WHERE goed LIKE ? OR beter LIKE ? OR focus LIKE ? ORDER BY sleutel DESC LIMIT ?",
                (pat, pat, pat, limiet)):
            tekst = " · ".join(x for x in (r["goed"], r["beter"], r["focus"]) if x)
            uit.append({"soort": "review", "id": None, "datum": r["sleutel"],
                        "titel": f"{r['soort']}review {r['sleutel']}",
                        "tekst": tekst[:140], "extra": "",
                        "url": ("/week?datum=" if r["soort"] == "week" else "/?datum=") + r["sleutel"]})
        for r in conn.execute(
            "SELECT id, datum, titel, toelichting FROM regelwijzigingen "
            "WHERE titel LIKE ? OR toelichting LIKE ? ORDER BY datum DESC LIMIT ?",
                (pat, pat, limiet)):
            uit.append({"soort": "regel", "id": r["id"], "datum": r["datum"],
                        "titel": "§ " + r["titel"], "tekst": r["toelichting"] or "",
                        "extra": "", "url": "/regels"})
    uit.sort(key=lambda x: x["datum"] or "", reverse=True)
    return {"q": q, "resultaten": uit[:limiet]}


# ---------- API: notitieboek (fase 12.3) ----------

class NotitieIn(BaseModel):
    id: Optional[int] = None
    datum: str
    titel: str
    tekst: Optional[str] = ""
    tags: Optional[str] = ""


@app.get("/api/notities")
def api_notities(zoek: Optional[str] = ""):
    with db.get_conn() as conn:
        return {"lijst": db.list_notities(conn, (zoek or "").strip())}


@app.post("/api/notitie")
def api_save_notitie(n: NotitieIn):
    if not n.titel.strip():
        raise HTTPException(400, "Geef je notitie een titel.")
    with db.get_conn() as conn:
        nid = db.save_notitie(conn, n.id, n.datum, n.titel.strip(),
                              (n.tekst or "").strip(), _schoon_tags(n.tags))
    return {"id": nid}


@app.delete("/api/notitie/{nid}")
def api_del_notitie(nid: int):
    with db.get_conn() as conn:
        db.delete_notitie(conn, nid)
    return {"ok": True}


def _schoon_tags(ruw):
    """Komma-gescheiden, ontdubbeld, kleine letters -- anders krijg je 'Sweep' en 'sweep'."""
    gezien, uit = set(), []
    for tag in (ruw or "").split(","):
        tag = " ".join(tag.split()).lower()
        if tag and tag not in gezien:
            gezien.add(tag)
            uit.append(tag)
    return ", ".join(uit)


# ---------- API: rapportkaart (fase 12.2) ----------

@app.get("/api/rapport")
def api_rapport(soort: str = "maand", sleutel: Optional[str] = None, bron: str = "live"):
    if soort not in ("maand", "jaar"):
        raise HTTPException(400, "soort moet 'maand' of 'jaar' zijn")
    vandaag = date.today()
    sleutel = sleutel or (vandaag.strftime("%Y-%m") if soort == "maand" else str(vandaag.year))
    try:
        van, tot, _ = rapport.periode_grenzen(soort, sleutel)
    except (ValueError, IndexError):
        raise HTTPException(400, f"Ongeldige sleutel: {sleutel}")

    bc = _bron_clause(bron)
    extra = (" AND " + bc) if bc else ""
    with db.get_conn() as conn:
        trades = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE status='genomen' AND verwijderd_op IS NULL AND fase=2 AND datum BETWEEN ? AND ?" + extra,
            (van, tot)).fetchall()]
        met_shot = {r["trade_id"] for r in conn.execute(
            "SELECT DISTINCT trade_id FROM screenshots WHERE trade_id IS NOT NULL")}
        for t in trades:
            t["heeft_screenshot"] = t["id"] in met_shot
        overgeslagen = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE status='overgeslagen' AND verwijderd_op IS NULL AND fase=2 AND datum BETWEEN ? AND ?",
            (van, tot)).fetchall()]
        no_trades = [dict(r) for r in conn.execute(
            "SELECT * FROM no_trades WHERE datum BETWEEN ? AND ? AND verwijderd_op IS NULL AND fase=2", (van, tot)).fetchall()]
        reviews = [db.row_to_dict(r) for r in conn.execute(
            "SELECT * FROM reviews WHERE sleutel BETWEEN ? AND ? ORDER BY sleutel",
            (van, tot)).fetchall()]
        settings = db.get_settings(conn)

    data = rapport.bouw(soort, sleutel, trades, overgeslagen, no_trades, reviews,
                        float(settings.get("startkapitaal") or 0))
    data["tags"] = rapport.tag_stats(trades)
    data["valuta"] = settings.get("valuta", "€")
    return data


# ---------- API: regel-changelog (fase 11.4) ----------

class RegelIn(BaseModel):
    datum: str
    titel: str
    toelichting: Optional[str] = ""


@app.get("/api/regelwijzigingen")
def api_regelwijzigingen():
    with db.get_conn() as conn:
        return {"lijst": db.list_regelwijzigingen(conn)}


@app.post("/api/regelwijziging")
def api_add_regelwijziging(r: RegelIn):
    if not r.titel.strip():
        raise HTTPException(400, "Geef je regelwijziging een titel.")
    with db.get_conn() as conn:
        rid = db.add_regelwijziging(conn, r.datum, r.titel.strip(), (r.toelichting or "").strip())
    return {"id": rid}


@app.delete("/api/regelwijziging/{rid}")
def api_del_regelwijziging(rid: int):
    with db.get_conn() as conn:
        db.delete_regelwijziging(conn, rid)
    return {"ok": True}


# ---------- API: kalender (fase 10.1) ----------

@app.get("/api/kalender")
def api_kalender(jaar: Optional[int] = None, maand: Optional[int] = None,
                 bron: str = "live"):
    vandaag = date.today()
    jaar = jaar or vandaag.year
    maand = maand or vandaag.month
    if not 1 <= maand <= 12:
        raise HTTPException(status_code=400, detail="maand moet 1..12 zijn")

    bc = _bron_clause(bron)
    extra = (" AND " + bc) if bc else ""
    with db.get_conn() as conn:
        genomen = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE status='genomen' AND verwijderd_op IS NULL AND fase=2" + extra).fetchall()]
        overgeslagen = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE status='overgeslagen' AND verwijderd_op IS NULL AND fase=2" + extra).fetchall()]
        no_trades = [dict(r) for r in conn.execute("SELECT * FROM no_trades WHERE verwijderd_op IS NULL AND fase=2").fetchall()]

    data = kalender.maand(jaar, maand, genomen, overgeslagen, no_trades)
    data["jaarstrook"] = kalender.jaarstrook(jaar, genomen, overgeslagen)
    data["bron"] = bron
    return data


# ---------- API: export / back-up ----------

@app.post("/api/backup")
def api_backup():
    """Handmatig een back-up maken (naast de automatische bij elke start)."""
    pad = backup.maak_backup(force=True)
    st = backup.status()
    st["gemaakt"] = bool(pad)
    return st


@app.get("/api/backup")
def api_backup_status():
    return backup.status()



EXPORT_TABELLEN = ["trades", "no_trades", "screenshots", "reviews",
                   "notities", "regelwijzigingen", "settings"]


@app.get("/api/export")
def api_export():
    """Alles in een zip: CSV per tabel plus de screenshots."""
    tmpdir = tempfile.mkdtemp(prefix="cbr-export-")
    zip_pad = os.path.join(tmpdir, "cbr-journal-export.zip")
    with db.get_conn() as conn, zipfile.ZipFile(zip_pad, "w", zipfile.ZIP_DEFLATED) as z:
        for tabel in EXPORT_TABELLEN:
            try:
                rows = conn.execute(f"SELECT * FROM {tabel}").fetchall()
            except Exception:
                continue
            buf = io.StringIO()
            if rows:
                w = csv.DictWriter(buf, fieldnames=rows[0].keys(), delimiter=";")
                w.writeheader()
                for r in rows:
                    w.writerow(dict(r))
            z.writestr(f"{tabel}.csv", buf.getvalue())

        # Screenshots meenemen
        for wortel, _, files in os.walk(SCREENSHOTS_DIR):
            for f in files:
                if f.startswith("."):
                    continue
                vol = os.path.join(wortel, f)
                rel = os.path.relpath(vol, os.path.dirname(SCREENSHOTS_DIR))
                z.write(vol, rel)

        z.writestr("LEESMIJ.txt",
                   "Export van je CBR Trading Journal.\r\n"
                   "CSV-bestanden zijn puntkomma-gescheiden (opent direct in Excel).\r\n"
                   "De map screenshots/ bevat je charts.\r\n")

    return FileResponse(zip_pad, filename="cbr-journal-export.zip",
                        media_type="application/zip")


# ---------- Statische bestanden + pagina's ----------

def _pagina(naam: str) -> HTMLResponse:
    """
    Serveer een pagina met een versie achter elk stylesheet en script, zodat je
    browser nooit een oude style.css of dashboard.js blijft tonen na een update.
    De HTML zelf wordt niet gecachet.
    """
    with open(os.path.join(STATIC_DIR, naam), encoding="utf-8") as f:
        html = f.read()
    html = re.sub(r'(/static/[\w./-]+\.(?:css|js))"', r'\1?v=' + VERSIE + '"', html)
    html = html.replace("<body", f'<body data-versie="{VERSIE}" data-build="{BUILD}"', 1)
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    })


@app.get("/api/versie")
def api_versie():
    return {"versie": VERSIE, "build": BUILD}

# Screenshots worden in fase 2 opgeslagen; map alvast serveerbaar maken.
app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")



@app.get("/api/archief")
def api_archief():
    """
    Alles uit fase 1 (t/m 10 sep 2026). Read-only: deze trades zijn met het
    oude model gelogd en tellen niet meer mee in de statistiek van fase 2,
    maar er zaten goede setups tussen die de moeite van het terugkijken waard
    blijven.
    """
    with db.get_conn() as conn:
        trades = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE fase=1 AND verwijderd_op IS NULL "
            "ORDER BY datum, id").fetchall()]
        no_trades = [dict(r) for r in conn.execute(
            "SELECT * FROM no_trades WHERE fase=1 AND verwijderd_op IS NULL "
            "ORDER BY datum, id").fetchall()]
        shots = {}
        for r in conn.execute(
                "SELECT * FROM screenshots ORDER BY id").fetchall():
            d = dict(r)
            sleutel = ("t", d["trade_id"]) if d["trade_id"] else ("n", d["no_trade_id"])
            shots.setdefault(sleutel, []).append(d)

    genomen = [t for t in trades if t["status"] == "genomen"]
    winst = [t for t in genomen if (t.get("resultaat_eur") or 0) > 0]
    netto = sum((t.get("resultaat_eur") or 0) + (t.get("charges") or 0) for t in genomen)
    per_grade = {}
    for t in genomen:
        per_grade[t["grade"]] = per_grade.get(t["grade"], 0) + 1

    for t in trades:
        t["screenshots"] = shots.get(("t", t["id"]), [])
    for n in no_trades:
        n["screenshots"] = shots.get(("n", n["id"]), [])

    return {
        "trades": trades,
        "no_trades": no_trades,
        "criteria": cbr.CRITERIA_F1,
        "samenvatting": {
            "aantal": len(genomen),
            "overgeslagen": len([t for t in trades if t["status"] == "overgeslagen"]),
            "no_trades": len(no_trades),
            "winrate": round(100 * len(winst) / len(genomen), 1) if genomen else 0,
            "netto": round(netto, 2),
            "per_grade": per_grade,
            "van": min([t["datum"] for t in trades], default=""),
            "tot": max([t["datum"] for t in trades], default=""),
        },
    }

@app.get("/")
def index():
    return _pagina("index.html")


@app.get("/trade")
def trade_page():
    return _pagina("trade.html")


@app.get("/notrade")
def notrade_page():
    return RedirectResponse("/")   # no-trade loggen is eruit (23 sep)


@app.get("/week")
def week_page():
    return _pagina("week.html")


@app.get("/snel")
def snel_page():
    return _pagina("snel.html")


@app.get("/fouten")
def fouten_page():
    return _pagina("fouten.html")


@app.get("/regels")
def regels_page():
    return _pagina("regels.html")


@app.get("/dashboard")
def dashboard_page():
    return _pagina("dashboard.html")


@app.get("/kalender")
def kalender_page():
    return _pagina("kalender.html")


@app.get("/notities")
def notities_page():
    return RedirectResponse("/")   # notitieboek is eruit (23 sep)


@app.get("/rapport")
def rapport_page():
    return RedirectResponse("/")   # rapportkaart is eruit (23 sep)


@app.get("/setups")
def setups_page():
    return _pagina("setups.html")


@app.get("/prullenbak")
def prullenbak_page():
    return RedirectResponse("/")   # prullenbak is eruit (23 sep)


_prullenbak_opruimen()   # fase 16.1 -- ouder dan 30 dagen is echt weg


@app.get("/nieuw")
def nieuw_page():
    return _pagina("nieuw.html")


@app.get("/log")
def log_page():
    return _pagina("log.html")


@app.get("/archief")
def archief_page():
    """Fase 1 -- het oude sweep-en-draai model. Alleen lezen."""
    return _pagina("archief.html")


@app.get("/guide")
def guide_page():
    """Visuele referentie voor de type 3 shift -- statische pagina, geen data."""
    return _pagina("guide.html")


@app.get("/trainer")
def trainer_page():
    """Setup Trainer: 50 oefencharts, buy/sell/wait-out."""
    return _pagina("trainer.html")


# --- blok 2/3 + foto-logboek: extra routers ---

# Wachtwoordpoort (blok 7, VPS). Alleen actief als JOURNAL_WACHTWOORD gezet
# is als omgevingsvariabele -- op je laptop staat die niet, dus daar blijft
# alles gewoon open. Op een server met een publiek IP zet je hem WEL.
try:
    from beveiliging import zet_wachtwoord_op
    zet_wachtwoord_op(app)
except Exception as _e:
    print("[journal] wachtwoordpoort niet geladen:", _e)

# De modules staan in de hoofdmap (naast cbr_journal.db), niet in app/.
# Ze worden hier ingehaakt NA alle bestaande routes, zodat er niets gekaapt wordt.
# Elk blok apart: valt er een weg (ontbrekend pakket, geen API-sleutel), dan
# blijft de rest van de journal gewoon draaien.
import sys as _sys, os as _os
_HOOFDMAP = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _HOOFDMAP not in _sys.path:
    _sys.path.insert(0, _HOOFDMAP)

# Pre-trade kaart (voorbereiding) is eruit gesloopt op verzoek (23 sep 2026).
# Code staat in _archief_py/pretrade.py als je 'm ooit terug wilt.
# from pretrade import router as _pretrade_router
# app.include_router(_pretrade_router)

try:
    from weekgetallen import router as _weekgetallen_router   # GET /hoe-sta-ik-ervoor
    app.include_router(_weekgetallen_router)
except Exception as _e:                                  # pragma: no cover
    print("[journal] weekgetallen niet geladen:", _e)

try:
    from foto_logboek import router as _foto_router      # /logboek/foto
    app.include_router(_foto_router)
except Exception as _e:                                  # pragma: no cover
    print("[journal] foto-logboek niet geladen:", _e)


# --- MT5-koppeling, beoordelen, journal-bot en export (22 sep 2026) ---
# De journal leest je gesloten trades zelf uit MetaTrader 5 (alleen lezen,
# nooit handelen), de journal-bot vraagt je checks/criteria in Telegram, en
# /beoordelen + /export zijn de webpagina's erbij. Alles apart ingepakt:
# valt er één weg, dan draait de journal gewoon door.
try:
    from beoordelen import router as _beoordelen_router    # /beoordelen, /export, /api/mt5/*
    app.include_router(_beoordelen_router)
except Exception as _e:                                    # pragma: no cover
    print("[journal] beoordelen/export niet geladen:", _e)

def _charts_v21():
    try:
        import time as _t
        _t.sleep(20)
        with db.get_conn() as _c:
            if (db.get_settings(_c).get("v21_charts") or ""):
                return
        import trade_chart
        n = trade_chart.herteken_alles()
        with db.get_conn() as _c:
            db.set_setting(_c, "v21_charts", str(n))
        print(f"[journal] {n} trade-charts opnieuw getekend (v2.1)")
    except Exception as _e:  # pragma: no cover
        print("[journal] charts hertekenen mislukt:", _e)


if not os.environ.get("CBR_GEEN_MT5"):
    import threading as _th
    _th.Thread(target=_charts_v21, name="charts-v21", daemon=True).start()

try:
    import mt5_koppeling as _mt5
    import beoordelen as _beoord
    try:
        import journal_bot as _bot
        _bot.start_achtergrond()
    except Exception as _e:                                # pragma: no cover
        _bot = None
        print("[journal] Telegram journal-bot niet geladen:", _e)
    try:
        import signalen as _sig                          # de wachter, nu in de journal (23 sep)
    except Exception as _e:                              # pragma: no cover
        _sig = None
        print("[journal] signaalwachter niet geladen:", _e)
    if _sig is not None and _sig.router is not None:
        app.include_router(_sig.router)                  # /api/signalen, /api/signalen/replay
    try:
        import v3_labels as _v3                          # plan v3 fase 2 (7 okt 2026)
    except Exception as _e:                              # pragma: no cover
        _v3 = None
        print("[journal] v3-labels niet geladen:", _e)
    _koppeling = _mt5.start_achtergrond()
    if _koppeling is not None:
        def _na_nieuwe_trade(tid):
            _beoord.voorvullen(tid)          # venster + dagmax zijn feiten
            if _sig is not None:
                try:
                    _sig.koppel_trade(tid)   # hoort deze trade bij een signaal?
                except Exception as _e:
                    print("[journal] signaal koppelen mislukt:", _e)
            if _bot is not None:
                _bot.meld_trade(tid)         # bericht met de tien knoppen
            if _v3 is not None:
                try:
                    _v3.meld_trade(tid)      # plan v3 fase 2: TP-type en begin van de expansie
                except Exception as _e:
                    print("[journal] v3 trade-bericht mislukt:", _e)
        _koppeling.bij_nieuwe_trade.append(_na_nieuwe_trade)
        if _bot is not None:
            _koppeling.bij_waarschuwing.append(_bot.meld_tekst)   # o.a. verkeerd MT5-account
        if _sig is not None:
            _koppeling.na_ronde.append(_sig.na_ronde)
        if _v3 is not None:
            _koppeling.na_ronde.append(_v3.na_ronde)     # plan v3 fase 2: v3-signalen met labelknoppen
except Exception as _e:                                    # pragma: no cover
    print("[journal] MT5-koppeling niet gestart:", _e)
