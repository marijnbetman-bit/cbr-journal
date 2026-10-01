# -*- coding: utf-8 -*-
"""
migreer.py -- voegt de WP1-velden toe aan de journal-database.

Additief en idempotent: leest welke kolommen er al zijn en voegt alleen de
ontbrekende toe. Twee keer draaien mag; bestaande trades blijven ongemoeid.

Draaien vanuit de journal-map:
    python migreer.py                 # migreert cbr_journal.db
    python migreer.py --db pad.db
    python migreer.py --droog         # toont wat het zou doen, verandert niets

MAAK EERST EEN KOPIE van cbr_journal.db voordat je dit draait.
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime

# De nieuwe kolommen (WP1). Naam -> SQL-type. Alles NULL-baar, zodat bestaande
# rijen gewoon leeg blijven tot ze gevuld worden (door MT5-import of de foto/handmatig).
NIEUWE_KOLOMMEN = {
    "positie_id":              "INTEGER",   # MT5, voorkomt dubbel importeren
    "lot":                     "REAL",
    "tijd_exit":               "TEXT",
    "entry_prijs":             "REAL",
    "exit_prijs":              "REAL",
    "sl_prijs":                "REAL",
    "tp_prijs":                "REAL",
    "sl_afstand_points":       "REAL",
    "tp_afstand_points":       "REAL",
    "sweep_overshoot_points":  "REAL",
    "risico_eur":              "REAL",
    "resultaat_r":             "REAL",
    "duur_minuten":            "INTEGER",
    "mfe_points":              "REAL",
    "mae_points":              "REAL",
    "minuut_in_uur":           "INTEGER",
    "signaal_id":              "INTEGER",    # koppeling naar signalen.db
    "signaal_gezien":          "TEXT",       # op_tijd | te_laat | niet_gezien | terecht_genegeerd
    "staat_vooraf":            "TEXT",       # rustig | gehaast | moe

    # --- blok 2: de pre-trade kaart ---------------------------------------
    "check_venster":           "INTEGER",    # 1/0 per vinkje van de vijf
    "check_dagmax":            "INTEGER",
    "check_bias":              "INTEGER",
    "check_entry50":           "INTEGER",
    "check_sl":                "INTEGER",
    "schoon":                  "INTEGER",    # 1 = alle vijf aan
    "checks_vooraf":           "INTEGER",    # 1 = vóór de trade getikt, 0 = achteraf
    "voorgenomen_id":          "INTEGER",    # koppeling naar de kaart die je vooraf invulde
    "foutcodes":               "TEXT",       # komma-gescheiden codes uit de vaste lijst
    "dagtype":                 "TEXT",       # thuiswerk | kantoor | weekend
    "trade_id":                "TEXT",       # gedeelde sleutel, voor het later samenvoegen
}

# Tabellen die erbij komen (blok 2). CREATE IF NOT EXISTS, dus idempotent.
NIEUWE_TABELLEN = {
    # wat je vóór de trade aanvinkte; wordt later aan de trade gekoppeld
    "voorgenomen": """
        CREATE TABLE IF NOT EXISTS voorgenomen (
          id             INTEGER PRIMARY KEY AUTOINCREMENT,
          ts             TEXT NOT NULL,
          datum          TEXT NOT NULL,
          check_venster  INTEGER, check_dagmax INTEGER, check_bias INTEGER,
          check_entry50  INTEGER, check_sl INTEGER,
          schoon         INTEGER,
          volgnummer     INTEGER,        -- de hoeveelste kaart van die dag
          doorgezet_reden TEXT,          -- ingevuld als je de dagrem negeerde
          gebruikt       INTEGER DEFAULT 0
        )""",
    # hoe goed leest de foto-lezer? elke correctie van jou is een gratis meting
    "lezer_meting": """
        CREATE TABLE IF NOT EXISTS lezer_meting (
          id          INTEGER PRIMARY KEY AUTOINCREMENT,
          ts          TEXT NOT NULL,
          veld        TEXT NOT NULL,     -- richting | entry | sl | tp
          gelezen     TEXT,              -- wat het model ervan maakte (NULL = niet gelezen)
          gecorrigeerd TEXT,             -- wat jij ervan maakte
          klopte      INTEGER,           -- 1 = ongewijzigd overgenomen
          tweede_foto INTEGER DEFAULT 0  -- was er een position-tool screenshot nodig
        )""",
    # de dagen dat je NIET handelde -- zonder dit heb je geen noemer
    "geen_trade": """
        CREATE TABLE IF NOT EXISTS geen_trade (
          id       INTEGER PRIMARY KEY AUTOINCREMENT,
          ts       TEXT NOT NULL,
          datum    TEXT NOT NULL,
          soort    TEXT NOT NULL,        -- niets_gezien | bewust_gelaten
          notitie  TEXT,
          dagtype  TEXT
        )""",
}


def bestaande_kolommen(conn, tabel="trades"):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({tabel})")}


def ontbrekend(conn):
    heeft = bestaande_kolommen(conn)
    return {k: t for k, t in NIEUWE_KOLOMMEN.items() if k not in heeft}


def migreer(db_pad, droog=False):
    conn = sqlite3.connect(db_pad)
    try:
        # bestaat de trades-tabel wel?
        tabellen = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "trades" not in tabellen:
            print("[!] geen 'trades'-tabel gevonden -- is dit de juiste database?")
            return 1

        te_doen = ontbrekend(conn)
        tabellen_te_doen = {n: sql for n, sql in NIEUWE_TABELLEN.items()
                            if n not in tabellen}
        if not te_doen and not tabellen_te_doen:
            print("Niets te doen: alle kolommen en tabellen bestaan al.")
            return 0

        if te_doen:
            print(f"Toe te voegen kolommen ({len(te_doen)}):")
            for naam, typ in te_doen.items():
                print(f"  + {naam:<24} {typ}")
        if tabellen_te_doen:
            print(f"Toe te voegen tabellen ({len(tabellen_te_doen)}): "
                  + ", ".join(tabellen_te_doen))
        if droog:
            print("\n[droog] er is niets veranderd.")
            return 0

        for naam, typ in te_doen.items():
            conn.execute(f"ALTER TABLE trades ADD COLUMN {naam} {typ}")
        for sql in NIEUWE_TABELLEN.values():
            conn.execute(sql)
        conn.commit()
        # controle
        na = bestaande_kolommen(conn)
        na_tab = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        klaar = (all(k in na for k in NIEUWE_KOLOMMEN)
                 and all(t in na_tab for t in NIEUWE_TABELLEN))
        print(f"\nKlaar. {len(te_doen)} kolommen en {len(tabellen_te_doen)} tabellen "
              f"toegevoegd, "
              f"{'alles aanwezig' if klaar else 'LET OP: niet alles gelukt'}.")
        return 0 if klaar else 1
    finally:
        conn.close()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="cbr_journal.db")
    p.add_argument("--droog", action="store_true")
    p.add_argument("--geen-backup", action="store_true",
                   help="sla de automatische kopie over (afgeraden)")
    a = p.parse_args(argv)

    if not a.droog and not a.geen_backup:
        kopie = f"{a.db}.backup-{datetime.now():%Y%m%d-%H%M%S}"
        try:
            shutil.copy2(a.db, kopie)
            print(f"Back-up gemaakt: {kopie}")
        except FileNotFoundError:
            print(f"[!] {a.db} niet gevonden.")
            return 1
    return migreer(a.db, droog=a.droog)


if __name__ == "__main__":
    sys.exit(main())
