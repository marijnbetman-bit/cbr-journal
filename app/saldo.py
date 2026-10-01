# -*- coding: utf-8 -*-
"""
saldo.py -- je saldo klopt altijd, en je rendement wordt niet vervuild door stortingen.

    saldo = startkapitaal + netto van je journal-trades + kasstromen

Kasstromen (tabel `kasstromen`):
  storting    +   geld erbij (uit MT5 automatisch, of met de hand)
  opname      -   geld eraf
  correctie   +/- met de hand: "mijn saldo is nu X" (testtrades, oude rommel)
  aansluiting +/- automatisch per dag: wat MT5 zegt minus wat de journal weet.
                  Zo is het journal-saldo altijd gelijk aan MT5, en zie je
                  zwart op wit hoeveel er NIET uit gelogde trades komt.

Het rendement (%) rekent alleen trading mee: per dag resultaat / saldo aan het
begin van die dag, samengesteld. Een storting van 100 is dus geen +100% winst.
"""

from datetime import date, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS kasstromen (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    datum      TEXT NOT NULL,
    tijd       TEXT,
    soort      TEXT NOT NULL,            -- storting | opname | correctie | aansluiting
    bedrag     REAL NOT NULL,            -- met teken: + erbij, - eraf
    notitie    TEXT DEFAULT '',
    bron       TEXT DEFAULT 'handmatig', -- handmatig | mt5
    mt5_deal   INTEGER UNIQUE,           -- ticket van de balansdeal in MT5
    sleutel    TEXT UNIQUE,              -- 'aansluiting-2026-09-29'
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS mt5_account_log (
    ts           TEXT PRIMARY KEY,
    balance      REAL, equity REAL, margin REAL, margin_free REAL,
    margin_level REAL, profit REAL, n_posities INTEGER
);
"""

SOORTEN = ("storting", "opname", "correctie", "aansluiting")
TRADE_FILTER = ("status = 'genomen' AND verwijderd_op IS NULL AND fase = 2 "
                "AND bron = 'live'")


# v2 trade-kolommen: bias-vrije checklist, discipline uit MT5, de mens-kant.
V2_KOLOMMEN = {
    "s_impuls": "TEXT DEFAULT 'maybe'", "s_top": "TEXT DEFAULT 'maybe'",
    "s_sweep": "TEXT DEFAULT 'maybe'", "s_bos": "TEXT DEFAULT 'maybe'",
    "check_sl_vast": "INTEGER", "check_beheer": "INTEGER",
    "emotie_voor": "TEXT", "uitvoering": "INTEGER", "opnieuw": "INTEGER",
    "proces_score": "INTEGER", "model": "TEXT", "beoordeeld_op": "TEXT",
    # context voor analyse/AI (gevuld door dataset.py)
    "sessie_markt": "TEXT", "atr_m1": "REAL", "spread_entry": "REAL",
    "vorige_1h_high": "REAL", "vorige_1h_low": "REAL",
}


def zorg_trade_kolommen(con):
    have = {r[1] for r in con.execute("PRAGMA table_info(trades)")}
    for kol, typ in V2_KOLOMMEN.items():
        if kol not in have:
            con.execute(f"ALTER TABLE trades ADD COLUMN {kol} {typ}")
    for kol in ("positie_id", "beoordeeld", "resultaat_r", "mfe_points", "mae_points",
                "sl_afstand_points", "duur_minuten", "tijd_exit", "lot"):
        if kol not in have:
            con.execute(f"ALTER TABLE trades ADD COLUMN {kol} "
                        f"{'TEXT' if kol == 'tijd_exit' else 'REAL'}")


def zorg_schema(con):
    con.executescript(SCHEMA)
    zorg_trade_kolommen(con)


def _setting(con, key, standaard=None):
    r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r and r[0] not in (None, "") else standaard


def _set_setting(con, key, value):
    con.execute("INSERT INTO settings (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def startkapitaal(con):
    try:
        return float(_setting(con, "startkapitaal", 0) or 0)
    except ValueError:
        return 0.0


def trading_netto(con):
    r = con.execute("SELECT COALESCE(SUM(COALESCE(resultaat_eur,0)+COALESCE(charges,0)),0) "
                    "FROM trades WHERE " + TRADE_FILTER).fetchone()
    return round(float(r[0] or 0), 2)


def lijst(con):
    zorg_schema(con)
    return [dict(r) for r in con.execute(
        "SELECT * FROM kasstromen ORDER BY datum, COALESCE(tijd,''), id")]


def som_kasstromen(con, excl_sleutel=None):
    zorg_schema(con)
    if excl_sleutel:
        r = con.execute("SELECT COALESCE(SUM(bedrag),0) FROM kasstromen "
                        "WHERE sleutel IS NULL OR sleutel != ?", (excl_sleutel,)).fetchone()
    else:
        r = con.execute("SELECT COALESCE(SUM(bedrag),0) FROM kasstromen").fetchone()
    return round(float(r[0] or 0), 2)


def journal_saldo(con, excl_sleutel=None):
    return round(startkapitaal(con) + trading_netto(con) + som_kasstromen(con, excl_sleutel), 2)


def _teken(soort, bedrag):
    b = abs(float(bedrag))
    if soort == "storting":
        return b
    if soort == "opname":
        return -b
    return float(bedrag)


def voeg_toe(con, datum, soort, bedrag, notitie="", bron="handmatig",
             mt5_deal=None, tijd=None, sleutel=None):
    zorg_schema(con)
    if soort not in SOORTEN:
        raise ValueError(f"onbekende soort {soort}")
    date.fromisoformat(datum)
    cur = con.execute(
        "INSERT INTO kasstromen (datum, tijd, soort, bedrag, notitie, bron, mt5_deal, sleutel) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (datum, tijd, soort, round(_teken(soort, bedrag), 2), notitie or "", bron,
         mt5_deal, sleutel))
    return cur.lastrowid


def verwijder(con, kid):
    con.execute("DELETE FROM kasstromen WHERE id=?", (kid,))


def zet_saldo(con, doel, datum=None, notitie=""):
    """'Mijn saldo is nu X' -> één correctieregel voor het verschil."""
    datum = datum or date.today().isoformat()
    verschil = round(float(doel) - journal_saldo(con), 2)
    if abs(verschil) < 0.005:
        return None, 0.0
    kid = voeg_toe(con, datum, "correctie", verschil,
                   notitie or f"Saldo gelijkgezet op € {float(doel):.2f}".replace(".", ","))
    return kid, verschil


# ------------------------------------------------------------------ MT5

BALANS_TYPES = {2: "balans", 3: "credit", 4: "charge", 5: "correctie", 6: "bonus",
                7: "commissie", 8: "commissie", 9: "commissie", 10: "commissie",
                11: "rente", 12: "correctie", 13: "correctie", 15: "dividend", 18: "belasting"}


def importeer_balansdeal(con, ticket, datum, tijd, bedrag, deal_type, comment=""):
    """Een storting/opname uit MT5. Stond hij er al met de hand (zelfde dag,
    zelfde bedrag), dan koppelen we i.p.v. dubbel te boeken."""
    zorg_schema(con)
    if con.execute("SELECT 1 FROM kasstromen WHERE mt5_deal=?", (ticket,)).fetchone():
        return None
    bedrag = round(float(bedrag), 2)
    if abs(bedrag) < 0.005:
        return None
    match = con.execute(
        "SELECT id FROM kasstromen WHERE mt5_deal IS NULL AND sleutel IS NULL "
        "AND soort IN ('storting','opname') AND datum=? AND ABS(bedrag-?)<0.011 "
        "ORDER BY id LIMIT 1", (datum, bedrag)).fetchone()
    if match:
        con.execute("UPDATE kasstromen SET mt5_deal=?, tijd=COALESCE(tijd,?), "
                    "notitie=TRIM(COALESCE(notitie,'')||' (bevestigd door MT5)') WHERE id=?",
                    (ticket, tijd, match[0]))
        return match[0]
    if deal_type == 2:
        soort = "storting" if bedrag > 0 else "opname"
    else:
        soort = "correctie"
    notitie = f"MT5 {BALANS_TYPES.get(deal_type, 'balans')}" + (f": {comment}" if comment else "")
    return voeg_toe(con, datum, soort, bedrag, notitie, bron="mt5", mt5_deal=ticket, tijd=tijd)


def aansluiten(con, mt5_balans, datum=None):
    """Journal-saldo gelijk trekken met MT5 via één aansluitingsregel per dag."""
    zorg_schema(con)
    datum = datum or date.today().isoformat()
    sleutel = f"aansluiting-{datum}"
    zonder = journal_saldo(con, excl_sleutel=sleutel)
    verschil = round(float(mt5_balans) - zonder, 2)
    bestaat = con.execute("SELECT id, bedrag FROM kasstromen WHERE sleutel=?", (sleutel,)).fetchone()
    if abs(verschil) < 0.01:
        if bestaat:
            con.execute("DELETE FROM kasstromen WHERE id=?", (bestaat[0],))
        return 0.0
    notitie = ("Automatisch: verschil tussen MT5-balans en je gelogde trades "
               "(testtrades, andere symbolen, niet-gesynchroniseerd)")
    if bestaat:
        if abs(bestaat[1] - verschil) >= 0.005:
            con.execute("UPDATE kasstromen SET bedrag=?, tijd=? WHERE id=?",
                        (verschil, datetime.now().strftime("%H:%M"), bestaat[0]))
    else:
        voeg_toe(con, datum, "aansluiting", verschil, notitie, bron="mt5",
                 tijd=datetime.now().strftime("%H:%M"), sleutel=sleutel)
    return verschil


def log_account(con, info, n_posities, min_interval_sec=300):
    """Snapshot van balans/equity/margin, hooguit elke 5 minuten (of bij verandering)."""
    zorg_schema(con)
    nu = datetime.now()
    laatste = con.execute("SELECT * FROM mt5_account_log ORDER BY ts DESC LIMIT 1").fetchone()
    rij = (round(float(getattr(info, "balance", 0) or 0), 2),
           round(float(getattr(info, "equity", 0) or 0), 2),
           round(float(getattr(info, "margin", 0) or 0), 2),
           round(float(getattr(info, "margin_free", 0) or 0), 2),
           round(float(getattr(info, "margin_level", 0) or 0), 2),
           round(float(getattr(info, "profit", 0) or 0), 2), int(n_posities))
    if laatste is not None:
        verstreken = (nu - datetime.fromisoformat(laatste[0])).total_seconds()
        veranderd = (laatste[1] != rij[0]) or (laatste[7] != rij[6])
        interval = min_interval_sec if rij[6] > 0 else 3600
        if not ((veranderd and verstreken >= 10) or verstreken >= interval):
            return False
    con.execute("INSERT OR REPLACE INTO mt5_account_log VALUES (?,?,?,?,?,?,?,?)",
                (nu.isoformat(timespec="seconds"),) + rij)
    return True


def laatste_account(con):
    zorg_schema(con)
    r = con.execute("SELECT * FROM mt5_account_log ORDER BY ts DESC LIMIT 1").fetchone()
    return dict(zip(["ts", "balance", "equity", "margin", "margin_free", "margin_level",
                     "profit", "n_posities"], r)) if r else None


# ------------------------------------------------------------------ overzicht

def overzicht(con):
    zorg_schema(con)
    rijen = lijst(con)
    per = {s: round(sum(r["bedrag"] for r in rijen if r["soort"] == s), 2) for s in SOORTEN}
    start = startkapitaal(con)
    netto = trading_netto(con)
    saldo = round(start + netto + sum(per.values()), 2)
    acc = laatste_account(con)
    return {
        "startkapitaal": round(start, 2),
        "trading_netto": netto,
        "stortingen": per["storting"],
        "opnames": per["opname"],
        "correcties": per["correctie"],
        "aansluiting": per["aansluiting"],
        "ingelegd": round(start + per["storting"] + per["opname"], 2),
        "saldo": saldo,
        "mt5": acc,
        "verschil_mt5": round(acc["balance"] - saldo, 2) if acc else None,
        "kasstromen": rijen[::-1],
    }


def eenmalige_seed(con):
    """29 sep 2026: €100 gestort, MT5 staat op €209. Eén keer, idempotent."""
    zorg_schema(con)
    if _setting(con, "v2_saldo_seed"):
        return
    if not con.execute("SELECT 1 FROM kasstromen LIMIT 1").fetchone():
        voeg_toe(con, "2026-09-29", "storting", 100, "Storting 29 sep")
        zet_saldo(con, 209.0, "2026-09-29",
                  "Gelijkgezet op MT5-saldo € 209,00 (29 sep) — verschil niet uit gelogde trades")
    # nog-niet-gelogde trades gaan het nieuwe (bias-vrije) model in
    con.execute("UPDATE trades SET model='biasvrij' WHERE beoordeeld=0 AND model IS NULL")
    _set_setting(con, "v2_saldo_seed", date.today().isoformat())
