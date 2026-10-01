# -*- coding: utf-8 -*-
"""
beoordelen.py -- je 5 checks + 5 CBR-criteria bij automatisch binnengekomen
trades, plus de MT5-status en de exports.

Eén logica voor twee ingangen: de journal-bot in Telegram en de pagina
/beoordelen (telefoon-vriendelijk). Beide roepen zet_antwoord() aan; de grade
wordt daarna opnieuw uitgerekend met dezelfde functie als de rest van de
journal (cbr.compute_grade_f2). Nooit handmatig.

Afgeleid (zodat een A haalbaar is zonder het grote formulier):
    f2_entry  = je check 'entry op 50%'
    f2_sl     = je check 'SL 5+ points voorbij de sweep'
    f2_tp     = RR >= je RR-vloer (1,0) -- alleen als de TP bekend is

Routes:
    GET  /beoordelen                 de pagina
    GET  /api/beoordelen             trades die op je wachten (+ vandaag)
    POST /api/beoordeel/{id}         één antwoord of een notitie opslaan
    GET  /api/mt5/status             draait de koppeling?
    POST /api/mt5/sync-nu            nu meteen kijken in MT5
    GET  /export                     exportpagina
    GET  /export/trades.csv          trades voor Excel
    GET  /export/journal.html        je journal als los bestand, overal te openen
"""

import csv
import html
import io
import json
import os
import sqlite3
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

HIER = os.path.dirname(os.path.abspath(__file__))
DB_PAD = os.path.join(HIER, "cbr_journal.db")
CONFIG_PAD = os.path.join(HIER, "journal_config.json")

router = APIRouter()

# ------------------------------------------------------------------ model (v2, 29 sep 2026)
# Het bias-vrije model. Bias/DXY/type-3 zijn eruit.
#   SETUP  (bepaalt de grade)      -> 'yes' / 'no' / 'maybe'
#   DISCIPLINE (bepaalt 'schoon')  -> 1 / 0 / None, grotendeels automatisch uit MT5
#   MENS   emotie vooraf, uitvoering 1-5, 'zou ik hem opnieuw nemen', les
CRITERIA = [
    ("s_impuls", "Impuls valide (≥4 candles, ≥4×ATR, breekt vorige 1H)"),
    ("s_top", "Kleine top + mini-pullback"),
    ("s_sweep", "Sweep ≤30 pts door de top"),
    ("s_bos", "BOS: candle sluit voorbij de pullback-low"),
    ("f2_entry", "Entry op 50% (sweep ↔ BOS)"),
    ("f2_sl", "SL 5+ pts voorbij de sweep"),
]
AUTO_CRIT = ("f2_tp", "TP op 1:1 (uit MT5)")
KRITISCH = ("s_impuls", "s_sweep", "s_bos")
CHECKS = [
    ("check_venster", "Binnen je venster"),
    ("check_dagmax", "Binnen je dagmaximum"),
    ("check_sl_vast", "SL niet verschoven"),
    ("check_beheer", "Laten lopen tot SL/TP"),
]
EMOTIES = [
    ("rustig", "😌 rustig", "goed"), ("gefocust", "🎯 gefocust", "goed"),
    ("twijfel", "🤔 twijfel", "let-op"), ("gehaast", "⏱ gehaast", "let-op"),
    ("fomo", "😬 FOMO", "slecht"), ("revenge", "😤 revenge", "slecht"),
    ("moe", "😴 moe", "let-op"),
]
EMOTIE_KEYS = [e[0] for e in EMOTIES]
MENS_VELDEN = ("emotie_voor", "uitvoering", "opnieuw", "les", "foutcodes")
FOUTTAGS = ["te vroeg ingestapt", "niet op 50% gewacht", "te vroeg gesloten",
            "SL te krap", "geen echte BOS", "impuls te zwak", "tegen de regels in",
            "revenge / na verlies", "overtrading", "twijfelde maar deed het toch"]

CHECK_KEYS = [k for k, _ in CHECKS]
CRIT_KEYS = [k for k, _ in CRITERIA]
AUTO_KEYS = ("check_venster", "check_dagmax", "check_sl_vast", "check_beheer")
# oude fase-2 lijsten, alleen voor trades die al in het oude model beoordeeld zijn
OUD_CHECK_KEYS = ["check_venster", "check_dagmax", "check_bias", "check_entry50", "check_sl"]
OUD_CRIT_KEYS = ["f2_bias", "f2_dxy", "f2_expansie", "f2_sweep", "f2_shift"]


def _cfg():
    try:
        with open(CONFIG_PAD, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _conn(pad=None):
    con = sqlite3.connect(pad or DB_PAD, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def _min(hhmm):
    try:
        u, m = str(hhmm).split(":")[:2]
        return int(u) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


# ------------------------------------------------------------------ logica

def grade_biasvrij(v):
    """C = een kritisch punt (impuls, sweep, BOS) niet ja. A = alles ja
    (incl. TP 1:1 als die bekend is). Anders B."""
    if any(v.get(k) != "yes" for k in KRITISCH):
        return "C"
    alle = CRIT_KEYS + (["f2_tp"] if v.get("f2_tp") in ("yes", "no") else [])
    if all(v.get(k) == "yes" for k in alle):
        return "A"
    return "B"


def _herbereken_oud(con, v):
    from app import cbr
    zet = {}
    if v.get("check_entry50") is not None:
        zet["f2_entry"] = "yes" if v["check_entry50"] == 1 else "no"
    if v.get("check_sl") is not None:
        zet["f2_sl"] = "yes" if v["check_sl"] == 1 else "no"
    v.update(zet)
    checks_vol = all(v.get(k) is not None for k in OUD_CHECK_KEYS)
    crit_vol = all(v.get(k) in ("yes", "no") for k in OUD_CRIT_KEYS)
    zet["schoon"] = (1 if all(v.get(k) == 1 for k in OUD_CHECK_KEYS) else 0) if checks_vol else None
    zet["grade"] = cbr.compute_grade_f2(v)
    if v.get("beoordeeld") is not None or checks_vol or crit_vol:
        zet["beoordeeld"] = 1 if (checks_vol and crit_vol) else 0
    return zet


def herbereken(con, tid):
    """Afgeleide criteria, schoon-vlag, grade, proces-score en 'beoordeeld'."""
    t = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
    if t is None:
        return None
    v = dict(t)
    if v.get("model") != "biasvrij":
        zet = _herbereken_oud(con, v)
    else:
        zet = {}
        if v.get("f2_tp") in (None, "", "maybe") and v.get("rr") is not None:
            min_rr = float((_cfg().get("mt5") or {}).get("min_rr", 1.0))
            zet["f2_tp"] = "yes" if v["rr"] >= min_rr - 0.05 else "no"
        v.update(zet)
        checks_vol = all(v.get(k) is not None for k in CHECK_KEYS)
        crit_vol = all(v.get(k) in ("yes", "no") for k in CRIT_KEYS)
        zet["schoon"] = (1 if all(v.get(k) == 1 for k in CHECK_KEYS) else 0) if checks_vol else None
        zet["grade"] = grade_biasvrij(v)
        # proces-score: aandeel 'goed' over setup + discipline (+ emotie)
        punten = [v.get(k) == "yes" for k in CRIT_KEYS if v.get(k) in ("yes", "no")]
        punten += [v.get(k) == 1 for k in CHECK_KEYS if v.get(k) is not None]
        if v.get("emotie_voor"):
            punten.append(v["emotie_voor"] in ("rustig", "gefocust"))
        zet["proces_score"] = round(100 * sum(punten) / len(punten)) if punten else None
        klaar = crit_vol and bool(v.get("emotie_voor"))
        zet["beoordeeld"] = 1 if klaar else 0
        if klaar and not v.get("beoordeeld_op"):
            zet["beoordeeld_op"] = datetime.now().isoformat(timespec="seconds")
    sets = ", ".join(f"{k}=?" for k in zet) + ", updated_at=datetime('now')"
    con.execute(f"UPDATE trades SET {sets} WHERE id=?", list(zet.values()) + [tid])
    con.commit()
    return dict(v, **zet)


def zet_antwoord(con, tid, sleutel, waarde):
    """sleutel = een check-kolom (1/0) of een setup-criterium ('yes'/'no')."""
    if sleutel in CHECK_KEYS or sleutel in OUD_CHECK_KEYS:
        w = None if waarde in (None, "", "leeg") else (1 if str(waarde) in ("1", "yes", "ja", "true") else 0)
    elif sleutel in CRIT_KEYS or sleutel in OUD_CRIT_KEYS or sleutel == "f2_tp":
        w = "maybe" if waarde in (None, "", "leeg") else ("yes" if str(waarde) in ("1", "yes", "ja", "true") else "no")
    else:
        raise ValueError(f"onbekend veld {sleutel}")
    con.execute(f"UPDATE trades SET {sleutel}=? WHERE id=?", (w, tid))
    return herbereken(con, tid)


def zet_mens(con, tid, veld, waarde):
    """Emotie, uitvoering (1-5), opnieuw nemen (1/0), les, fouttags."""
    if veld == "emotie_voor":
        w = waarde if waarde in EMOTIE_KEYS else None
    elif veld == "uitvoering":
        w = int(waarde) if str(waarde) in ("1", "2", "3", "4", "5") else None
    elif veld == "opnieuw":
        w = None if waarde in (None, "") else (1 if str(waarde) in ("1", "ja", "yes", "true") else 0)
    elif veld == "les":
        w = (waarde or "").strip()
    elif veld == "foutcodes":
        lijst = waarde if isinstance(waarde, list) else str(waarde or "").split(",")
        w = ",".join(x.strip() for x in lijst if x and x.strip())
    else:
        raise ValueError(f"onbekend veld {veld}")
    con.execute(f"UPDATE trades SET {veld}=?, updated_at=datetime('now') WHERE id=?", (w, tid))
    return herbereken(con, tid)


def zet_niveaus(con, tid, sl=None, tp=None):
    """SL/TP achteraf invullen (als MT5 ze niet zag): R, RR, risico en de chart
    worden opnieuw uitgerekend/getekend."""
    import mt5_koppeling as K
    t = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
    if t is None:
        raise ValueError("trade niet gevonden")
    t = dict(t)

    def getal(v, oud):
        if v in (None, ""):
            return oud
        return float(str(v).replace(",", "."))

    sl = getal(sl, t.get("sl_prijs"))
    tp = getal(tp, t.get("tp_prijs"))
    entry = t.get("entry_prijs") or t.get("entry")
    if entry is None:
        raise ValueError("geen entryprijs bekend")
    lang = t.get("richting") == "long"
    if sl is not None and ((lang and sl >= entry) or (not lang and sl <= entry)):
        raise ValueError(f"SL {sl} ligt aan de verkeerde kant van je entry {entry}")
    if tp is not None and ((lang and tp <= entry) or (not lang and tp >= entry)):
        raise ValueError(f"TP {tp} ligt aan de verkeerde kant van je entry {entry}")
    pos = {"entry": entry, "exit": t.get("exit_prijs"), "richting": t.get("richting"),
           "bruto": t.get("resultaat_eur") or 0, "open_ts": None, "dicht_ts": None}
    m = K.bereken(pos, sl, tp)
    zet = {"sl_prijs": sl, "tp_prijs": tp, "sl": sl, "tp": tp, "f2_tp": "maybe"}
    for k in ("sl_afstand_points", "tp_afstand_points", "rr", "risico_eur", "resultaat_r"):
        if m.get(k) is not None:
            zet[k] = m[k]
    sets = ", ".join(f"{k}=?" for k in zet) + ", updated_at=datetime('now')"
    con.execute(f"UPDATE trades SET {sets} WHERE id=?", list(zet.values()) + [tid])
    con.commit()
    v = herbereken(con, tid)
    try:
        import trade_chart
        trade_chart.herteken(con, tid)
    except Exception as e:  # pragma: no cover
        print("[journal] chart hertekenen mislukt:", e)
    return v


def voeg_notitie_toe(con, tid, tekst):
    tekst = (tekst or "").strip()
    if not tekst:
        return
    oud = con.execute("SELECT notities FROM trades WHERE id=?", (tid,)).fetchone()
    nieuw = ((oud["notities"] or "").rstrip() + "\n" + tekst).strip() if oud else tekst
    con.execute("UPDATE trades SET notities=?, updated_at=datetime('now') WHERE id=?", (nieuw, tid))
    con.commit()


def auto_feiten(con, tid):
    """Wat MT5 al weet, vullen we zelf in (jij kunt het altijd omzetten):
    venster, dagmaximum, SL verschoven, laten lopen tot SL/TP, en -- als de
    signaalwachter deze setup vond -- de vier setup-punten van de detector."""
    jc = _cfg()
    t = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
    if t is None:
        return
    t = dict(t)
    zet = {}
    if t.get("model") is None and t.get("beoordeeld") in (None, 0):
        zet["model"] = "biasvrij"
    import venster as _venster          # blokken-lijst (Asia + 10-15), 1 okt 2026
    tm = _min(t["tijd_entry"])
    if t.get("check_venster") is None and tm is not None:
        zet["check_venster"] = 1 if _venster.binnen(tm, jc) else 0
    if t.get("check_dagmax") is None:
        eerder = 0
        for r in con.execute(
                "SELECT id, tijd_entry FROM trades WHERE datum=? AND id!=? AND verwijderd_op IS NULL "
                "AND (status IS NULL OR status='genomen')", (t["datum"], tid)):
            tr = _min(r["tijd_entry"])
            if (tr is not None and tm is not None and tr < tm) or (tr == tm and r["id"] < tid):
                eerder += 1
        zet["check_dagmax"] = 1 if eerder + 1 <= int(jc.get("dagmaximum", 2)) else 0
    if t.get("check_sl_vast") is None and t.get("positie_id"):
        p = con.execute("SELECT eerste_sl, laatste_sl FROM mt5_posities WHERE positie_id=?",
                        (t["positie_id"],)).fetchone()
        if p is not None and p["eerste_sl"] is not None and p["laatste_sl"] is not None:
            zet["check_sl_vast"] = 0 if abs(p["eerste_sl"] - p["laatste_sl"]) > 0.5 else 1
        elif t.get("sl_prijs") is not None:
            zet["check_sl_vast"] = 1
    if t.get("check_beheer") is None and t.get("exit_reden"):
        er = t["exit_reden"].lower()
        if "sl geraakt" in er or "tp geraakt" in er:
            zet["check_beheer"] = 1
        elif "handmatig" in er or "stop-out" in er:
            zet["check_beheer"] = 0
    if t.get("signaal_id"):
        for k in ("s_impuls", "s_top", "s_sweep", "s_bos"):
            if (t.get(k) or "maybe") == "maybe":
                zet[k] = "yes"
    if zet:
        sets = ", ".join(f"{k}=?" for k in zet)
        con.execute(f"UPDATE trades SET {sets} WHERE id=?", list(zet.values()) + [tid])
    herbereken(con, tid)


def voorvullen(tid, pad=None):
    con = _conn(pad)
    try:
        _zorg(con)
        auto_feiten(con, tid)
    finally:
        con.close()


def trade_json(t, con=None):
    t = dict(t)
    chart = None
    if con is not None:
        r = con.execute("SELECT pad FROM screenshots WHERE trade_id=? ORDER BY id LIMIT 1",
                        (t["id"],)).fetchone()
        chart = "/" + r["pad"] if r else None
        if chart:
            try:
                chart += "?v=" + str(int(os.path.getmtime(os.path.join(HIER, r["pad"]))))
            except OSError:
                pass
    sl = t.get("sl_afstand_points")
    return {
        "id": t["id"], "datum": t["datum"], "tijd": t.get("tijd_entry"),
        "tijd_exit": t.get("tijd_exit"), "richting": t.get("richting"),
        "resultaat": t.get("resultaat_eur"), "charges": t.get("charges"),
        "r": t.get("resultaat_r"), "rr": t.get("rr"), "exit_reden": t.get("exit_reden"),
        "sl_points": sl, "lot": t.get("lot"), "duur": t.get("duur_minuten"),
        "entry": t.get("entry_prijs") or t.get("entry"), "exit": t.get("exit_prijs"),
        "sl_prijs": t.get("sl_prijs"), "tp_prijs": t.get("tp_prijs"),
        "mfe_r": round(t["mfe_points"] / sl, 2) if t.get("mfe_points") is not None and sl else None,
        "mae_r": round(t["mae_points"] / sl, 2) if t.get("mae_points") is not None and sl else None,
        "grade": t.get("grade"), "beoordeeld": t.get("beoordeeld"), "model": t.get("model"),
        "schoon": t.get("schoon"), "proces_score": t.get("proces_score"),
        "notities": t.get("notities") or "", "les": t.get("les") or "",
        "positie_id": t.get("positie_id"), "signaal_id": t.get("signaal_id"), "chart": chart,
        "emotie_voor": t.get("emotie_voor"), "uitvoering": t.get("uitvoering"),
        "opnieuw": t.get("opnieuw"),
        "foutcodes": [x for x in (t.get("foutcodes") or "").split(",") if x.strip()],
        "checks": {k: t.get(k) for k in CHECK_KEYS},
        "criteria": {k: t.get(k) for k in CRIT_KEYS + ["f2_tp"]},
    }


def _zorg(con):
    try:
        import mt5_koppeling
        mt5_koppeling.zorg_schema(con)
    except Exception:
        pass
    try:
        from app import saldo
        saldo.zorg_trade_kolommen(con)
    except Exception:
        pass


# ------------------------------------------------------------------ API

@router.get("/api/beoordelen")
def api_lijst():
    con = _conn()
    try:
        _zorg(con)
        ids = [r[0] for r in con.execute(
            "SELECT id FROM trades WHERE beoordeeld=0 AND verwijderd_op IS NULL")]
        for tid in ids:
            auto_feiten(con, tid)
        open_ = con.execute(
            "SELECT * FROM trades WHERE beoordeeld=0 AND verwijderd_op IS NULL "
            "ORDER BY datum DESC, tijd_entry DESC").fetchall()
        vandaag = con.execute(
            "SELECT * FROM trades WHERE datum=? AND (beoordeeld IS NULL OR beoordeeld=1) "
            "AND verwijderd_op IS NULL AND (status IS NULL OR status='genomen') "
            "ORDER BY tijd_entry DESC", (date.today().isoformat(),)).fetchall()
        return {"open": [trade_json(t, con) for t in open_],
                "vandaag": [trade_json(t, con) for t in vandaag],
                "checks": CHECKS, "criteria": CRITERIA, "auto_crit": AUTO_CRIT,
                "kritisch": KRITISCH, "emoties": EMOTIES, "fouttags": FOUTTAGS}
    finally:
        con.close()


@router.post("/api/beoordeel/{tid}")
async def api_beoordeel(tid: int, request: Request):
    body = await request.json()
    con = _conn()
    try:
        if con.execute("SELECT 1 FROM trades WHERE id=?", (tid,)).fetchone() is None:
            raise HTTPException(404, "trade niet gevonden")
        _zorg(con)
        if "notitie" in body:
            voeg_notitie_toe(con, tid, body["notitie"])
        try:
            if "sleutel" in body:
                zet_antwoord(con, tid, body["sleutel"], body.get("waarde"))
            if "veld" in body:
                zet_mens(con, tid, body["veld"], body.get("waarde"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        t = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
        return trade_json(t, con)
    finally:
        con.close()


@router.post("/api/trade/{tid}/niveaus")
async def api_niveaus(tid: int, request: Request):
    body = await request.json()
    con = _conn()
    try:
        _zorg(con)
        try:
            zet_niveaus(con, tid, body.get("sl"), body.get("tp"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        t = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
        return trade_json(t, con)
    finally:
        con.close()


@router.post("/api/charts/herteken")
def api_herteken_alles():
    import trade_chart
    return {"hertekend": trade_chart.herteken_alles()}


@router.get("/api/mt5/status")
def api_mt5_status():
    try:
        import mt5_koppeling
        s = mt5_koppeling.status()
    except Exception as e:
        s = {"verbonden": False, "melding": f"koppeling niet geladen: {e}"}
    try:
        import journal_bot
        s["telegram"] = journal_bot.status()
    except Exception as e:
        s["telegram"] = {"actief": False, "melding": str(e)}
    return s


@router.post("/api/mt5/sync-nu")
def api_sync_nu():
    import mt5_koppeling
    k = mt5_koppeling.koppeling()
    if k is None:
        raise HTTPException(503, "koppeling draait niet")
    k.nu_synchroniseren()
    return {"ok": True}


# ------------------------------------------------------------------ exports

EXPORT_KOLOMMEN = [
    ("id", "#"), ("datum", "datum"), ("tijd_entry", "in"), ("tijd_exit", "uit"),
    ("richting", "richting"), ("lot", "lot"), ("entry", "entry"), ("sl", "SL"),
    ("tp", "TP"), ("exit_prijs", "exit"), ("sl_afstand_points", "SL pts"),
    ("rr", "RR"), ("resultaat_eur", "resultaat"), ("charges", "charges"),
    ("netto", "netto"), ("resultaat_r", "R"), ("exit_reden", "exit"),
    ("grade", "grade"), ("schoon", "schone trade"),
] + [(k, lbl) for k, lbl in CHECKS] + [(k, lbl) for k, lbl in CRITERIA] + [
    ("emotie_voor", "emotie"), ("uitvoering", "uitvoering"), ("opnieuw", "opnieuw nemen"),
    ("proces_score", "proces %"), ("les", "les"), ("foutcodes", "fouten"),
    ("mfe_points", "MFE pts"), ("mae_points", "MAE pts"), ("duur_minuten", "duur min"),
    ("sessie", "sessie"), ("tags", "tags"), ("notities", "notities"), ("positie_id", "MT5 positie"),
]


def _trades_voor_export(con, fase=None):
    _zorg(con)
    q = "SELECT * FROM trades WHERE verwijderd_op IS NULL AND (status IS NULL OR status='genomen')"
    args = []
    if fase:
        q += " AND fase=?"
        args.append(fase)
    rijen = [dict(r) for r in con.execute(q + " ORDER BY datum, tijd_entry, id", args)]
    for r in rijen:
        r["netto"] = round((r.get("resultaat_eur") or 0) + (r.get("charges") or 0), 2) \
            if r.get("resultaat_eur") is not None else None
    return rijen


def _nl(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}".replace(".", ",")
    return str(v)


@router.get("/export/trades.csv")
def export_csv(fase: int = 2):
    con = _conn()
    try:
        rijen = _trades_voor_export(con, fase or None)
    finally:
        con.close()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([lbl for _, lbl in EXPORT_KOLOMMEN])
    for r in rijen:
        w.writerow([_nl(r.get(k)) for k, _ in EXPORT_KOLOMMEN])
    naam = f"cbr-trades-{date.today().isoformat()}.csv"
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{naam}"'})


@router.get("/export/dataset.csv")
def export_dataset():
    """v2: gelabelde dataset (MT5-feiten + marktcontext + jouw oordeel) voor analyse/AI."""
    import marktdata
    try:
        marktdata.verrijk_trades()
    except Exception as e:  # pragma: no cover
        print("[journal] verrijken mislukt:", e)
    naam = f"cbr-dataset-{date.today().isoformat()}.csv"
    return Response("\ufeff" + marktdata.dataset_csv(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{naam}"'})


@router.get("/api/marktdata/status")
def api_marktdata_status():
    import marktdata
    return marktdata.status()


@router.get("/export/journal.html")
def export_html(fase: int = 2):
    import export_offline
    con = _conn()
    try:
        inhoud = export_offline.maak(con, _trades_voor_export(con, fase or None), HIER, fase)
    finally:
        con.close()
    naam = f"CBR-journal-{date.today().isoformat()}.html"
    return Response(inhoud, media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{naam}"'})


# ------------------------------------------------------------------ pagina's

def _pagina(naam):
    with open(os.path.join(HIER, "static", naam), encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-store"})


@router.get("/beoordelen")
def pagina_beoordelen():
    # v2: loggen gebeurt op de homepage ("Nog te loggen")
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/#te-loggen", status_code=307)


@router.get("/export", response_class=HTMLResponse)
def pagina_export():
    return _pagina("export.html")
