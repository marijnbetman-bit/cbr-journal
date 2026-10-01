"""
SQLite-database voor de CBR Trading Journal.

Drie tabellen: trades, no_trades, screenshots.
Bij een lege database wordt de startdag (3 sep 2026) automatisch geseed.
"""

import os
import sqlite3
from contextlib import contextmanager

from . import cbr

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "cbr_journal.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    datum           TEXT NOT NULL,
    tijd_entry      TEXT,
    instrument      TEXT NOT NULL DEFAULT 'XAUUSD',
    sessie          TEXT DEFAULT '2e uur Londen',
    richting        TEXT DEFAULT '',

    crit1_conditie  TEXT NOT NULL DEFAULT 'maybe',
    crit2_sweep     TEXT NOT NULL DEFAULT 'maybe',
    crit3_shift     TEXT NOT NULL DEFAULT 'maybe',
    crit4_entry     TEXT NOT NULL DEFAULT 'maybe',
    crit5_tp        TEXT NOT NULL DEFAULT 'maybe',
    rr              REAL,

    grade           TEXT NOT NULL DEFAULT 'C',
    status          TEXT NOT NULL DEFAULT 'genomen',   -- gepland | genomen | overgeslagen
    skip_reden      TEXT DEFAULT '',                    -- waarom overgeslagen (fase 11.2)
    tags            TEXT DEFAULT '',                    -- vrije tags (fase 12.4)
    verwijderd_op   TEXT,                               -- prullenbak (fase 16.1)
    bron            TEXT NOT NULL DEFAULT 'live',       -- live | backtest
    zekerheid       INTEGER,                            -- 1..5, hoe zeker was je vooraf

    entry           REAL,
    sl              REAL,
    tp              REAL,
    risk_eur        REAL,

    -- Ronde 2 -- sweep-overshoot meten. 1 point = 0,10 in prijs.
    -- sl_marge (= sl_afstand_points - sweep_overshoot_points) wordt berekend,
    -- niet opgeslagen: afgeleide data hoort niet in de tabel.
    sweep_overshoot_points REAL,
    sl_afstand_points      REAL,
    tp_afstand_points      REAL,

    -- Ronde 2 -- kwaliteit die je wel toepast maar tot nu toe niet logde.
    shift_kwaliteit        TEXT DEFAULT '',   -- duidelijk | soft | onduidelijk
    volume_hoog            TEXT DEFAULT '',   -- ja | nee
    overextensie_kwaliteit TEXT DEFAULT '',   -- goed | slecht
    minuten_in_hourly      INTEGER,
    sl_dan_tp              TEXT DEFAULT '',   -- SL geraakt en daarna alsnog TP-niveau: ja | nee

    -- Proces boven uitkomst: een winst die je zelf niet aan je edge toeschrijft
    -- hoort niet stilzwijgend je winrate in te glippen als 'skill'.
    luck_flag              TEXT DEFAULT '',   -- ja = voelde als luck / geen duidelijke edge

    resultaat_eur   REAL,
    charges         REAL DEFAULT -0.06,
    exit_reden      TEXT,

    sl_nabijheid    TEXT DEFAULT '',
    tp_verloop      TEXT DEFAULT '',

    foutcodes       TEXT DEFAULT '',
    mentale_staat   TEXT,
    les             TEXT,
    notities        TEXT,
    dxy_context     TEXT,

    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS no_trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    datum       TEXT NOT NULL,
    tijd        TEXT,
    reden       TEXT,
    wat_zag_ik  TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
,
    verwijderd_op TEXT                       -- prullenbak (fase 16.1)
);

CREATE TABLE IF NOT EXISTS screenshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id     INTEGER,
    no_trade_id  INTEGER,
    pad          TEXT NOT NULL,
    beschrijving TEXT,
    type         TEXT DEFAULT 'entry',
    created_at   TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE,
    FOREIGN KEY (no_trade_id) REFERENCES no_trades(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS voorbereiding (
    datum      TEXT PRIMARY KEY,
    punten     TEXT DEFAULT '',        -- komma-gescheiden keys die afgevinkt zijn
    notitie    TEXT DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notities (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    datum      TEXT NOT NULL,
    titel      TEXT NOT NULL,
    tekst      TEXT,
    tags       TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS regelwijzigingen (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    datum       TEXT NOT NULL,          -- vanaf welke dag geldt de nieuwe regel
    titel       TEXT NOT NULL,
    toelichting TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessies (
    datum        TEXT PRIMARY KEY,
    in_venster   TEXT DEFAULT '',       -- ja | nee  (alleen in mijn uur getraded?)
    plan_gevolgd TEXT DEFAULT '',       -- ja | nee  (plan gevolgd, niets geforceerd?)
    staat        TEXT DEFAULT '',       -- rustig | gehaast | moe
    les          TEXT DEFAULT '',       -- belangrijkste les van vandaag, één regel
    updated_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    soort      TEXT NOT NULL,          -- 'dag' | 'week'
    sleutel    TEXT NOT NULL,          -- '2026-09-04' of de maandag van de week
    goed       TEXT,
    beter      TEXT,
    focus      TEXT,
    focus_af   TEXT DEFAULT '',       -- 'ja' zodra je de focus hebt afgevinkt
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE (soort, sleutel)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

DEFAULT_SETTINGS = {
    "startkapitaal": "50",     # EUR, portfolio-startkapitaal (basis spaarverloop)
    "valuta": "€",
    "werkelijke_balans": "",   # EUR, wat je broker echt laat zien (voor de balans-check)
    # Dagregels (fase 9.4) -- de vangrail. 0 = uit.
    "max_trades_dag": "3",
    "stop_na_verliezen": "2",
    # Londense sessie op Amsterdamse tijd: vanaf het 2e uur Londen tot een half
    # uur voor de Amerikaanse open (23 sep) -- wordt ook meegesynct vanuit
    # journal_config.json, dat is de bron van waarheid.
    "venster_van": "10:00",
    "venster_tot": "15:00",
}


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Kolommen die later zijn toegevoegd; worden bij bestaande DBs bijgewerkt.
MIGRATIONS = {
    "reviews": {
        "focus_af": "TEXT DEFAULT ''",
    },
    "no_trades": {
        "verwijderd_op": "TEXT",
        "fase": "INTEGER",
    },
    "trades": {
        "richting": "TEXT DEFAULT ''",
        "sl_nabijheid": "TEXT DEFAULT ''",   # nooit | halverwege | bijna
        "tp_verloop": "TEXT DEFAULT ''",     # precies | liep_door | te_vroeg
        "status": "TEXT NOT NULL DEFAULT 'genomen'",
        "bron": "TEXT NOT NULL DEFAULT 'live'",
        "skip_reden": "TEXT DEFAULT ''",
        "tags": "TEXT DEFAULT ''",
        "verwijderd_op": "TEXT",
        "zekerheid": "INTEGER",
        # Ronde 2 -- meetvelden rond de sweep en de setup-kwaliteit.
        "sweep_overshoot_points": "REAL",
        "sl_afstand_points": "REAL",
        "tp_afstand_points": "REAL",
        "shift_kwaliteit": "TEXT DEFAULT ''",
        "volume_hoog": "TEXT DEFAULT ''",
        "overextensie_kwaliteit": "TEXT DEFAULT ''",
        "minuten_in_hourly": "INTEGER",
        "sl_dan_tp": "TEXT DEFAULT ''",
        "luck_flag": "TEXT DEFAULT ''",
        # ---- Fase 2 (11 sep 2026): bias eerst ----------------------------
        # Bewust ZONDER default: NULL betekent "bestond al voor de omslag" en
        # wordt eenmalig op 1 gezet. Nieuwe trades sturen de fase altijd mee.
        "fase": "INTEGER",
        "f2_bias": "TEXT DEFAULT 'maybe'",
        "f2_dxy": "TEXT DEFAULT 'maybe'",
        "f2_expansie": "TEXT DEFAULT 'maybe'",
        "f2_sweep": "TEXT DEFAULT 'maybe'",
        "f2_shift": "TEXT DEFAULT 'maybe'",
        "f2_entry": "TEXT DEFAULT 'maybe'",
        "f2_sl": "TEXT DEFAULT 'maybe'",
        "f2_tp": "TEXT DEFAULT 'maybe'",
        # context bij de fase-2-criteria
        "bias_1hr": "TEXT DEFAULT ''",          # bullish | bearish | onduidelijk
        "dxy_richting": "TEXT DEFAULT ''",      # invers | unison | onduidelijk
        "expansie_minuten": "INTEGER",
        "fvg_waarschuwing": "TEXT DEFAULT ''",  # ja | nee -- grote FVG open
        "trigger_type": "TEXT DEFAULT ''",      # sweep_1e_uur | rebalance
        "poging_nr": "INTEGER",                 # 1 of 2, max 2 per sessie
    },
}


def _migrate(conn):
    """Voeg ontbrekende kolommen toe aan bestaande databases."""
    for table, cols in MIGRATIONS.items():
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, ddl in cols.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _eenmalige_correcties(conn):
    """
    Kleine, doelgerichte datacorrecties voor databases die al bestaan.
    Idempotent: raakt alleen precies de rij die nog niet klopt.
    """
    # Fase-omslag 11 sep 2026. Alles wat op dat moment al in de journal stond
    # is fase 1 -- het oude sweep-en-draai model, zonder biasfilter. Die trades
    # blijven bewaard in het archief maar tellen niet meer mee in de statistiek.
    conn.execute("UPDATE trades SET fase=1 WHERE fase IS NULL")
    conn.execute("UPDATE no_trades SET fase=1 WHERE fase IS NULL")

    # De trade van 4 sep 2026 (+EUR 4,28) stond op grade B omdat criterium 4 nog
    # op '?' stond. Marijn heeft bevestigd dat de uitvoering perfect was.
    conn.execute(
        "UPDATE trades SET crit4_entry='yes', grade='A', updated_at=datetime('now') "
        "WHERE datum='2026-09-04' AND resultaat_eur=4.28 AND crit4_entry='maybe' "
        "AND crit1_conditie='yes' AND crit2_sweep='yes' AND crit3_shift='yes' "
        "AND crit5_tp='yes'")

    # Databases die vóór 4 sep 2026 zijn aangemaakt misten die trade helemaal:
    # de seed draait alleen bij een lege database. Eenmalig aanvullen.
    bestaat = conn.execute(
        "SELECT COUNT(*) c FROM trades WHERE resultaat_eur=4.28").fetchone()["c"]
    heeft_data = conn.execute("SELECT COUNT(*) c FROM trades").fetchone()["c"]
    if heeft_data and not bestaat:
        _seed_dag2(conn)

    # Ronde 2 -- trade 8 (7 sep 2026, -EUR 3,40) stond op grade B, maar de shift
    # was een SOFT break. Twijfel telt als '?', en een kritisch criterium op '?'
    # geeft grade C. De grade volgt hier dus gewoon weer uit de checklist, niet
    # uit de uitkomst. Idempotent: raakt alleen de rij die nog op 'yes' staat.
    conn.execute(
        "UPDATE trades SET crit3_shift='maybe', shift_kwaliteit='soft', grade='C', "
        "updated_at=datetime('now') "
        "WHERE datum='2026-09-07' AND ROUND(resultaat_eur, 2) = -3.4 "
        "AND crit3_shift='yes'")


def _zoek_oude_database():
    """
    Verhuis je naar een nieuwe map, dan staat je oude cbr_journal.db nog ergens
    anders. Bij een lege installatie kijken we één keer in de buurt: de map
    boven deze, en maximaal drie niveaus daaronder. We KOPIEREN alleen -- het
    origineel blijft altijd staan.
    """
    import shutil
    ouder = os.path.dirname(BASE_DIR)
    kandidaten = []
    for wortel, mappen, files in os.walk(ouder):
        diepte = wortel[len(ouder):].count(os.sep)
        if diepte >= 3:
            mappen[:] = []
            continue
        mappen[:] = [m for m in mappen
                     if m not in (".venv", "__pycache__", "backups", "node_modules")]
        if os.path.abspath(wortel) == os.path.abspath(BASE_DIR):
            continue
        if "cbr_journal.db" in files:
            pad = os.path.join(wortel, "cbr_journal.db")
            try:
                kandidaten.append((os.path.getmtime(pad), os.path.getsize(pad), pad))
            except OSError:
                pass
    kandidaten = [k for k in kandidaten if k[1] > 0]
    if not kandidaten:
        return None
    kandidaten.sort(reverse=True)
    bron = kandidaten[0][2]
    try:
        shutil.copy2(bron, DB_PATH)
    except OSError:
        return None
    return bron


def init_db():
    """Maak het schema aan en seed de startdag als de DB nog leeg is."""
    fresh = not os.path.exists(DB_PATH)
    overgenomen = None
    if fresh:
        overgenomen = _zoek_oude_database()
        if overgenomen:
            fresh = False
            print(f"  Oude journal gevonden en overgenomen uit:\n    {overgenomen}")
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))
        _eenmalige_correcties(conn)
    if fresh:
        _seed_startdag()


def get_settings(conn):
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    s = {r["key"]: r["value"] for r in rows}
    for k, v in DEFAULT_SETTINGS.items():
        s.setdefault(k, v)
    return s


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def _seed_startdag():
    """
    Startdata: mijn eerste dag (3 sep 2026). Alle vier XAUUSD, 2e uur Londen.
    Charges -EUR 0,06 per trade. Plus twee bewuste no-trades.
    """
    datum = "2026-09-03"

    trades = [
        # Trade 1 -- grade C, -EUR 2,00.
        # Overextensie met grote pullback, daarna upside. Entry zonder
        # duidelijke shift (crit3 X). SL vlak boven recente high, in
        # sweep-zone (R1). SL met minimale marge geraakt, daarna zou TP
        # geraakt zijn. Fout: E1, R1.
        dict(
            tijd_entry="", richting="short", crit1_conditie="maybe", crit2_sweep="maybe",
            crit3_shift="no", crit4_entry="maybe", crit5_tp="maybe", rr=None,
            entry=None, sl=None, tp=None, risk_eur=2.0,
            resultaat_eur=-2.0, exit_reden="SL geraakt (minimale marge, daarna zou TP geraakt zijn)",
            foutcodes="E1,R1",
            notities="Overextensie met grote pullback, daarna upside. Entry zonder duidelijke shift. SL vlak boven recente high, in de sweep-zone.",
            les="Geen entry zonder bevestigde shift; leg de SL niet in de sweep-zone.",
            dxy_context="",
        ),
        # Trade 2 -- grade C, +EUR 2,24.
        # Overextensie omlaag, type-3 shift op 1M, entry 50% pullback op
        # 4434,15, TP 50% ext, RR 1,37. Achteraf: shift in chop, geen sweep
        # van 1H H/L (crit2 X, crit1 ?). DXY bewoog mee. Fout: E2, E8, E6.
        dict(
            tijd_entry="", richting="short", crit1_conditie="maybe", crit2_sweep="no",
            crit3_shift="yes", crit4_entry="yes", crit5_tp="yes", rr=1.37,
            entry=4434.15, sl=None, tp=None, risk_eur=None,
            resultaat_eur=2.24, exit_reden="TP geraakt",
            foutcodes="E2,E8,E6",
            notities="Overextensie omlaag, type-3 shift op 1M, entry 50% pullback, TP 50% ext. Achteraf: shift in chop, geen sweep van 1H H/L.",
            les="Een shift telt alleen na een echte sweep van de 1H high/low; niet in chop.",
            dxy_context="DXY bewoog mee (geen inverse).",
        ),
        # Trade 3 -- grade C, +EUR 1,94.
        # Long. Overextensie buiten vorige 1H range met veel volume, type-3
        # shift, entry in shift-zone, TP 50% 1H candle, RR 1:1. Sweep V en
        # shift V, MAAR bredere structuur was een schone downtrend met een
        # ~30%-reversal -> verboden reversal in schone trend (crit1 X). Fout: E2.
        dict(
            tijd_entry="", richting="long", crit1_conditie="no", crit2_sweep="yes",
            crit3_shift="yes", crit4_entry="yes", crit5_tp="yes", rr=1.0,
            entry=None, sl=None, tp=None, risk_eur=None,
            resultaat_eur=1.94, exit_reden="TP geraakt",
            foutcodes="E2",
            notities="Long. Overextensie buiten vorige 1H range met veel volume, type-3 shift, entry in shift-zone, TP 50% 1H candle. Sweep en shift OK, maar bredere structuur was een schone downtrend met slechts een ~30%-reversal.",
            les="Nooit een reversal nemen in een schone trend; de conditie moet een range met 2+ legs zijn.",
            dxy_context="",
        ),
        # Trade 4 -- grade B (eerste valide setup!), +EUR 3,14.
        # Long in bullish trending range met meerdere legs. Brak boven vorige
        # 1H candle (crit2 V), type-3 shift (crit3 V), entry op 50% retrace
        # (crit4 V), TP 50%, RR 1:1. Conditie = range met 2+ legs (crit1 V).
        # Door hemzelf bevestigd als A-setup: alle vijf criteria V.
        dict(
            tijd_entry="", richting="long", crit1_conditie="yes", crit2_sweep="yes",
            crit3_shift="yes", crit4_entry="yes", crit5_tp="yes", rr=1.0,
            entry=None, sl=None, tp=None, risk_eur=None,
            resultaat_eur=3.14, exit_reden="TP geraakt",
            foutcodes="",
            notities="Long in bullish trending range met meerdere legs. Brak boven vorige 1H candle, type-3 shift, entry op 50% retrace, TP 50%, RR 1:1. Eerste valide setup van de dag.",
            les="Zo ziet een valide setup eruit: range met 2+ legs, sweep, type-3 shift, entry op 50%.",
            dxy_context="",
        ),
    ]

    with get_conn() as conn:
        for t in trades:
            grade = cbr.compute_grade(t)
            t = {**t, "datum": datum, "instrument": "XAUUSD",
                 "sessie": "2e uur Londen", "charges": -0.06, "grade": grade,
                 "mentale_staat": "", "fase": 1}
            _insert_trade(conn, t)

        no_trades = [
            dict(
                datum=datum, tijd="",
                reden="Geen duidelijke break boven/onder de vorige 1H H/L.",
                wat_zag_ik="Geen duidelijke eenzijdige beweging, geen fractal shift.",
            ),
            dict(
                datum=datum, tijd="",
                reden="Prijs bleef binnen de zwarte stippellijn (vorige 1H H/L).",
                wat_zag_ik="Geen eenzijdige move, geen fractal shift.",
            ),
            # Gemiste valide setup (laatste uit de vorige chat) -- niet genomen.
            dict(
                datum=datum, tijd="16:15",
                reden="Valide setup GEMIST (niet genomen) — had een entry kunnen zijn.",
                wat_zag_ik="~16:15–16:30: prijs brak boven de vorige 1H range, pullback naar de 50%-zone (groen blokje op de chart), daarna weer omhoog. Zag er valide uit maar niet ingestapt.",
            ),
        ]
        for nt in no_trades:
            conn.execute(
                "INSERT INTO no_trades (datum, tijd, reden, wat_zag_ik, fase) "
                "VALUES (?,?,?,?,1)",
                (nt["datum"], nt["tijd"], nt["reden"], nt["wat_zag_ik"]),
            )

        _seed_dag2(conn)


def _seed_dag2(conn):
    """4 sep 2026 -- XAUUSD long na overextensie omlaag, TP geraakt, RR 1:1.8."""
    datum = "2026-09-04"
    t = dict(
        datum=datum, tijd_entry="11:25", instrument="XAUUSD", sessie="2e uur Londen",
        richting="long",
        crit1_conditie="yes",     # brak uit een 1H range -> conditie was een range
        crit2_sweep="yes",        # overextensie omlaag, uit de vorige 1H range gebroken
        crit3_shift="yes",        # 1-minuut 3-step break = type-3 shift
        crit4_entry="yes",        # entry op 50% van de shift -- door Marijn bevestigd
        crit5_tp="yes",           # TP geraakt, RR 1,8 (ruim boven de 1:1-vloer)
        rr=1.8,
        entry=None, sl=None, tp=None, risk_eur=None,
        resultaat_eur=4.28,
        charges=-0.06,
        exit_reden="TP geraakt",
        foutcodes="",
        mentale_staat="",
        les="Overextensie omlaag uit de 1H range, 3-step break op 1M, TP geraakt op 1:1,8.",
        notities="Overextensie naar beneden, uit een 1H range gebroken. Op de 1-minuut een 3-step break (type-3 shift), daarna long. TP geraakt, RR 1:1,8. Entry 11:25 Amsterdam = 10:25 Londen, dus binnen het 2e uur van Londen.",
        dxy_context="",
    )
    t["grade"] = cbr.compute_grade(t)
    t["fase"] = 1
    tid = _insert_trade(conn, t)

    for pad, beschrijving, typ in [
        (f"screenshots/{datum}/1h_context.png", "1H-context: overextensie omlaag uit de vorige 1H range", "pre-entry"),
        (f"screenshots/{datum}/1m_entry.png", "1M: 3-step break (type-3 shift) en de entry-zone", "entry"),
    ]:
        conn.execute(
            "INSERT INTO screenshots (trade_id, pad, beschrijving, type) VALUES (?,?,?,?)",
            (tid, pad, beschrijving, typ),
        )


TRADE_FIELDS = [
    "datum", "tijd_entry", "instrument", "sessie", "richting",
    "crit1_conditie", "crit2_sweep", "crit3_shift", "crit4_entry", "crit5_tp",
    "rr", "grade", "status", "bron", "skip_reden", "tags", "zekerheid", "entry", "sl", "tp", "risk_eur",
    "resultaat_eur", "charges", "exit_reden", "sl_nabijheid", "tp_verloop",
    "foutcodes", "mentale_staat", "les", "notities", "dxy_context",
    # Ronde 2
    "sweep_overshoot_points", "sl_afstand_points", "tp_afstand_points",
    "shift_kwaliteit", "volume_hoog", "overextensie_kwaliteit", "minuten_in_hourly",
    "sl_dan_tp", "luck_flag",
    # Fase 2 -- bias eerst
    "fase",
    "f2_bias", "f2_dxy", "f2_expansie", "f2_sweep", "f2_shift",
    "f2_entry", "f2_sl", "f2_tp",
    "bias_1hr", "dxy_richting", "expansie_minuten", "fvg_waarschuwing",
    "trigger_type", "poging_nr",
]


def _insert_trade(conn, data: dict) -> int:
    # status is NOT NULL; seed-data en oudere aanroepen laten 'm weg.
    if not data.get("status"):
        data = {**data, "status": "genomen"}
    if not data.get("bron"):
        data = {**data, "bron": "live"}
    if data.get("fase") in (None, ""):
        data = {**data, "fase": cbr.FASE_ACTIEF}
    cols = [f for f in TRADE_FIELDS]
    placeholders = ",".join("?" for _ in cols)
    values = [data.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT INTO trades ({','.join(cols)}) VALUES ({placeholders})", values
    )
    return cur.lastrowid


# ---------- Query-helpers ----------

def row_to_dict(row):
    return dict(row) if row is not None else None


def get_trade(conn, trade_id):
    row = conn.execute(
        "SELECT * FROM trades WHERE id=? AND verwijderd_op IS NULL", (trade_id,)).fetchone()
    return row_to_dict(row)


def get_no_trade(conn, no_trade_id):
    row = conn.execute(
        "SELECT * FROM no_trades WHERE id=? AND verwijderd_op IS NULL", (no_trade_id,)).fetchone()
    return row_to_dict(row)


def get_screenshots_for_trade(conn, trade_id):
    rows = conn.execute(
        "SELECT * FROM screenshots WHERE trade_id=? ORDER BY id", (trade_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_screenshots_for_no_trade(conn, no_trade_id):
    rows = conn.execute(
        "SELECT * FROM screenshots WHERE no_trade_id=? ORDER BY id", (no_trade_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_review(conn, soort, sleutel):
    row = conn.execute(
        "SELECT * FROM reviews WHERE soort=? AND sleutel=?", (soort, sleutel)
    ).fetchone()
    return dict(row) if row else None


def zet_focus_af(conn, soort, sleutel, af):
    """Focus afvinken (of weer aanzetten). Blijft anders bovenaan staan."""
    conn.execute(
        "INSERT INTO reviews (soort, sleutel, focus_af) VALUES (?,?,?) "
        "ON CONFLICT(soort, sleutel) DO UPDATE SET focus_af=excluded.focus_af, "
        "updated_at=datetime('now')",
        (soort, sleutel, "ja" if af else ""))


def save_review(conn, soort, sleutel, goed, beter, focus):
    conn.execute(
        "INSERT INTO reviews (soort, sleutel, goed, beter, focus) VALUES (?,?,?,?,?) "
        "ON CONFLICT(soort, sleutel) DO UPDATE SET "
        "goed=excluded.goed, beter=excluded.beter, focus=excluded.focus, "
        "updated_at=datetime('now')",
        (soort, sleutel, goed, beter, focus),
    )


# ---------- Sessies: de mens-laag, per dag ----------

def get_sessie(conn, datum):
    r = conn.execute("SELECT * FROM sessies WHERE datum=?", (datum,)).fetchone()
    if not r:
        return {"datum": datum, "in_venster": "", "plan_gevolgd": "", "staat": "", "les": ""}
    return dict(r)


def save_sessie(conn, datum, in_venster, plan_gevolgd, staat, les):
    conn.execute(
        "INSERT INTO sessies (datum, in_venster, plan_gevolgd, staat, les) VALUES (?,?,?,?,?) "
        "ON CONFLICT(datum) DO UPDATE SET in_venster=excluded.in_venster, "
        "plan_gevolgd=excluded.plan_gevolgd, staat=excluded.staat, les=excluded.les, "
        "updated_at=datetime('now')",
        (datum, in_venster, plan_gevolgd, staat, les))


def alle_sessies(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM sessies ORDER BY datum")]


# ---------- Voorbereiding (fase 14.2) ----------

def get_voorbereiding(conn, datum):
    r = conn.execute("SELECT * FROM voorbereiding WHERE datum=?", (datum,)).fetchone()
    return row_to_dict(r) if r else None


def save_voorbereiding(conn, datum, punten, notitie):
    conn.execute(
        "INSERT INTO voorbereiding (datum, punten, notitie) VALUES (?,?,?) "
        "ON CONFLICT(datum) DO UPDATE SET punten=excluded.punten, "
        "notitie=excluded.notitie, updated_at=datetime('now')",
        (datum, punten, notitie))


def voorbereiding_per_dag(conn):
    """Alle dagen met hun afgevinkte punten -- voor de discipline-meter."""
    return {r["datum"]: (r["punten"] or "")
            for r in conn.execute("SELECT datum, punten FROM voorbereiding")}


# ---------- Notitieboek (fase 12.3) ----------

def list_notities(conn, zoek=""):
    if zoek:
        pat = f"%{zoek}%"
        rows = conn.execute(
            "SELECT * FROM notities WHERE titel LIKE ? OR tekst LIKE ? OR tags LIKE ? "
            "ORDER BY datum DESC, id DESC", (pat, pat, pat))
    else:
        rows = conn.execute("SELECT * FROM notities ORDER BY datum DESC, id DESC")
    return [row_to_dict(r) for r in rows]


def save_notitie(conn, nid, datum, titel, tekst, tags):
    if nid:
        conn.execute(
            "UPDATE notities SET datum=?, titel=?, tekst=?, tags=?, "
            "updated_at=datetime('now') WHERE id=?",
            (datum, titel, tekst, tags, nid))
        return nid
    cur = conn.execute(
        "INSERT INTO notities (datum, titel, tekst, tags) VALUES (?,?,?,?)",
        (datum, titel, tekst, tags))
    return cur.lastrowid


def delete_notitie(conn, nid):
    conn.execute("DELETE FROM notities WHERE id=?", (nid,))


def alle_tags(conn):
    """Tags die al ergens gebruikt zijn -- voor de suggesties in het formulier."""
    uit = {}
    for tabel in ("trades", "notities"):
        try:
            rows = conn.execute(f"SELECT tags FROM {tabel}")
        except Exception:
            continue
        for r in rows:
            for tag in (r["tags"] or "").split(","):
                tag = tag.strip()
                if tag:
                    uit[tag] = uit.get(tag, 0) + 1
    return [{"tag": t, "aantal": a} for t, a in sorted(uit.items(), key=lambda x: (-x[1], x[0]))]


# ---------- Regel-changelog (fase 11.4) ----------

def list_regelwijzigingen(conn):
    return [row_to_dict(r) for r in conn.execute(
        "SELECT * FROM regelwijzigingen ORDER BY datum DESC, id DESC")]


def add_regelwijziging(conn, datum, titel, toelichting):
    cur = conn.execute(
        "INSERT INTO regelwijzigingen (datum, titel, toelichting) VALUES (?,?,?)",
        (datum, titel, toelichting or ""))
    return cur.lastrowid


def delete_regelwijziging(conn, rid):
    conn.execute("DELETE FROM regelwijzigingen WHERE id=?", (rid,))


def laatste_regelwijziging(conn):
    r = conn.execute(
        "SELECT * FROM regelwijzigingen ORDER BY datum DESC, id DESC LIMIT 1").fetchone()
    return row_to_dict(r) if r else None


def list_dates(conn):
    rows = conn.execute(
        "SELECT datum FROM trades WHERE verwijderd_op IS NULL AND fase=2 "
        "UNION SELECT datum FROM no_trades WHERE verwijderd_op IS NULL AND fase=2 "
        "ORDER BY datum DESC"
    ).fetchall()
    return [r["datum"] for r in rows]
