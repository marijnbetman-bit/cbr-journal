# -*- coding: utf-8 -*-
"""
Importeert gelabelde signalen van de signaalwachter (VPS) in de CBR-journal.

Zet af en toe zelf een vers exemplaar van signalen.db (van de VPS) neer in:
    signalen-import/signalen.db

en draai dan (dubbelklik):
    importeer.bat

Wat er gebeurt met je Telegram-oordelen:
    👍 goede setup  -> concept-TRADE (fase 2, grade C), checklist op "?"
    👎 geen setup   -> NO-TRADE in de journal, met de poort die faalde
    🤔 twijfel      -> NO-TRADE in de journal, gemarkeerd als twijfel

Elke geimporteerde regel krijgt de marktsnapshot van dat moment (candles ->
SVG in je TradingView-kleuren). Zo kun je ook de slechte signalen visueel
terugkijken -- dat is precies de data waarmee je de wachter aanscherpt.

Al eerder geimporteerde signalen worden overgeslagen (bijgehouden in
signalen-import/geimporteerd.json), dus dit script is veilig om telkens
opnieuw te draaien nadat je een vers exemplaar hebt neergezet.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)

from app import db, cbr  # noqa: E402
import chart  # noqa: E402

IMPORT_DB = os.path.join(HIER, "signalen-import", "signalen.db")
STATE_PAD = os.path.join(HIER, "signalen-import", "geimporteerd.json")
SCREENSHOTS_DIR = os.path.join(HIER, "screenshots")

# Amsterdamse tijd, vaste +2 uur (zomertijd/CEST). Draai je dit nog in de
# winter, zet dan hieronder 2 op 1 (wintertijd).
UUR_VERSCHIL = 2

# Welke poort faalde volgens jou (👎 -> keuze in Telegram) -> leesbare tekst.
POORT_TEKST = {
    "bias": "bias klopte niet",
    "expansie": "geen echte expansie",
    "sweep": "geen sweep",
    "shift": "geen type-3 shift",
    "entry": "entry/50% klopte niet",
    "anders": "iets anders",
}


def lees_state():
    if os.path.exists(STATE_PAD):
        with open(STATE_PAD, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def schrijf_state(sleutels):
    os.makedirs(os.path.dirname(STATE_PAD), exist_ok=True)
    with open(STATE_PAD, "w", encoding="utf-8") as f:
        json.dump(sorted(sleutels), f, ensure_ascii=False, indent=2)


def lokale_datum_tijd(ts_iso):
    dt = datetime.fromisoformat(ts_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt + timedelta(hours=UUR_VERSCHIL)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def _richting(rij):
    return rij["richting"] or {"buy": "long", "sell": "short"}.get(rij["actie"], "")


def _context_regels(rij):
    """Gemeenschappelijke context: bias/DXY, blokkade, toelichting, jouw notitie."""
    try:
        toelichting = json.loads(rij["toelichting"] or "[]")
    except (ValueError, TypeError):
        toelichting = []
    regels = [
        f"bias {rij['bias'] or '?'} - DXY {rij['dxy'] or '?'}"
        + ("" if rij["in_venster"] else "  (buiten venster)")
    ]
    if rij["blokkade"]:
        regels.append(f"gestopt bij: {rij['blokkade']}")
    regels.extend(f"- {r}" for r in toelichting[:3])
    opmerking = rij["opmerking"] if "opmerking" in rij.keys() else None
    if opmerking:
        regels.append(f"notitie via Telegram: {opmerking}")
    return regels


def maak_snapshot(rij, datum, tijd, richting, conn, trade_id=None, no_trade_id=None):
    """Tekent de candles van dit signaal als SVG en hangt hem aan trade of no-trade."""
    try:
        candles = json.loads(rij["candles"] or "[]")
    except (ValueError, TypeError):
        candles = []
    if not candles:
        return False
    svg = chart.maak_svg(
        candles, entry=rij["entry"], sl=rij["sl"], tp=rij["tp"],
        richting=richting, symbool=(rij["symbool"] or "XAUUSD"),
        tier=rij["tier"] or "", kop_extra=f"{datum[5:]} {tijd}", rr=rij["rr"])
    daydir = os.path.join(SCREENSHOTS_DIR, datum)
    os.makedirs(daydir, exist_ok=True)
    soort = "trade" if trade_id else "notrade"
    fname = f"wachter_{soort}_{trade_id or no_trade_id}.svg"
    with open(os.path.join(daydir, fname), "w", encoding="utf-8") as f:
        f.write(svg)
    pad = f"screenshots/{datum}/{fname}"
    conn.execute(
        "INSERT INTO screenshots (trade_id, no_trade_id, pad, beschrijving, type) "
        "VALUES (?,?,?,?,?)",
        (trade_id, no_trade_id, pad, "Marktsnapshot op signaalmoment (automatisch)", "entry"))
    return True


def maak_trade_payload(rij, datum, tijd, richting):
    genomen = rij["genomen"] == 1
    notitie_regels = [
        f"Automatisch geimporteerd vanuit de signaalwachter (signaal #{rij['id']}, "
        f"tier {rij['tier']})."
    ] + _context_regels(rij)

    # Alle checklist-vinkjes op "?" (maybe): fase-1-crits zijn NOT NULL en moeten
    # gevuld, en fase-2 op maybe zorgt dat de grade op C ("nog beoordelen") begint.
    vinkjes = {k: "maybe" for k in (
        "crit1_conditie", "crit2_sweep", "crit3_shift", "crit4_entry", "crit5_tp",
        "f2_bias", "f2_dxy", "f2_expansie", "f2_sweep", "f2_shift",
        "f2_entry", "f2_sl", "f2_tp")}

    payload = dict(
        **vinkjes,
        datum=datum, tijd_entry=tijd,
        instrument=(rij["symbool"] or "XAUUSD").rstrip("+"),
        sessie="2e uur Londen", richting=richting,
        rr=rij["rr"], entry=rij["entry"], sl=rij["sl"], tp=rij["tp"],
        status="genomen" if genomen else "overgeslagen",
        skip_reden="" if genomen else
        "signaal gemarkeerd als goede setup, niet genomen (wachter)",
        bron="live", fase=cbr.FASE_ACTIEF,
        resultaat_eur=rij["resultaat_eur"] if genomen else None,
        charges=-0.06 if genomen else None,
        tags="wachter",
        bias_1hr=rij["bias"] or "", dxy_richting=rij["dxy"] or "",
        notities="\n".join(notitie_regels),
    )
    payload["grade"] = cbr.compute_grade_f2(payload)
    return payload


def maak_no_trade(rij, datum, tijd, oordeel, conn):
    """👎/🤔 wordt een no-trade in de journal, met poort-reden en context."""
    if oordeel == "twijfel":
        reden = "Wachter: twijfel over de setup"
    else:
        poort = POORT_TEKST.get(rij["fout_poort"] if "fout_poort" in rij.keys() else None)
        reden = "Wachter: geen geldige setup" + (f" ({poort})" if poort else "")
    wat_zag_ik = f"signaal #{rij['id']}, tier {rij['tier']}, {_richting(rij) or '-'}\n" \
                 + "\n".join(_context_regels(rij))
    cur = conn.execute(
        "INSERT INTO no_trades (datum, tijd, reden, wat_zag_ik, fase) VALUES (?,?,?,?,2)",
        (datum, tijd, reden, wat_zag_ik))
    return cur.lastrowid


def maak_snapshot_handmatig(candles_json, datum, tijd, richting, symbool, conn,
                            trade_id, entry=None, sl=None, tp=None, rr=None):
    """Tekent de bewaarde candles van een Telegram /trade als SVG en hangt hem
    aan de trade. Tekent entry/SL/TP-lijnen als je die bij /trade meegaf."""
    try:
        candles = json.loads(candles_json or "[]")
    except (ValueError, TypeError):
        candles = []
    if not candles:
        return False
    svg = chart.maak_svg(
        candles, entry=entry, sl=sl, tp=tp, rr=rr,
        richting=richting or "", symbool=(symbool or "XAUUSD"),
        kop_extra=f"{datum[5:]} {tijd}  (handmatig)")
    daydir = os.path.join(SCREENSHOTS_DIR, datum)
    os.makedirs(daydir, exist_ok=True)
    fname = f"wachter_handmatig_{trade_id}.svg"
    with open(os.path.join(daydir, fname), "w", encoding="utf-8") as f:
        f.write(svg)
    pad = f"screenshots/{datum}/{fname}"
    conn.execute(
        "INSERT INTO screenshots (trade_id, no_trade_id, pad, beschrijving, type) "
        "VALUES (?,?,?,?,?)",
        (trade_id, None, pad, "Marktsnapshot rond je log-moment (automatisch)", "entry"))
    return True


# De vijf pre-trade checks zoals de wachter ze in Telegram vraagt (achteraf).
HANDMATIG_CHECKS = ["check_venster", "check_dagmax", "check_bias", "check_entry50", "check_sl"]


def importeer_handmatige(bron, conn, al_binnen):
    """Haalt /trade-meldingen (handmatige_trades) uit de wachter-db naar de journal,
    inclusief de vijf pre-trade vinkjes die je achteraf in Telegram invulde.
    Geeft het aantal nieuw geimporteerde trades terug."""
    tabellen = {r[0] for r in bron.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "handmatige_trades" not in tabellen:
        return 0
    kolommen = {r[1] for r in bron.execute("PRAGMA table_info(handmatige_trades)")}
    rijen = bron.execute("SELECT * FROM handmatige_trades ORDER BY id").fetchall()

    vinkjes = {k: "maybe" for k in (
        "crit1_conditie", "crit2_sweep", "crit3_shift", "crit4_entry", "crit5_tp",
        "f2_bias", "f2_dxy", "f2_expansie", "f2_sweep", "f2_shift",
        "f2_entry", "f2_sl", "f2_tp")}

    n = 0
    for rij in rijen:
        key = f"hm:{rij['id']}"
        if key in al_binnen:
            continue
        # de vijf checks uitlezen (kunnen deels leeg zijn als je niet alles tikte)
        checks = {k: (rij[k] if k in kolommen else None) for k in HANDMATIG_CHECKS}
        alle_ja = all(checks[k] == 1 for k in HANDMATIG_CHECKS)
        gemist = [k.replace("check_", "") for k in HANDMATIG_CHECKS if checks[k] == 0]
        notitie = rij["notities"] or ""
        extra = ("\nPre-trade: alle vijf akkoord (schone trade)." if alle_ja
                 else (f"\nPre-trade: {', '.join(gemist)} stond(en) op nee."
                       if gemist else ""))
        # entry/sl/tp als je ze bij /trade meegaf; rr eruit berekenen als het kan
        entry = rij["entry"] if "entry" in kolommen else None
        sl_p  = rij["sl"] if "sl" in kolommen else None
        tp_p  = rij["tp"] if "tp" in kolommen else None
        rr = None
        if entry is not None and sl_p is not None and tp_p is not None and entry != sl_p:
            rr = round(abs(tp_p - entry) / abs(entry - sl_p), 2)
        # de vijf CBR-criteria uit de tweede Telegram-ronde overnemen (bepalen de grade)
        for kol in ("f2_bias", "f2_dxy", "f2_expansie", "f2_sweep", "f2_shift"):
            if kol in kolommen and rij[kol] in ("yes", "no"):
                vinkjes[kol] = rij[kol]
        payload = dict(
            **vinkjes,
            datum=rij["datum"], tijd_entry=rij["tijd_entry"] or "",
            instrument="XAUUSD", sessie="2e uur Londen",
            richting=rij["richting"] or "", status="genomen",
            resultaat_eur=rij["resultaat_eur"], charges=rij["charges"],
            lot=rij["lot"], entry=entry, sl=sl_p, tp=tp_p, rr=rr,
            bron="live", fase=cbr.FASE_ACTIEF,
            tags="wachter,handmatig",
            notities=("Via Telegram /trade gelogd." + extra
                      + (f"\n{notitie}" if notitie else "")),
        )
        payload["grade"] = cbr.compute_grade_f2(payload)
        tid = db._insert_trade(conn, payload)
        # de check-kolommen staan niet in TRADE_FIELDS -> los bijwerken
        conn.execute(
            "UPDATE trades SET check_venster=?, check_dagmax=?, check_bias=?, "
            "check_entry50=?, check_sl=?, schoon=?, checks_vooraf=? WHERE id=?",
            (checks["check_venster"], checks["check_dagmax"], checks["check_bias"],
             checks["check_entry50"], checks["check_sl"],
             1 if alle_ja else 0,
             1 if any(checks[k] is not None for k in HANDMATIG_CHECKS) else 0,
             tid))
        # marktsnapshot tekenen als de wachter candles bij deze trade bewaarde
        if "candles" in kolommen:
            try:
                maak_snapshot_handmatig(rij["candles"], rij["datum"],
                                        rij["tijd_entry"] or "", rij["richting"],
                                        "XAUUSD", conn, tid,
                                        entry=entry, sl=sl_p, tp=tp_p, rr=rr)
            except Exception as e:
                print(f"  (snapshot voor handmatige trade #{tid} overgeslagen: {e})")
        al_binnen.add(key)
        n += 1
    return n


def main():
    if not os.path.exists(IMPORT_DB):
        print(f"Geen bestand gevonden op:\n  {IMPORT_DB}")
        print("Kopieer eerst signalen.db van de VPS naar de map signalen-import/.")
        return

    al_binnen = lees_state()

    bron = sqlite3.connect(IMPORT_DB)
    bron.row_factory = sqlite3.Row
    rijen = bron.execute(
        """SELECT s.*, l.oordeel, l.genomen, l.resultaat_eur, l.fout_poort, l.opmerking
           FROM signalen s JOIN labels l ON l.signaal_id = s.id
           WHERE l.oordeel IN ('goed','niet','twijfel')
             AND s.sleutel NOT LIKE 'TEST%'
           ORDER BY s.ts"""
    ).fetchall()
    bron.close()

    nieuw = [r for r in rijen if r["sleutel"] not in al_binnen]

    # Handmatige /trade-meldingen apart importeren -- ook als er geen nieuwe
    # signalen zijn (je logt vaak wel een trade zonder dat er een signaal was).
    hbron = sqlite3.connect(IMPORT_DB); hbron.row_factory = sqlite3.Row
    with db.get_conn() as conn:
        n_handmatig = importeer_handmatige(hbron, conn, al_binnen)
    hbron.close()

    if not nieuw and not n_handmatig:
        schrijf_state(al_binnen)
        print(f"Niks nieuws. {len(rijen)} eerder gelabelde signalen stonden al binnen.")
        return
    if n_handmatig:
        print(f"{n_handmatig} handmatige /trade-melding(en) uit Telegram geimporteerd "
              f"(met je pre-trade vinkjes).")

    n_genomen = n_overgeslagen = n_notrade = n_charts = 0
    with db.get_conn() as conn:
        for rij in nieuw:
            datum, tijd = lokale_datum_tijd(rij["ts"])
            richting = _richting(rij)
            oordeel = rij["oordeel"]

            if oordeel == "goed":
                payload = maak_trade_payload(rij, datum, tijd, richting)
                tid = db._insert_trade(conn, payload)
                gemaakt = maak_snapshot(rij, datum, tijd, richting, conn, trade_id=tid)
                if payload["status"] == "genomen":
                    n_genomen += 1
                else:
                    n_overgeslagen += 1
            else:
                ntid = maak_no_trade(rij, datum, tijd, oordeel, conn)
                gemaakt = maak_snapshot(rij, datum, tijd, richting, conn, no_trade_id=ntid)
                n_notrade += 1

            if gemaakt:
                n_charts += 1
            al_binnen.add(rij["sleutel"])

    schrijf_state(al_binnen)
    print(f"{len(nieuw)} nieuwe signaal-regel(s) geimporteerd:")
    print(f"  {n_genomen} genomen trade(s), {n_overgeslagen} overgeslagen trade(s)")
    print(f"  {n_notrade} no-trade(s) uit 👎/🤔 -- de data om de wachter aan te scherpen")
    print(f"  {n_charts} marktsnapshot(s) getekend en gekoppeld")
    print("\nGoede setups staan op grade C tot je de fase-2-checklist afvinkt.")


if __name__ == "__main__":
    main()
