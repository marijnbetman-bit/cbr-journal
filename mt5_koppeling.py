# -*- coding: utf-8 -*-
"""
mt5_koppeling.py -- je echte trades automatisch uit MetaTrader 5 in de journal.

Zolang de journal draait, kijkt deze module elke 30 seconden in de
MetaTrader 5 die op dezelfde laptop open staat (ingelogd bij Vantage):

  1. OPEN posities: SL en TP worden onthouden zodra ze er staan. Zo kennen we
     later je oorspronkelijke risico, ook als je de SL pas na instappen zette
     of hem daarna naar break-even schoof.
  2. GESLOTEN posities: elke nieuwe gesloten XAU-trade komt als trade in de
     journal: datum en tijden (Amsterdams), richting, lot, entry/exit/SL/TP,
     resultaat en charges zoals de broker ze boekte, RR, R-multiple, MFE/MAE,
     en een chart van de minuutcandles met je in- en uitstapmoment erop.
  3. Stond de trade er al (je logde hem zelf), dan wordt hij GEKOPPELD en
     aangevuld, niet dubbel toegevoegd.

Nieuwe trades krijgen beoordeeld = 0. Je 5 checks en 5 CBR-criteria vul je in
via de journal-bot in Telegram of op /beoordelen; de grade volgt daaruit.

Deze module LEEST alleen. Er wordt nooit een order geplaatst of gewijzigd.
"""

import json
import os
import re
import sqlite3
import sys
import threading
import time
import traceback
from datetime import datetime, date, timedelta, timezone, time as dtime

HIER = os.path.dirname(os.path.abspath(__file__))
if HIER not in sys.path:
    sys.path.insert(0, HIER)

DB_PAD = os.path.join(HIER, "cbr_journal.db")
CONFIG_PAD = os.path.join(HIER, "journal_config.json")
SCREENSHOTS_DIR = os.path.join(HIER, "screenshots")
LOG_PAD = os.path.join(HIER, "mt5_koppeling.log")

STANDAARD = {
    "aan": True,
    "sync_vanaf": "2026-09-22",   # oudere trades staan er al (met de hand gelogd)
    "interval_sec": 30,
    "symbool": "XAUUSD+",         # voor de klok-check en de candles
    "symbool_bevat": "XAU",       # alleen trades op goud komen de journal in
    "broker_offset_uur": 3,       # reserve als de klok niet automatisch te bepalen is
    "terminal_pad": "",           # leeg = de MT5 die open staat
    "min_rr": 1.0,                # jouw RR-vloer, voor het TP-criterium
    "saldo_volgen": True,         # v2: journal-saldo altijd gelijk aan MT5-balans
    "match_marge_eur": 0.03,
    "match_marge_min": 15,
}

# MT5-constanten (numeriek, zodat tests zonder de package draaien)
ENTRY_IN, ENTRY_OUT, ENTRY_INOUT, ENTRY_OUT_BY = 0, 1, 2, 3
TYPE_BUY, TYPE_SELL = 0, 1
REDEN_TEKST = {
    0: "handmatig gesloten", 1: "handmatig gesloten (telefoon)",
    2: "handmatig gesloten (web)", 3: "gesloten door EA",
    4: "SL geraakt", 5: "TP geraakt", 6: "stop-out",
}
POINT = 0.10          # jouw notatie: 1 point = 0,10 in prijs
TIMEFRAME_M1 = 1

VINKJES_MAYBE = ("crit1_conditie", "crit2_sweep", "crit3_shift", "crit4_entry",
                 "crit5_tp", "f2_bias", "f2_dxy", "f2_expansie", "f2_sweep",
                 "f2_shift", "f2_entry", "f2_sl", "f2_tp")


# ------------------------------------------------------------------ basis

def lees_config():
    cfg = dict(STANDAARD)
    try:
        with open(CONFIG_PAD, encoding="utf-8") as f:
            cfg.update(json.load(f).get("mt5") or {})
    except (FileNotFoundError, ValueError):
        pass
    return cfg


def lees_journal_config():
    try:
        with open(CONFIG_PAD, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def log(tekst):
    print("[mt5]", tekst, flush=True)
    try:
        if os.path.exists(LOG_PAD) and os.path.getsize(LOG_PAD) > 512_000:
            os.replace(LOG_PAD, LOG_PAD + ".oud")
        with open(LOG_PAD, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {tekst}\n")
    except OSError:
        pass


# ------------------------------------------------------------------ tijd

def _laatste_zondag(jaar, maand):
    d = date(jaar, maand, 31)          # maart en oktober hebben 31 dagen
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def amsterdam_uur(utc_dt):
    """+2 in de Europese zomertijd, anders +1."""
    j = utc_dt.year
    begin = datetime.combine(_laatste_zondag(j, 3), dtime(1, 0), tzinfo=timezone.utc)
    eind = datetime.combine(_laatste_zondag(j, 10), dtime(1, 0), tzinfo=timezone.utc)
    return 2 if begin <= utc_dt < eind else 1


def server_naar_amsterdam(server_ts, offset_uur):
    """MT5 geeft tijden in servertijd. -> naive Amsterdamse datetime."""
    utc = datetime.fromtimestamp(int(server_ts) - int(offset_uur) * 3600, tz=timezone.utc)
    return (utc + timedelta(hours=amsterdam_uur(utc))).replace(tzinfo=None)


def detecteer_offset(tick_tijd, nu_utc_ts):
    """Serverklok minus echte UTC, in hele uren. None als de tick niet vers is
    (weekend, markt dicht) -- dan valt de koppeling terug op de config."""
    if not tick_tijd:
        return None
    verschil = tick_tijd - nu_utc_ts
    uur = round(verschil / 3600)
    if -12 <= uur <= 14 and abs(verschil - uur * 3600) <= 180:
        return int(uur)
    return None


def _minuten(hhmm):
    try:
        u, m = str(hhmm).split(":")[:2]
        return int(u) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


# ------------------------------------------------------------------ puur: deals -> posities

_COMMENT_RE = re.compile(r"\[\s*(sl|tp)\s*([0-9]+(?:\.[0-9]+)?)\s*\]", re.I)


def _gewogen(deals):
    vol = sum(float(d.get("volume") or 0) for d in deals)
    if vol <= 0:
        return float(deals[0].get("price")) if deals else None
    return sum(float(d.get("price") or 0) * float(d.get("volume") or 0) for d in deals) / vol


def groepeer(deals):
    """Losse MT5-deals -> {positie_id: samenvatting}. Alleen posities die
    volledig dicht zijn krijgen gesloten=True."""
    per = {}
    for d in deals:
        pid = d.get("position_id")
        if not pid:
            continue                        # balansposten, stortingen
        b = per.setdefault(pid, {"in": [], "uit": [], "profit": 0.0, "kosten": 0.0})
        b["profit"] += float(d.get("profit") or 0)
        b["kosten"] += (float(d.get("commission") or 0) + float(d.get("swap") or 0)
                        + float(d.get("fee") or 0))
        e = d.get("entry")
        if e == ENTRY_IN:
            b["in"].append(d)
        elif e in (ENTRY_OUT, ENTRY_OUT_BY, ENTRY_INOUT):
            b["uit"].append(d)

    uit = {}
    for pid, b in per.items():
        if not b["in"]:
            continue
        b["in"].sort(key=lambda d: d.get("time") or 0)
        b["uit"].sort(key=lambda d: d.get("time") or 0)
        vol_in = sum(float(d.get("volume") or 0) for d in b["in"])
        vol_uit = sum(float(d.get("volume") or 0) for d in b["uit"])
        opening = b["in"][0]
        laatste = b["uit"][-1] if b["uit"] else None
        comm = {}
        if laatste:
            comm = {k.lower(): float(v) for k, v in _COMMENT_RE.findall(laatste.get("comment") or "")}
        uit[pid] = {
            "positie_id": int(pid),
            "symbool": opening.get("symbol") or "",
            "richting": "long" if opening.get("type") == TYPE_BUY else "short",
            "lot": round(vol_in, 2),
            "open_ts": int(opening.get("time") or 0),
            "dicht_ts": int(laatste.get("time") or 0) if laatste else None,
            "entry": _gewogen(b["in"]),
            "exit": _gewogen(b["uit"]) if b["uit"] else None,
            "reden": laatste.get("reason") if laatste else None,
            "sl_comment": comm.get("sl"),
            "tp_comment": comm.get("tp"),
            "bruto": round(b["profit"], 2),
            "charges": round(b["kosten"], 2),
            "netto": round(b["profit"] + b["kosten"], 2),
            "gesloten": bool(b["uit"]) and vol_uit + 1e-9 >= vol_in,
            "order_id": opening.get("order"),
        }
    return uit


def bepaal_niveaus(pos, order_sl=None, order_tp=None, gezien=None):
    """Oorspronkelijke SL en TP. Volgorde: wat je bij het instappen meegaf ->
    wat de koppeling als eerste op de open positie zag -> wat er in de
    sluitregel van de broker staat. Een SL op entry (break-even) zegt niets
    over je risico en wordt overgeslagen."""
    gezien = gezien or {}
    entry = pos.get("entry")

    def kies(kandidaten, is_sl):
        for v in kandidaten:
            if v in (None, 0, 0.0):
                continue
            v = float(v)
            if is_sl and entry is not None and abs(v - entry) < 0.05:
                continue
            return v
        return None

    sl = kies([order_sl, gezien.get("eerste_sl"), pos.get("sl_comment"),
               gezien.get("laatste_sl")], True)
    tp = kies([order_tp, gezien.get("eerste_tp"), pos.get("tp_comment"),
               gezien.get("laatste_tp")], False)
    return sl, tp


def bereken(pos, sl, tp):
    """Afgeleide cijfers. Euro-risico uit de trade zelf (lot en koers zitten
    er dan al in): euro per prijseenheid = |bruto| / |beweging|."""
    entry, exit_ = pos["entry"], pos["exit"]
    lang = pos["richting"] == "long"
    m = {"sl_afstand_points": None, "tp_afstand_points": None, "rr": None,
         "risico_eur": None, "resultaat_r": None, "duur_minuten": None}
    if sl is not None:
        m["sl_afstand_points"] = round(abs(entry - sl) / POINT, 1)
    if tp is not None:
        m["tp_afstand_points"] = round(abs(tp - entry) / POINT, 1)
    if m["sl_afstand_points"] and m["tp_afstand_points"] is not None:
        m["rr"] = round(m["tp_afstand_points"] / m["sl_afstand_points"], 2)
    if exit_ is not None:
        beweging = (exit_ - entry) if lang else (entry - exit_)
        if sl is not None and abs(beweging) >= 0.05 and pos["bruto"]:
            per_prijs = abs(pos["bruto"]) / abs(beweging)
            risico = round(per_prijs * abs(entry - sl), 2)
            if risico > 0:
                m["risico_eur"] = risico
                m["resultaat_r"] = round(pos["bruto"] / risico, 2)
    if pos.get("dicht_ts") and pos.get("open_ts"):
        m["duur_minuten"] = max(0, round((pos["dicht_ts"] - pos["open_ts"]) / 60))
    return m


def mfe_mae(candles, open_ts, dicht_ts, entry, lang):
    """candles: [(t, o, h, l, c)] in servertijd. Max gunstige en ongunstige
    uitslag tijdens de trade, in points."""
    binnen = [c for c in candles if open_ts - 59 <= c[0] <= (dicht_ts or open_ts)]
    if not binnen:
        return None, None
    hoog = max(c[2] for c in binnen)
    laag = min(c[3] for c in binnen)
    mfe, mae = ((hoog - entry), (entry - laag)) if lang else ((entry - laag), (hoog - entry))
    return round(max(0.0, mfe) / POINT, 1), round(max(0.0, mae) / POINT, 1)


def candle_index(candles, ts):
    for i, c in enumerate(candles):
        if c[0] <= ts < c[0] + 60:
            return i
    return None


def sessie_label(tijd_hhmm, jcfg):
    import venster as _venster          # 1 okt 2026: Asia (01-09) + 2e uur Londen (10-15)
    return _venster.sessie(tijd_hhmm, jcfg)


def dagtype(d, jcfg):
    if d.weekday() >= 5:
        return "weekend"
    return "thuiswerk" if d.weekday() in jcfg.get("handelsdagen", []) else "kantoor"


# ------------------------------------------------------------------ database

KOLOMMEN = {
    "positie_id": "INTEGER", "lot": "REAL", "tijd_exit": "TEXT",
    "entry_prijs": "REAL", "exit_prijs": "REAL", "sl_prijs": "REAL", "tp_prijs": "REAL",
    "risico_eur": "REAL", "resultaat_r": "REAL", "duur_minuten": "INTEGER",
    "mfe_points": "REAL", "mae_points": "REAL", "minuut_in_uur": "INTEGER",
    "dagtype": "TEXT",
    "check_venster": "INTEGER", "check_dagmax": "INTEGER", "check_bias": "INTEGER",
    "check_entry50": "INTEGER", "check_sl": "INTEGER", "schoon": "INTEGER",
    "checks_vooraf": "INTEGER",
    "beoordeeld": "INTEGER",          # 0 = wacht op jouw checks/criteria
}

TABELLEN = """
CREATE TABLE IF NOT EXISTS mt5_verwerkt (
    positie_id INTEGER PRIMARY KEY,
    trade_id   INTEGER,
    actie      TEXT,                  -- nieuw | gekoppeld
    ts         TEXT
);
CREATE TABLE IF NOT EXISTS mt5_posities (
    positie_id    INTEGER PRIMARY KEY,
    symbool       TEXT,
    richting      TEXT,
    eerste_sl     REAL,
    eerste_tp     REAL,
    laatste_sl    REAL,
    laatste_tp    REAL,
    eerst_gezien  TEXT,
    laatst_gezien TEXT
);
"""


def verbind_db(pad=None):
    con = sqlite3.connect(pad or DB_PAD, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def zorg_schema(con):
    have = {r["name"] for r in con.execute("PRAGMA table_info(trades)")}
    for kol, typ in KOLOMMEN.items():
        if kol not in have:
            con.execute(f"ALTER TABLE trades ADD COLUMN {kol} {typ}")
    con.executescript(TABELLEN)
    con.commit()


def zoek_match(con, datum, tijd, pos, cfg):
    """Een trade die je zelf al logde: zelfde dag, zelfde resultaat (bruto of
    netto, binnen een paar cent), zelfde richting, en -- als er een tijd staat --
    binnen een kwartier."""
    rijen = con.execute(
        "SELECT id, tijd_entry, richting, resultaat_eur FROM trades "
        "WHERE datum=? AND positie_id IS NULL AND verwijderd_op IS NULL "
        "AND (status IS NULL OR status='genomen')", (datum,)).fetchall()
    t_pos = _minuten(tijd)
    beste, beste_verschil = None, None
    for r in rijen:
        if r["resultaat_eur"] is None:
            continue
        if min(abs(r["resultaat_eur"] - pos["bruto"]),
               abs(r["resultaat_eur"] - pos["netto"])) > cfg["match_marge_eur"]:
            continue
        if r["richting"] and r["richting"] != pos["richting"]:
            continue
        verschil = 0
        t_r = _minuten(r["tijd_entry"])
        if t_r is not None and t_pos is not None:
            verschil = abs(t_r - t_pos)
            if verschil > cfg["match_marge_min"]:
                continue
        if beste is None or verschil < beste_verschil:
            beste, beste_verschil = r, verschil
    return beste


def _heeft_screenshot(con, trade_id):
    return con.execute("SELECT 1 FROM screenshots WHERE trade_id=? LIMIT 1",
                       (trade_id,)).fetchone() is not None


def bewaar_chart(con, trade_id, datum, tijd, pos, sl, tp, rr, candles):
    """SVG van de minuutcandles met entry/SL/TP en je in- en uitstapmoment."""
    if not candles:
        return False
    import chart
    ohlc = [[c[1], c[2], c[3], c[4]] for c in candles]
    i_in = candle_index(candles, pos["open_ts"])
    i_uit = candle_index(candles, pos["dicht_ts"]) if pos.get("dicht_ts") else None
    t_uit = ""
    if pos.get("tijd_exit"):
        t_uit = pos["tijd_exit"]
    markers = [(i_in, chart.ENTRY_KLEUR, f"in {tijd}")]
    if i_uit is not None:
        kleur = chart.TP_KLEUR if pos["bruto"] >= 0 else chart.SL_KLEUR
        markers.append((i_uit, kleur, f"exit {t_uit}".strip()))
    svg = chart.maak_svg(
        ohlc, entry=pos["entry"], sl=sl, tp=tp, rr=rr, richting=pos["richting"],
        symbool=(pos["symbool"] or "XAUUSD").rstrip("+"),
        kop_extra=f"{datum[5:]} {tijd}  ·  MT5 #{pos['positie_id']}",
        markers=markers, markeer_laatste=False, exit_prijs=pos.get("exit"),
        zone_van=i_in, zone_tot=i_uit)
    daydir = os.path.join(SCREENSHOTS_DIR, datum)
    os.makedirs(daydir, exist_ok=True)
    fname = f"mt5_{pos['positie_id']}.svg"
    with open(os.path.join(daydir, fname), "w", encoding="utf-8") as f:
        f.write(svg)
    con.execute(
        "INSERT INTO screenshots (trade_id, no_trade_id, pad, beschrijving, type) "
        "VALUES (?,?,?,?,?)",
        (trade_id, None, f"screenshots/{datum}/{fname}",
         "Chart uit MetaTrader 5 (automatisch): entry, exit, SL en TP", "entry"))
    return True


# ------------------------------------------------------------------ de koppeling

class VerbindFout(Exception):
    pass


class Koppeling:
    """Eén instantie per journal-proces. mt5 mag een nep-object zijn (tests)."""

    def __init__(self, mt5=None, db_pad=None):
        self.mt5 = mt5
        self.db_pad = db_pad
        self.verbonden = False
        self.offset = None
        self.eerste_ronde = True
        self.wekker = threading.Event()
        self.bij_nieuwe_trade = []        # callbacks(trade_id)
        self.na_ronde = []                # callbacks(koppeling), zelfde thread -> MT5 veilig
        self.status = {
            "aan": True, "verbonden": False, "melding": "nog niet gestart",
            "laatste_ronde": None, "laatste_nieuw": None, "account": None,
            "server": None, "valuta": None, "offset_uur": None,
            "offset_bron": None, "open_posities": 0, "fout": None,
        }

    # ---- MT5
    def _mt5(self):
        if self.mt5 is None:
            try:
                import MetaTrader5 as m          # noqa: N813
            except ImportError:
                raise VerbindFout("Het MetaTrader5-pakket is nog niet geinstalleerd. "
                                  "Sluit de journal en start START-JOURNAL.bat opnieuw.")
            self.mt5 = m
        return self.mt5

    def verbind(self, cfg):
        mt5 = self._mt5()
        pad = (cfg.get("terminal_pad") or "").strip().strip('"')
        if pad:
            if pad.startswith("\\") and not pad.startswith("\\\\"):
                pad = "C:" + pad                         # schijfletter kwijtgeraakt
            if os.path.isdir(pad):
                pad = os.path.join(pad, "terminal64.exe")  # map i.p.v. het programma
        ok = mt5.initialize(pad) if pad else mt5.initialize()
        if not ok and pad:
            eerste = mt5.last_error() if hasattr(mt5, "last_error") else ""
            ok = mt5.initialize()                        # dan de MT5 die al openstaat
            if ok:
                log(f"terminal_pad '{pad}' werkte niet ({eerste}); verbonden met de MT5 die openstaat")
        if not ok:
            fout = mt5.last_error() if hasattr(mt5, "last_error") else ""
            raise VerbindFout(f"MetaTrader 5 niet bereikbaar {fout}. Staat MT5 open "
                              "en ben je ingelogd bij Vantage?")
        acc = mt5.account_info()
        if acc is None:
            raise VerbindFout("MT5 draait, maar er is geen account ingelogd.")
        self.verbonden = True
        self.status.update(verbonden=True, account=f"…{str(acc.login)[-3:]}",
                           server=getattr(acc, "server", None),
                           valuta=getattr(acc, "currency", None))
        log(f"verbonden met MT5 ({self.status['server']}, account {self.status['account']})")

    def verbreek(self):
        if self.mt5 is not None and self.verbonden:
            try:
                self.mt5.shutdown()
            except Exception:
                pass
        self.verbonden = False
        self.status["verbonden"] = False

    def _bepaal_offset(self, cfg):
        mt5 = self.mt5
        for sym in [cfg.get("symbool"), "XAUUSD+", "XAUUSD"]:
            if not sym:
                continue
            try:
                mt5.symbol_select(sym, True)
                tick = mt5.symbol_info_tick(sym)
            except Exception:
                tick = None
            if tick is not None:
                uur = detecteer_offset(getattr(tick, "time", 0), time.time())
                if uur is not None:
                    self.offset = uur
                    self.status.update(offset_uur=uur, offset_bron="automatisch (live koers)")
                    return uur
        if self.offset is None:
            self.offset = int(cfg.get("broker_offset_uur", 3))
            self.status.update(offset_uur=self.offset, offset_bron="config (markt dicht)")
        return self.offset

    def _candles(self, symbool, van_ts, tot_ts):
        try:
            r = self.mt5.copy_rates_range(
                symbool, getattr(self.mt5, "TIMEFRAME_M1", TIMEFRAME_M1),
                datetime.fromtimestamp(int(van_ts), tz=timezone.utc),
                datetime.fromtimestamp(int(tot_ts), tz=timezone.utc))
        except Exception:
            r = None
        if r is None:
            return []
        return [(int(x["time"]), float(x["open"]), float(x["high"]),
                 float(x["low"]), float(x["close"])) for x in r]

    # ---- één ronde
    def ronde(self, cfg=None):
        cfg = cfg or lees_config()
        self.status["aan"] = bool(cfg.get("aan", True))
        if not self.status["aan"]:
            self.status["melding"] = "uitgezet in journal_config.json"
            return []
        if not self.verbonden:
            self.verbind(cfg)
        mt5 = self.mt5
        ti = mt5.terminal_info() if hasattr(mt5, "terminal_info") else None
        if ti is not None and not getattr(ti, "connected", True):
            self.status["melding"] = "MT5 staat open maar heeft geen verbinding met de server"
            return []
        offset = self._bepaal_offset(cfg)
        bevat = (cfg.get("symbool_bevat") or "").upper()
        try:
            acc = mt5.account_info()        # v2: balans lezen VOOR de deals
        except Exception:
            acc = None
        if acc is not None and getattr(acc, "balance", None) is None:
            acc = None                      # (test-)account zonder balans: overslaan
        if acc is not None:
            self.status.update(balans=round(float(acc.balance), 2),
                               equity=round(float(getattr(acc, "equity", acc.balance)), 2),
                               zwevend=round(float(getattr(acc, "profit", 0) or 0), 2),
                               margin_level=round(float(getattr(acc, "margin_level", 0) or 0), 1))

        con = verbind_db(self.db_pad)
        nieuw_ids = []
        try:
            zorg_schema(con)
            self._volg_open_posities(con, bevat)
            # eerste ronde: alles vanaf sync_vanaf; daarna alleen de laatste 3 dagen
            vanaf = datetime.fromisoformat(cfg["sync_vanaf"]).replace(tzinfo=timezone.utc)
            van = vanaf - timedelta(days=1)
            if not self.eerste_ronde:
                van = max(van, datetime.now(timezone.utc) - timedelta(days=3))
            tot = datetime.now(timezone.utc) + timedelta(days=2)
            deals = mt5.history_deals_get(van, tot)
            if deals is None:
                raise VerbindFout(f"history_deals_get gaf niets terug {mt5.last_error()}")
            posities = groepeer([_deal_dict(d) for d in deals])
            verwerkt = {r[0] for r in con.execute("SELECT positie_id FROM mt5_verwerkt")}
            for pid, pos in sorted(posities.items(), key=lambda kv: kv[1]["open_ts"]):
                if not pos["gesloten"] or pid in verwerkt:
                    continue
                if bevat and bevat not in (pos["symbool"] or "").upper():
                    continue
                if server_naar_amsterdam(pos["open_ts"], offset).date() < vanaf.date():
                    continue
                tid, actie = self._verwerk(con, pos, offset, cfg)
                if actie == "nieuw":
                    nieuw_ids.append(tid)
            con.commit()
            self._saldo(con, deals, acc, offset, vanaf, cfg)
            con.commit()
        finally:
            con.close()

        # v2: marktdata bijhouden + nieuwe trades verrijken (nooit fataal)
        try:
            import marktdata
            n = marktdata.verzamel_candles(mt5, cfg.get("symbool") or "XAUUSD+", offset)
            if n or nieuw_ids or self.eerste_ronde:
                marktdata.verrijk_trades(cfg.get("symbool") or "XAUUSD+", pad=self.db_pad)
        except Exception as e:
            log(f"marktdata: {e}")

        self.eerste_ronde = False
        self.status.update(laatste_ronde=datetime.now().isoformat(timespec="seconds"),
                           melding="actief", fout=None)
        if nieuw_ids:
            self.status["laatste_nieuw"] = datetime.now().isoformat(timespec="seconds")
            for tid in nieuw_ids:
                for cb in list(self.bij_nieuwe_trade):
                    try:
                        cb(tid)
                    except Exception as e:
                        log(f"melding voor trade #{tid} mislukt: {e}")
        return nieuw_ids

    def _saldo(self, con, deals, acc, offset, vanaf, cfg):
        """v2: stortingen/opnames uit MT5 + het journal-saldo gelijk aan MT5."""
        try:
            from app import saldo
        except Exception as e:
            log(f"saldo-module niet geladen: {e}")
            return
        saldo.zorg_schema(con)
        for d in deals:
            dd = _deal_dict(d)
            if dd.get("position_id") or dd.get("type") in (TYPE_BUY, TYPE_SELL):
                continue
            if not dd.get("ticket") or not dd.get("profit"):
                continue
            ams = server_naar_amsterdam(dd["time"], offset)
            if ams.date() < vanaf.date():
                continue
            if saldo.importeer_balansdeal(con, int(dd["ticket"]), ams.strftime("%Y-%m-%d"),
                                          ams.strftime("%H:%M"), float(dd["profit"]),
                                          int(dd.get("type") or 2), dd.get("comment") or ""):
                log(f"kasstroom uit MT5: {ams:%Y-%m-%d %H:%M} {float(dd['profit']):+.2f}")
        if acc is None:
            return
        saldo.log_account(con, acc, self.status.get("open_posities") or 0)
        if cfg.get("saldo_volgen", True):
            v = saldo.aansluiten(con, float(acc.balance))
            self.status["aansluiting_vandaag"] = v

    def _volg_open_posities(self, con, bevat):
        """Onthoud SL/TP van open posities, zodat het oorspronkelijke risico
        bekend blijft als je later schuift."""
        try:
            posities = self.mt5.positions_get() or ()
        except Exception:
            posities = ()
        nu = datetime.now().isoformat(timespec="seconds")
        n = 0
        for p in posities:
            sym = getattr(p, "symbol", "") or ""
            if bevat and bevat not in sym.upper():
                continue
            n += 1
            pid = int(getattr(p, "identifier", 0) or getattr(p, "ticket", 0))
            sl = float(getattr(p, "sl", 0) or 0) or None
            tp = float(getattr(p, "tp", 0) or 0) or None
            richting = "long" if getattr(p, "type", 0) == TYPE_BUY else "short"
            rij = con.execute("SELECT * FROM mt5_posities WHERE positie_id=?", (pid,)).fetchone()
            try:
                import marktdata
                marktdata.log_positie(con, pid, sl, tp, float(getattr(p, "price_current", 0) or 0),
                                      float(getattr(p, "profit", 0) or 0),
                                      float(getattr(p, "volume", 0) or 0), nieuw=rij is None)
            except Exception as e:
                log(f"positie-tijdlijn: {e}")
            if rij is None:
                con.execute(
                    "INSERT INTO mt5_posities (positie_id, symbool, richting, eerste_sl, "
                    "eerste_tp, laatste_sl, laatste_tp, eerst_gezien, laatst_gezien) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", (pid, sym, richting, sl, tp, sl, tp, nu, nu))
            else:
                con.execute(
                    "UPDATE mt5_posities SET eerste_sl=COALESCE(eerste_sl, ?), "
                    "eerste_tp=COALESCE(eerste_tp, ?), laatste_sl=?, laatste_tp=?, "
                    "laatst_gezien=? WHERE positie_id=?", (sl, tp, sl, tp, nu, pid))
        self.status["open_posities"] = n

    def _order_niveaus(self, pos):
        try:
            orders = self.mt5.history_orders_get(position=pos["positie_id"]) or ()
        except Exception:
            orders = ()
        sl = tp = None
        # de order waarmee je instapte eerst, daarna de rest
        orders = sorted(orders, key=lambda o: (getattr(o, "ticket", 0) != pos.get("order_id"),
                                               getattr(o, "time_setup", 0)))
        for o in orders:
            if sl is None and getattr(o, "sl", 0):
                sl = float(o.sl)
            if tp is None and getattr(o, "tp", 0):
                tp = float(o.tp)
        return sl, tp

    def _verwerk(self, con, pos, offset, cfg):
        jcfg = lees_journal_config()
        o_sl, o_tp = self._order_niveaus(pos)
        gezien = con.execute("SELECT * FROM mt5_posities WHERE positie_id=?",
                             (pos["positie_id"],)).fetchone()
        sl, tp = bepaal_niveaus(pos, o_sl, o_tp, dict(gezien) if gezien else None)
        m = bereken(pos, sl, tp)

        open_ams = server_naar_amsterdam(pos["open_ts"], offset)
        datum, tijd = open_ams.strftime("%Y-%m-%d"), open_ams.strftime("%H:%M")
        tijd_exit = (server_naar_amsterdam(pos["dicht_ts"], offset).strftime("%H:%M")
                     if pos.get("dicht_ts") else None)
        pos = dict(pos, tijd_exit=tijd_exit)

        # candles: 90 min ervoor (30 bij lange trades), tot 10 min na de exit
        duur = m["duur_minuten"] or 0
        voor = 30 if duur > 240 else 90
        candles = self._candles(pos["symbool"], pos["open_ts"] - voor * 60,
                                (pos["dicht_ts"] or pos["open_ts"]) + 10 * 60)
        if len(candles) > 400:
            candles = candles[-400:]
        mfe, mae = mfe_mae(candles, pos["open_ts"], pos["dicht_ts"], pos["entry"],
                           pos["richting"] == "long")
        reden = REDEN_TEKST.get(pos.get("reden"), "gesloten")

        extra = {
            "positie_id": pos["positie_id"], "lot": pos["lot"], "tijd_exit": tijd_exit,
            "entry_prijs": round(pos["entry"], 2),
            "exit_prijs": round(pos["exit"], 2) if pos["exit"] is not None else None,
            "sl_prijs": sl, "tp_prijs": tp, "risico_eur": m["risico_eur"],
            "resultaat_r": m["resultaat_r"], "duur_minuten": m["duur_minuten"],
            "mfe_points": mfe, "mae_points": mae, "minuut_in_uur": open_ams.minute,
            "dagtype": dagtype(open_ams.date(), jcfg),
        }

        match = zoek_match(con, datum, tijd, pos, cfg)
        if match is not None:
            tid = match["id"]
            oud = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
            zet = dict(extra)
            # broker is leidend voor geld; wat jij al invulde blijft staan
            zet.update(resultaat_eur=pos["bruto"], charges=pos["charges"])
            for kol, waarde in (("entry", round(pos["entry"], 2)), ("sl", sl), ("tp", tp),
                                ("rr", m["rr"]), ("sl_afstand_points", m["sl_afstand_points"]),
                                ("tp_afstand_points", m["tp_afstand_points"]),
                                ("exit_reden", reden), ("richting", pos["richting"])):
                if oud[kol] in (None, ""):
                    zet[kol] = waarde
            al_beoordeeld = any((oud[k] or "maybe") != "maybe"
                                for k in ("f2_bias", "f2_dxy", "f2_expansie", "f2_sweep", "f2_shift"))
            zet["beoordeeld"] = 1 if al_beoordeeld else 0
            sets = ", ".join(f"{k}=?" for k in zet) + ", updated_at=datetime('now')"
            con.execute(f"UPDATE trades SET {sets} WHERE id=?", list(zet.values()) + [tid])
            if not _heeft_screenshot(con, tid):
                bewaar_chart(con, tid, datum, tijd, pos, sl, tp, m["rr"], candles)
            actie = "gekoppeld"
            log(f"positie {pos['positie_id']} gekoppeld aan je eigen trade #{tid} ({datum} {tijd})")
        else:
            from app import db, cbr
            regels = [f"Automatisch uit MetaTrader 5 · positie #{pos['positie_id']} · "
                      f"{pos['lot']:.2f} lot · {reden} na {m['duur_minuten'] or 0} min."]
            if sl is None:
                regels.append("SL niet bekend bij de broker (vul hem aan als je hem weet).")
            regels.append("Loggen: setup-checklist + emotie (Telegram of 'Nog te loggen' op de homepage).")
            payload = {k: "maybe" for k in VINKJES_MAYBE}
            payload.update(
                datum=datum, tijd_entry=tijd, instrument="XAUUSD",
                sessie=sessie_label(tijd, jcfg), richting=pos["richting"],
                rr=m["rr"], entry=round(pos["entry"], 2), sl=sl, tp=tp,
                status="genomen", bron="live", fase=cbr.FASE_ACTIEF,
                resultaat_eur=pos["bruto"], charges=pos["charges"], exit_reden=reden,
                sl_afstand_points=m["sl_afstand_points"],
                tp_afstand_points=m["tp_afstand_points"],
                tags="mt5-auto", notities="\n".join(regels))
            payload["grade"] = cbr.compute_grade_f2(payload)
            tid = db._insert_trade(con, payload)
            zet = dict(extra, beoordeeld=0, checks_vooraf=0)
            sets = ", ".join(f"{k}=?" for k in zet)
            con.execute(f"UPDATE trades SET {sets} WHERE id=?", list(zet.values()) + [tid])
            bewaar_chart(con, tid, datum, tijd, pos, sl, tp, m["rr"], candles)
            actie = "nieuw"
            log(f"nieuwe trade #{tid}: {datum} {tijd} {pos['richting']} "
                f"{pos['bruto']:+.2f} ({reden})")

        con.execute("INSERT OR REPLACE INTO mt5_verwerkt (positie_id, trade_id, actie, ts) "
                    "VALUES (?,?,?,?)", (pos["positie_id"], tid, actie,
                                         datetime.now().isoformat(timespec="seconds")))
        return tid, actie

    # ---- achtergrond
    def loop(self):
        time.sleep(3)
        while True:
            cfg = lees_config()
            wacht = max(10, int(cfg.get("interval_sec") or 30))
            try:
                self.ronde(cfg)
                for cb in list(self.na_ronde):
                    try:
                        cb(self)
                    except Exception as e:
                        log(f"na_ronde mislukt: {e}")
            except VerbindFout as e:
                self.verbreek()
                self.status.update(melding=str(e), fout=str(e))
                wacht = max(wacht, 60)
            except Exception as e:
                self.verbreek()
                self.status.update(melding="fout in de koppeling (zie mt5_koppeling.log)",
                                   fout=str(e))
                log("FOUT: " + traceback.format_exc())
                wacht = max(wacht, 60)
            self.wekker.wait(wacht)
            self.wekker.clear()

    def nu_synchroniseren(self):
        self.wekker.set()


def _deal_dict(d):
    return {k: getattr(d, k, None) for k in
            ("ticket", "position_id", "entry", "type", "volume", "price", "time", "profit",
             "commission", "swap", "fee", "symbol", "reason", "comment", "order")}


# ------------------------------------------------------------------ status voor de journal

_KOPPELING = None


def start_achtergrond():
    """Wordt één keer aangeroepen vanuit app/main.py. CBR_GEEN_MT5=1 zet hem uit
    (handig voor tests)."""
    global _KOPPELING
    if _KOPPELING is not None or os.environ.get("CBR_GEEN_MT5"):
        return _KOPPELING
    _KOPPELING = Koppeling()
    threading.Thread(target=_KOPPELING.loop, name="mt5-koppeling", daemon=True).start()
    return _KOPPELING


def koppeling():
    return _KOPPELING


def status(db_pad=None):
    s = dict(_KOPPELING.status) if _KOPPELING else {
        "aan": lees_config().get("aan", True), "verbonden": False,
        "melding": "koppeling niet gestart"}
    try:
        con = verbind_db(db_pad)
        try:
            zorg_schema(con)
            s["te_beoordelen"] = con.execute(
                "SELECT COUNT(*) FROM trades WHERE beoordeeld=0 AND verwijderd_op IS NULL"
            ).fetchone()[0]
            s["vandaag_mt5"] = con.execute(
                "SELECT COUNT(*) FROM trades WHERE positie_id IS NOT NULL AND datum=? "
                "AND verwijderd_op IS NULL", (date.today().isoformat(),)).fetchone()[0]
        finally:
            con.close()
    except Exception as e:
        s["db_fout"] = str(e)
    return s
