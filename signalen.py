# -*- coding: utf-8 -*-
"""
signalen.py -- de signaalwachter, nu IN de journal (23 sep 2026).

Eén programma, één database, één Telegram-bot:
  * elke ronde van de MT5-koppeling haalt deze module de laatste 1-minuut-
    candles op en zoekt jouw setup (setup_detector.py);
  * nieuwe stappen gaan als bericht via de journal-bot:
        🟡 opgelet   impuls gezien, ik zoek de sweep
        🟠 klaar     sweep + BOS: entry, SL en TP staan vast   [✅ genomen] [❌ niet]
        🟢 entry     prijs raakt je entry
        🎯/🛑        TP of SL (stil, voor de statistiek)
        ⚪ vervallen met de reden (stil)
  * sluit MT5 een trade die bij een signaal past, dan staat dat signaal
    vanzelf op 'genomen' en hangt het aan die trade;
  * alles komt in de tabel 'signalen' van cbr_journal.db, en in een leesbaar
    log per dag: logs/signalen_JJJJ-MM-DD.log (alleen regels die iets nieuws zeggen).

Geen bias, geen DXY. Alleen lezen uit MT5, nooit handelen.

Instellingen: journal_config.json -> "signalen" (wordt elke ronde herlezen).
"""

import json
import os
import sqlite3
import threading
import time
import traceback
from datetime import datetime, timedelta

import setup_detector as D
import venster as _venster

HIER = os.path.dirname(os.path.abspath(__file__))
DB_PAD = os.path.join(HIER, "cbr_journal.db")
CONFIG_PAD = os.path.join(HIER, "journal_config.json")
LOG_DIR = os.path.join(HIER, "logs")

RUNTIME = {
    "aan": True,
    "symbool": "XAUUSD+",
    "candles": 300,              # zoveel minuten terug kijken
    "vers_seconden": 180,        # oudere gebeurtenissen bij (her)start niet meer pushen
    "stil": ["vervallen", "tp", "sl", "onbeslist"],   # zonder geluid
    "koppel_marge_points": 20,   # MT5-trade hoort bij een signaal als de entry zo dichtbij ligt
    "koppel_minuten": 60,        # ... en hij binnen zoveel minuten na de BOS opende
}

_STATUS = {"aan": True, "melding": "nog niet gestart", "laatste_ronde": None,
           "candles": 0, "levend": 0, "fout": None, "laatste_candle": None}
_EERSTE_LIVE_TS = None
_LOCK = threading.Lock()


# ------------------------------------------------------------------ config

def lees_config():
    try:
        with open(CONFIG_PAD, encoding="utf-8") as f:
            root = json.load(f)
    except (FileNotFoundError, ValueError):
        root = {}
    eigen = root.get("signalen") or {}
    cfg = {**D.STANDAARD, **RUNTIME, **{k: v for k, v in eigen.items() if not k.startswith("_")}}
    cfg["venster_van"] = root.get("venster_van", "11:00")
    cfg["venster_tot"] = root.get("venster_tot", "12:00")
    cfg["venster"] = root.get("venster")          # lijst met blokken (1 okt 2026: Asia + 10-15)
    cfg["handelsdagen"] = root.get("handelsdagen")
    return cfg


def status():
    return dict(_STATUS)


# ------------------------------------------------------------------ opmaak

def _p(x):
    return "–" if x is None else f"{x:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _hm(dt):
    return dt.strftime("%H:%M") if dt else "–"


def _minuten(hhmm):
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def venster_label(dt, cfg):
    """'' binnen je venster op een handelsdag, anders een korte toevoeging."""
    stukken = []
    dagen = cfg.get("handelsdagen")
    if dagen and dt.weekday() not in dagen:
        stukken.append("geen handelsdag")
    nu = dt.hour * 60 + dt.minute
    if _venster.binnen(nu, cfg) is False:
        stukken.append("buiten venster")
    return (" · <i>" + ", ".join(stukken) + "</i>") if stukken else ""


# ------------------------------------------------------------------ database

SCHEMA = """
CREATE TABLE IF NOT EXISTS signalen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sleutel TEXT UNIQUE,
    datum TEXT, trade TEXT, impuls_richting TEXT,
    impuls_van_tijd TEXT, impuls_tot_tijd TEXT, impuls_van REAL, impuls_tot REAL,
    impuls_candles INTEGER, kracht REAL, overlap REAL, efficientie REAL,
    eq REAL, top REAL, pullback REAL, sweep REAL, sweep_tijd TEXT, bos_tijd TEXT,
    entry REAL, sl REAL, tp REAL, risico_points REAL,
    entry_tijd TEXT, uitkomst_tijd TEXT, geldig_tot TEXT,
    status TEXT, reden TEXT, in_venster INTEGER,
    genomen INTEGER, trade_id INTEGER,
    gemeld TEXT DEFAULT '[]', bericht_id INTEGER, candles TEXT,
    aangemaakt TEXT, bijgewerkt TEXT
);
CREATE TABLE IF NOT EXISTS signaal_berichten (
    message_id INTEGER PRIMARY KEY, signaal_id INTEGER, soort TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS signaal_opmerkingen (
    id INTEGER PRIMARY KEY AUTOINCREMENT, signaal_id INTEGER, ts TEXT, tekst TEXT, bron TEXT
);
CREATE INDEX IF NOT EXISTS idx_sig_opm ON signaal_opmerkingen(signaal_id);
"""

# Kolommen die er sinds 1 okt 2026 bij zijn (oordeel + chart). Wordt bij de eerste
# verbinding per database automatisch toegevoegd; bestaande signalen blijven staan.
NIEUWE_KOLOMMEN = {"oordeel": "TEXT", "oordeel_ts": "TEXT", "chart_pad": "TEXT", "chart_status": "TEXT"}
_GEMIGREERD = set()


def _migreer(con, pad):
    if pad in _GEMIGREERD:
        return
    aanwezig = {r[1] for r in con.execute("PRAGMA table_info(signalen)")}
    for kol, typ in NIEUWE_KOLOMMEN.items():
        if kol not in aanwezig:
            try:
                con.execute(f"ALTER TABLE signalen ADD COLUMN {kol} {typ}")
            except sqlite3.OperationalError:
                pass
    # oude knop-antwoorden (genomen=1/0) meenemen als oordeel
    con.execute("UPDATE signalen SET oordeel='genomen' WHERE oordeel IS NULL AND genomen=1")
    con.execute("UPDATE signalen SET oordeel='niet' WHERE oordeel IS NULL AND genomen=0")
    con.commit()
    _GEMIGREERD.add(pad)


def conn(pad=None):
    pad = pad or DB_PAD
    con = sqlite3.connect(pad, timeout=20)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _migreer(con, pad)
    return con


# ------------------------------------------------------------------ log

def _log_pad(dt):
    os.makedirs(LOG_DIR, exist_ok=True)
    return os.path.join(LOG_DIR, f"signalen_{dt:%Y-%m-%d}.log")


_LAATSTE_LOGREGEL = {"tekst": None, "rust_dt": None}


def log_regel(dt, tekst, altijd=False):
    """Schrijft alleen als er iets anders staat dan de vorige keer. 'Geen setup'-
    regels hoogstens eens per 5 minuten, zodat het log leesbaar blijft."""
    if not altijd:
        if tekst == _LAATSTE_LOGREGEL["tekst"]:
            return
        rust = tekst.startswith("geen setup")
        vorige_rust = (_LAATSTE_LOGREGEL["tekst"] or "").startswith("geen setup")
        if rust and vorige_rust and _LAATSTE_LOGREGEL["rust_dt"] is not None \
                and dt - _LAATSTE_LOGREGEL["rust_dt"] < timedelta(minutes=5):
            return
        _LAATSTE_LOGREGEL["tekst"] = tekst
        if rust:
            _LAATSTE_LOGREGEL["rust_dt"] = dt
    try:
        with open(_log_pad(dt), "a", encoding="utf-8") as f:
            f.write(f"[{dt:%H:%M}] {tekst}\n")
    except OSError:
        pass


def laatste_logregels(n=15, dt=None):
    dt = dt or datetime.now()
    for dag in (dt, dt - timedelta(days=1)):
        pad = _log_pad(dag)
        if os.path.exists(pad):
            with open(pad, encoding="utf-8") as f:
                return os.path.basename(pad), f.read().splitlines()[-n:]
    return None, []


# ------------------------------------------------------------------ Telegram

def _bot():
    import journal_bot
    return journal_bot


def _stuur(tekst, knoppen=None, stil=False, antwoord_op=None):
    jb = _bot()
    c = jb.cfg()
    if not (c["aan"] and c["token"] and c["chat_id"]):
        return None
    data = {"chat_id": c["chat_id"], "text": tekst, "parse_mode": "HTML",
            "disable_notification": bool(stil)}
    if knoppen:
        data["reply_markup"] = knoppen
    if antwoord_op:
        data["reply_to_message_id"] = antwoord_op
        data["allow_sending_without_reply"] = True
    r = jb.api(c["token"], "sendMessage", data)
    return (r.get("result") or {}).get("message_id")


# Je oordeel over een signaal (1 okt 2026). Eerste twee: wat je deed. Laatste twee:
# je zag het niet op tijd -- had je het genomen als je had gekeken?
OORDELEN = {
    "genomen": ("g", "✅ Genomen", "genomen"),
    "niet": ("n", "❌ Niet genomen", "niet genomen"),
    "gemist_wel": ("w", "⏱ Gemist: wel", "gemist, had ik wél genomen"),
    "gemist_niet": ("x", "⏱ Gemist: niet", "gemist, had ik níét genomen"),
}
CB_CODE = {v[0]: k for k, v in OORDELEN.items()}
CB_CODE.update({"1": "genomen", "0": "niet"})          # knoppen van vóór 1 okt
OORDEEL_KORT = {"genomen": "✅ genomen", "niet": "❌ niet genomen",
                "gemist_wel": "⏱ gemist: wel", "gemist_niet": "⏱ gemist: niet"}


def oordeel_van(r):
    """Het oordeel van een signaal-rij; oude genomen=1/0-waarden tellen mee."""
    try:
        o = r["oordeel"]
    except (KeyError, IndexError):
        o = None
    if o:
        return o
    g = r["genomen"]
    return "genomen" if g == 1 else ("niet" if g == 0 else None)


def knoppen(sid, oordeel=None):
    """2x2 knoppen onder 'klaar'. Het gekozen antwoord krijgt een ● ervoor."""
    if oordeel in (0, 1):                      # oude aanroepen gaven genomen=1/0
        oordeel = "genomen" if oordeel == 1 else "niet"

    def knop(sleutel):
        code, tekst, _ = OORDELEN[sleutel]
        return {"text": ("● " if oordeel == sleutel else "") + tekst, "callback_data": f"s:{sid}:{code}"}

    return {"inline_keyboard": [[knop("genomen"), knop("niet")],
                                [knop("gemist_wel"), knop("gemist_niet")]]}


def _sluit_knoppen(con, sid):
    """Een signaal waarvan de entry nooit geraakt werd: niets te beoordelen. Vervang de
    vier knoppen door één rustig label, tenzij je al een oordeel gaf."""
    try:
        r = con.execute("SELECT * FROM signalen WHERE id=?", (sid,)).fetchone()
        if r is None or not r["bericht_id"] or r["bos_tijd"] is None or r["entry_tijd"] is not None:
            return
        if oordeel_van(r):
            return
        jb = _bot()
        c = jb.cfg()
        if not (c["aan"] and c["token"] and c["chat_id"]):
            return
        jb.api(c["token"], "editMessageReplyMarkup", {
            "chat_id": c["chat_id"], "message_id": r["bericht_id"],
            "reply_markup": {"inline_keyboard": [[
                {"text": "⚪ Entry nooit geraakt", "callback_data": f"s:{sid}:z"}]]}})
    except Exception as e:
        print("[signalen] knoppen sluiten:", e)


def tekst_voor(soort, r, cfg):
    richting = (r["trade"] or "").upper()
    omhoog = r["impuls_richting"] == "up"
    extra = venster_label(datetime.fromisoformat(r["datum"] + "T" + (r["impuls_tot_tijd"] or "00:00")), cfg)
    if soort == "opgelet":
        pts = abs((r["impuls_tot"] or 0) - (r["impuls_van"] or 0)) / cfg["punt"]
        kant = "boven" if omhoog else "onder"
        close = "onder" if omhoog else "boven"
        try:
            h, m = map(int, r["impuls_tot_tijd"].split(":"))
            deadline = (datetime(2000, 1, 1, h, m) + timedelta(minutes=cfg["top_geldig_candles"])).strftime("%H:%M")
        except (ValueError, AttributeError):
            deadline = "?"
        kracht = f"{r['kracht']:.1f}".replace(".", ",")
        return (f"🟡 <b>Impuls {'omhoog' if omhoog else 'omlaag'}</b> · {pts:.0f} pts "
                f"({r['impuls_van_tijd']}–{r['impuls_tot_tijd']}, {kracht}× ATR){extra}\n"
                f"Ik zoek nu een <b>{richting}</b>:\n"
                f"• sweep {kant} <b>{_p(r['top'])}</b> vóór {deadline} "
                f"(max {cfg['sweep_max_points']} pts erdoor)\n"
                f"• dan een close {close} de mini-pullback\n"
                f"50% van de impuls: {_p(r['eq'])} — raakt prijs die eerst, dan vervalt hij.")
    if soort == "rijp":
        return (f"🟠 <b>{richting} klaar</b>{extra}\n"
                f"Sweep {_p(r['sweep'])} ({r['sweep_tijd']}) · BOS {r['bos_tijd']}\n"
                f"Entry <b>{_p(r['entry'])}</b>\n"
                f"SL {_p(r['sl'])} ({r['risico_points']:.0f} pts)\n"
                f"TP {_p(r['tp'])} (1:1)\n"
                f"<i>Geldig tot {r['geldig_tot']}, of tot prijs {_p(r['eq'])} raakt.</i>")
    if soort == "entry":
        return f"🟢 <b>Entry geraakt</b> · {richting} {_p(r['entry'])} om {r['entry_tijd']}"
    if soort == "tp":
        return f"🎯 TP geraakt om {r['uitkomst_tijd']} ({richting} #{r['id']})"
    if soort == "sl":
        return f"🛑 SL geraakt om {r['uitkomst_tijd']} ({richting} #{r['id']})"
    if soort == "onbeslist":
        return f"❔ Onbeslist: {r['reden']} ({richting} #{r['id']})"
    if soort == "vervallen":
        return f"⚪ Vervallen ({richting} #{r['id']}): {r['reden']}"
    return f"{soort} #{r['id']}"


# ------------------------------------------------------------------ één ronde

def _tijd(ts, offset):
    import mt5_koppeling as K
    return K.server_naar_amsterdam(ts, offset)


def verwerk(con, setups, bars, offset, cfg, nu_ts, stuur=True):
    """Zet de setups in de database en pusht wat nieuw is. Geeft [(soort, id)] terug."""
    global _EERSTE_LIVE_TS
    if _EERSTE_LIVE_TS is None:
        _EERSTE_LIVE_TS = nu_ts
    verstuurd = []
    for s in setups:
        top_dt = _tijd(s.top_tijd, offset)
        f = lambda ts: _hm(_tijd(ts, offset)) if ts is not None else None   # noqa: E731
        geldig = None
        if s.bos_tijd is not None:
            geldig = _hm(_tijd(s.bos_tijd + 60 * (cfg["entry_max_candles"] + 1), offset))
        velden = dict(
            sleutel=s.sleutel, datum=top_dt.date().isoformat(), trade=s.trade,
            impuls_richting=s.impuls_richting,
            impuls_van_tijd=f(s.impuls["van_tijd"]), impuls_tot_tijd=f(s.impuls["tot_tijd"]),
            impuls_van=s.impuls["van"], impuls_tot=s.impuls["tot"],
            impuls_candles=s.impuls["candles"], kracht=s.impuls["kracht"],
            overlap=s.impuls["overlap"], efficientie=s.impuls["efficientie"],
            eq=s.eq, top=s.top, pullback=s.pullback, sweep=s.sweep,
            sweep_tijd=f(s.sweep_tijd), bos_tijd=f(s.bos_tijd),
            entry=s.entry, sl=s.sl, tp=s.tp, risico_points=s.risico_points,
            entry_tijd=f(s.entry_tijd), uitkomst_tijd=f(s.uitkomst_tijd), geldig_tot=geldig,
            status=s.status, reden=s.reden,
            in_venster=0 if venster_label(top_dt, cfg) else 1,
            bijgewerkt=datetime.now().isoformat(timespec="seconds"),
        )
        rij = con.execute("SELECT * FROM signalen WHERE sleutel=?", (s.sleutel,)).fetchone()
        if rij is None:
            velden["aangemaakt"] = velden["bijgewerkt"]
            if s.bos_tijd is not None:
                velden["candles"] = json.dumps([list(b) for b in bars[-120:]])
            kol = ", ".join(velden)
            con.execute(f"INSERT INTO signalen ({kol}) VALUES ({', '.join('?' * len(velden))})",
                        list(velden.values()))
            rij = con.execute("SELECT * FROM signalen WHERE sleutel=?", (s.sleutel,)).fetchone()
        else:
            if s.bos_tijd is not None and not rij["candles"]:
                velden["candles"] = json.dumps([list(b) for b in bars[-120:]])
            con.execute(f"UPDATE signalen SET {', '.join(k + '=?' for k in velden)} WHERE id=?",
                        list(velden.values()) + [rij["id"]])
            rij = con.execute("SELECT * FROM signalen WHERE id=?", (rij["id"],)).fetchone()
        con.commit()

        gemeld = json.loads(rij["gemeld"] or "[]")
        for soort, ts in s.events:
            if soort in gemeld:
                continue
            gemeld.append(soort)
            vers = ts >= _EERSTE_LIVE_TS - cfg["vers_seconden"]
            # 'vervallen' alleen melden als je eerder iets over deze setup kreeg
            if soort == "vervallen" and not any(g in gemeld for g in ("opgelet", "rijp")):
                vers = False
            if stuur and vers:
                try:
                    mid = _stuur(
                        tekst_voor(soort, rij, cfg),
                        knoppen=knoppen(rij["id"], oordeel_van(rij)) if soort == "rijp" else None,
                        stil=soort in cfg["stil"],
                        antwoord_op=rij["bericht_id"] if soort not in ("opgelet", "rijp") else None)
                    if mid:
                        con.execute("INSERT OR REPLACE INTO signaal_berichten VALUES (?,?,?,?)",
                                    (mid, rij["id"], soort, datetime.now().isoformat(timespec="seconds")))
                        if soort in ("opgelet", "rijp"):
                            con.execute("UPDATE signalen SET bericht_id=? WHERE id=?", (mid, rij["id"]))
                    verstuurd.append((soort, rij["id"]))
                    if soort == "vervallen":
                        _sluit_knoppen(con, rij["id"])
                except Exception as e:
                    _STATUS["fout"] = f"Telegram: {e}"
            con.execute("UPDATE signalen SET gemeld=? WHERE id=?", (json.dumps(gemeld), rij["id"]))
            con.commit()
            rij = con.execute("SELECT * FROM signalen WHERE id=?", (rij["id"],)).fetchone()
    return verstuurd


def samenvatting(setups, bars, cfg, offset):
    """Eén leesbare regel voor het log: wat ziet de bot nu?"""
    levend = [s for s in setups if s.status in D.LEVEND]
    if levend:
        delen = []
        for s in levend:
            r = s.trade.upper()
            if s.status == "opgelet" and s.sweep is None:
                delen.append(f"{r}: impuls {s.impuls_richting} tot {_p(s.top)}, wacht op sweep")
            elif s.status == "opgelet":
                delen.append(f"{r}: sweep {_p(s.sweep)}, wacht op close voorbij {_p(s.pullback)}")
            elif s.status == "rijp":
                delen.append(f"{r}: klaar, wacht op entry {_p(s.entry)}")
            else:
                delen.append(f"{r}: in de trade vanaf {_p(s.entry)} (SL {_p(s.sl)}, TP {_p(s.tp)})")
        return " | ".join(delen)
    k = D.beste_kandidaat(bars, cfg)
    if k is None:
        return "te weinig candles"
    kant = "omhoog" if k.richting == "up" else "omlaag"
    kracht = f"{k.kracht:.1f}".replace(".", ",")
    if D.is_goed(k, cfg):
        return (f"impuls {kant} loopt: {k.netto / cfg['punt']:.0f} pts in {k.candles} candles, "
                f"{kracht}× ATR — wacht op de top")
    return (f"geen setup · sterkste beweging nu: {kant} {k.netto / cfg['punt']:.0f} pts in "
            f"{k.candles} candles — {D.waarom_niet(k, cfg)}")


def ronde(koppeling, cfg=None, stuur=True):
    """Wordt na elke ronde van de MT5-koppeling aangeroepen (zelfde thread)."""
    cfg = cfg or lees_config()
    _STATUS["aan"] = bool(cfg.get("aan", True))
    if not _STATUS["aan"]:
        _STATUS["melding"] = "uitgezet in journal_config.json"
        return []
    mt5 = koppeling.mt5
    offset = koppeling.offset if koppeling.offset is not None else 3
    sym = cfg["symbool"]
    try:
        mt5.symbol_select(sym, True)
    except Exception:
        pass
    r = mt5.copy_rates_from_pos(sym, getattr(mt5, "TIMEFRAME_M1", 1), 0, int(cfg["candles"]))
    if r is None or len(r) < 60:
        _STATUS.update(melding=f"geen candles van {sym} ontvangen", fout=None)
        return []
    bars = [(int(x["time"]), float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"]))
            for x in r]
    gesloten, live = bars[:-1], bars[-1]
    setups = D.scan(gesloten, cfg, live=live)
    # alleen setups van de laatste 4 uur zijn nog interessant
    grens = live[0] - 4 * 3600
    setups = [s for s in setups if s.top_tijd >= grens]
    nu_dt = _tijd(live[0], offset)
    with _LOCK:
        con = conn()
        try:
            verstuurd = verwerk(con, setups, gesloten, offset, cfg, live[0], stuur=stuur)
        finally:
            con.close()
    log_regel(nu_dt, samenvatting(setups, gesloten, cfg, offset))
    for soort, sid in verstuurd:
        log_regel(nu_dt, f"→ Telegram: {soort} (signaal #{sid})", altijd=True)
    _STATUS.update(melding="actief", fout=None, candles=len(bars),
                   levend=sum(1 for s in setups if s.status in D.LEVEND),
                   laatste_ronde=datetime.now().isoformat(timespec="seconds"),
                   laatste_candle=_hm(nu_dt))
    return verstuurd


def na_ronde(koppeling):
    """Haakje voor mt5_koppeling.Koppeling.na_ronde."""
    _doe_replay_als_gevraagd(koppeling)
    try:
        ronde(koppeling)
    except Exception as e:
        _STATUS.update(melding="fout in de signaalwachter (zie logs)", fout=str(e))
        try:
            log_regel(datetime.now(), "FOUT: " + traceback.format_exc().replace("\n", " | "), altijd=True)
        except Exception:
            pass


# ------------------------------------------------------------------ knoppen en koppelen

def callback(c, cb):
    """'s:{id}:{g|n|w|x}' uit de journal-bot (oude knoppen: 1 en 0 werken nog)."""
    jb = _bot()
    antwoord = "Opgeslagen"
    try:
        _, sid, code = (cb.get("data") or "").split(":")
        sid = int(sid)
        if code == "z":
            antwoord = "Entry is nooit geraakt: niets te beoordelen"
        else:
            oordeel = CB_CODE[code]
            zet_oordeel(sid, oordeel, bron="telegram")
            msg = cb.get("message") or {}
            jb.api(c["token"], "editMessageReplyMarkup", {
                "chat_id": msg.get("chat", {}).get("id"), "message_id": msg.get("message_id"),
                "reply_markup": knoppen(sid, oordeel)})
            antwoord = OORDELEN[oordeel][1].lstrip("✅❌⏱ ") + " ✓ · reply op dit bericht = opmerking"
    except Exception as e:
        antwoord = "Kon dit niet opslaan"
        print("[signalen] callback:", e)
    jb.api(c["token"], "answerCallbackQuery", {"callback_query_id": cb.get("id"), "text": antwoord})


def koppel_trade(tid, pad=None):
    """Een gesloten MT5-trade aan een signaal hangen als hij erbij past."""
    cfg = lees_config()
    with _LOCK:
        con = conn(pad)
        try:
            t = con.execute("SELECT id, datum, tijd_entry, richting, entry FROM trades WHERE id=?",
                            (tid,)).fetchone()
            if t is None or not t["tijd_entry"] or t["entry"] is None:
                return None
            tm = _minuten(t["tijd_entry"])
            beste = None
            for s in con.execute("SELECT * FROM signalen WHERE datum=? AND trade=? AND entry IS NOT NULL "
                                 "AND trade_id IS NULL", (t["datum"], t["richting"])):
                bm = _minuten(s["bos_tijd"] or "")
                if bm is None or tm is None or not (bm <= tm <= bm + cfg["koppel_minuten"]):
                    continue
                afstand = abs(s["entry"] - t["entry"]) / cfg["punt"]
                if afstand > cfg["koppel_marge_points"]:
                    continue
                if beste is None or afstand < beste[0]:
                    beste = (afstand, s["id"])
            if beste is None:
                return None
            sid = beste[1]
            nu = datetime.now().isoformat(timespec="seconds")
            con.execute("UPDATE signalen SET genomen=1, oordeel='genomen', oordeel_ts=?, trade_id=?, "
                        "bijgewerkt=? WHERE id=?", (nu, tid, nu, sid))
            con.execute("UPDATE trades SET signaal_id=?, signaal_gezien=1 WHERE id=?", (sid, tid))
            con.commit()
            return sid
        finally:
            con.close()


# ------------------------------------------------------------------ voor /signalen en /status

def vandaag_tekst(datum=None):
    datum = datum or datetime.now().date().isoformat()
    con = conn()
    try:
        rijen = con.execute("SELECT * FROM signalen WHERE datum=? ORDER BY impuls_tot_tijd", (datum,)).fetchall()
    finally:
        con.close()
    if not rijen:
        return "Vandaag nog geen signalen."
    regels = [f"<b>Signalen vandaag: {len(rijen)}</b>"]
    for r in rijen:
        g = OORDEEL_KORT.get(oordeel_van(r), "")
        stap = r["status"]
        if r["entry"] is not None:
            stap += f" · entry {_p(r['entry'])}"
        regels.append(f"#{r['id']} {r['impuls_tot_tijd']} {(r['trade'] or '').upper():5} {stap} {g}")
    return "\n".join(regels)


def status_tekst():
    s = status()
    regel = f"Signaalwachter: {s['melding']}"
    if s.get("laatste_candle"):
        regel += f" · laatste candle {s['laatste_candle']} · {s['levend']} setup(s) in de gaten"
    if s.get("fout"):
        regel += f"\n⚠️ {s['fout']}"
    return regel


# ------------------------------------------------------------------ replay van een hele dag
# Draait IN de thread van de MT5-koppeling (MT5 houdt niet van twee threads
# tegelijk): de aanvraag wordt klaargezet, de koppeling pakt hem bij de
# volgende ronde op, en de vrager wacht op het antwoord.

_REPLAY = {"datum": None, "antwoord": None, "klaar": threading.Event()}


def _server_ts(ams_dt, offset):
    """Amsterdamse (naive) tijd -> MT5-servertijd als epoch."""
    import mt5_koppeling as K
    from datetime import timezone
    guess = ams_dt.replace(tzinfo=timezone.utc) - timedelta(hours=2)
    utc = ams_dt.replace(tzinfo=timezone.utc) - timedelta(hours=K.amsterdam_uur(guess))
    return int(utc.timestamp()) + int(offset) * 3600


def replay(koppeling, datum, cfg=None):
    """Alle setups van één dag, zoals de wachter ze live gezien zou hebben."""
    cfg = cfg or lees_config()
    d = datetime.fromisoformat(datum)
    offset = koppeling.offset if koppeling.offset is not None else 3
    van = _server_ts(d - timedelta(hours=2), offset)
    tot = _server_ts(d + timedelta(days=1), offset)
    from datetime import timezone
    mt5 = koppeling.mt5
    try:
        mt5.symbol_select(cfg["symbool"], True)
    except Exception:
        pass
    r = mt5.copy_rates_range(cfg["symbool"], getattr(mt5, "TIMEFRAME_M1", 1),
                             datetime.fromtimestamp(van, tz=timezone.utc),
                             datetime.fromtimestamp(tot, tz=timezone.utc))
    if r is None or len(r) == 0:
        return {"datum": datum, "candles": 0, "setups": [], "melding": "geen candles voor deze dag"}
    bars = [(int(x["time"]), float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"]))
            for x in r]
    begin = _server_ts(d, offset)
    uit = []
    for s in D.scan(bars, cfg):
        if s.top_tijd < begin:
            continue
        f = lambda ts: _hm(_tijd(ts, offset)) if ts is not None else None   # noqa: E731
        uit.append({
            "trade": s.trade, "impuls": f"{f(s.impuls['van_tijd'])}–{f(s.impuls['tot_tijd'])}",
            "impuls_pts": round(abs(s.impuls["tot"] - s.impuls["van"]) / cfg["punt"]),
            "kracht": s.impuls["kracht"], "top": s.top, "sweep": s.sweep, "sweep_tijd": f(s.sweep_tijd),
            "pullback": s.pullback, "bos_tijd": f(s.bos_tijd), "entry": s.entry, "sl": s.sl, "tp": s.tp,
            "entry_tijd": f(s.entry_tijd), "status": s.status, "uitkomst_tijd": f(s.uitkomst_tijd),
            "reden": s.reden})
    return {"datum": datum, "candles": len(bars), "setups": uit}


def replay_aanvraag(datum, wacht=45):
    import mt5_koppeling as K
    kop = K.koppeling()
    if kop is None:
        return {"datum": datum, "melding": "MT5-koppeling draait niet"}
    _REPLAY["klaar"].clear()
    _REPLAY["antwoord"] = None
    _REPLAY["datum"] = datum
    kop.nu_synchroniseren()
    if not _REPLAY["klaar"].wait(wacht):
        _REPLAY["datum"] = None
        return {"datum": datum, "melding": "MT5 gaf niet op tijd antwoord (staat MT5 open?)"}
    return _REPLAY["antwoord"]


def _doe_replay_als_gevraagd(koppeling):
    datum = _REPLAY["datum"]
    if not datum:
        return
    _REPLAY["datum"] = None
    try:
        _REPLAY["antwoord"] = replay(koppeling, datum)
    except Exception as e:
        _REPLAY["antwoord"] = {"datum": datum, "melding": f"fout: {e}"}
    _REPLAY["klaar"].set()


def replay_tekst(res):
    if res.get("melding") and not res.get("setups"):
        return f"Replay {res.get('datum')}: {res['melding']}"
    s = res["setups"]
    regels = [f"<b>Replay {res['datum']}</b> · {res['candles']} candles · {len(s)} setup(s)"]
    for x in s:
        regel = f"{x['impuls'].split('–')[1]} {x['trade'].upper():5} {x['status']}"
        if x["entry"] is not None:
            regel += f" · entry {_p(x['entry'])} ({x['bos_tijd']})"
        elif x["reden"]:
            regel += f" · {x['reden']}"
        regels.append(regel)
    return "\n".join(regels)


# ------------------------------------------------------------------ oordeel, opmerking, dataset
# (1 okt 2026) Elk 'klaar'-signaal krijgt jouw oordeel, wat het zou zijn geworden en
# je opmerkingen. Dat is de gelabelde dataset voor betere signalen / een AI later.

def zet_oordeel(sid, oordeel, bron="journal"):
    if oordeel not in OORDELEN:
        raise ValueError("onbekend oordeel")
    nu = datetime.now().isoformat(timespec="seconds")
    with _LOCK:
        con = conn()
        try:
            if con.execute("SELECT id FROM signalen WHERE id=?", (sid,)).fetchone() is None:
                raise LookupError("signaal bestaat niet")
            con.execute("UPDATE signalen SET oordeel=?, oordeel_ts=?, genomen=?, bijgewerkt=? WHERE id=?",
                        (oordeel, nu, 1 if oordeel == "genomen" else 0, nu, sid))
            con.commit()
        finally:
            con.close()
    return oordeel


def _opmerking_in(con, sid, tekst, bron):
    con.execute("INSERT INTO signaal_opmerkingen (signaal_id, ts, tekst, bron) VALUES (?,?,?,?)",
                (sid, datetime.now().isoformat(timespec="seconds"), tekst, bron))
    con.commit()


def voeg_opmerking_toe(message_id, tekst, bron="telegram"):
    """Reply op een signaalbericht in Telegram -> opmerking bij dat signaal.
    Geeft het signaal-id terug, of None als dit geen signaalbericht was."""
    tekst = (tekst or "").strip()
    if not tekst:
        return None
    with _LOCK:
        con = conn()
        try:
            r = con.execute("SELECT signaal_id FROM signaal_berichten WHERE message_id=?",
                            (message_id,)).fetchone()
            if r is None:
                return None
            _opmerking_in(con, r["signaal_id"], tekst, bron)
            return r["signaal_id"]
        finally:
            con.close()


def voeg_opmerking_toe_aan_signaal(sid, tekst, bron="journal"):
    tekst = (tekst or "").strip()
    if not tekst:
        raise ValueError("lege opmerking")
    with _LOCK:
        con = conn()
        try:
            if con.execute("SELECT id FROM signalen WHERE id=?", (sid,)).fetchone() is None:
                raise LookupError("signaal bestaat niet")
            _opmerking_in(con, sid, tekst, bron)
            return [dict(o) for o in con.execute(
                "SELECT ts, tekst, bron FROM signaal_opmerkingen WHERE signaal_id=? ORDER BY id", (sid,))]
        finally:
            con.close()


def uitkomst_van(r):
    """Wat zou er met dit signaal gebeurd zijn? (hypothetisch, uit de candles)"""
    st = r["status"]
    if st in ("tp", "sl", "onbeslist"):
        return st
    if st == "entry":
        return "bezig"
    if st == "rijp":
        return "wacht"
    if st == "vervallen":
        return "nooit_gevuld" if r["entry"] is not None and r["entry_tijd"] is None else "vervallen"
    return st


DATASET_KOLOMMEN = [
    "id", "datum", "tijd_klaar", "trade", "in_venster", "impuls_pts", "kracht", "overlap", "efficientie",
    "entry", "sl", "tp", "risico_points", "uitkomst", "reden", "hyp_r", "oordeel", "oordeel_ts",
    "genomen_trade_id", "genomen_r", "opmerkingen",
]


def dataset(van=None, tot=None, alles=False):
    """Alle signalen (standaard: de 'klaar'-signalen) als lijst dicts, nieuwste eerst."""
    cfg = lees_config()
    punt = cfg.get("punt", 0.10)
    con = conn()
    try:
        w, p = [], []
        if not alles:
            w.append("entry IS NOT NULL")
        if van:
            w.append("datum>=?")
            p.append(van)
        if tot:
            w.append("datum<=?")
            p.append(tot)
        rijen = con.execute("SELECT * FROM signalen" + (" WHERE " + " AND ".join(w) if w else "") +
                            " ORDER BY datum DESC, COALESCE(bos_tijd, impuls_tot_tijd) DESC, id DESC", p).fetchall()
        opm = {}
        for o in con.execute("SELECT signaal_id, ts, tekst, bron FROM signaal_opmerkingen ORDER BY id"):
            opm.setdefault(o["signaal_id"], []).append({"ts": o["ts"], "tekst": o["tekst"], "bron": o["bron"]})
        trade_r = {}
        tids = [r["trade_id"] for r in rijen if r["trade_id"]]
        if tids:
            try:
                for t in con.execute("SELECT id, resultaat_r FROM trades WHERE id IN (%s)" % ",".join("?" * len(tids)), tids):
                    trade_r[t["id"]] = t["resultaat_r"]
            except sqlite3.OperationalError:
                pass
        uit = []
        for r in rijen:
            u = uitkomst_van(r)
            rr = None
            if r["entry"] is not None and r["sl"] is not None and r["tp"] is not None and r["entry"] != r["sl"]:
                rr = abs(r["tp"] - r["entry"]) / abs(r["entry"] - r["sl"])
            hyp = round(rr, 2) if (u == "tp" and rr) else (-1.0 if u == "sl" else None)
            pts = None
            if r["impuls_van"] is not None and r["impuls_tot"] is not None:
                pts = round(abs(r["impuls_tot"] - r["impuls_van"]) / punt)
            uit.append({
                "id": r["id"], "datum": r["datum"], "tijd_klaar": r["bos_tijd"] or r["impuls_tot_tijd"],
                "trade": r["trade"], "in_venster": r["in_venster"], "impuls_pts": pts,
                "kracht": r["kracht"], "overlap": r["overlap"], "efficientie": r["efficientie"],
                "entry": r["entry"], "sl": r["sl"], "tp": r["tp"], "risico_points": r["risico_points"],
                "uitkomst": u, "reden": r["reden"], "hyp_r": hyp,
                "oordeel": oordeel_van(r), "oordeel_ts": r["oordeel_ts"],
                "genomen_trade_id": r["trade_id"], "genomen_r": trade_r.get(r["trade_id"]),
                "opmerkingen": opm.get(r["id"], []),
                "chart_url": f"/api/signalen/{r['id']}/chart.svg" if r["entry"] is not None else None,
            })
        return uit
    finally:
        con.close()


def statistiek(rijen):
    """Per oordeel: hoeveel, en wat er hypothetisch van geworden zou zijn. Laat zien of
    je oordeel iets toevoegt (win% van 'gemist: wel' tegenover 'gemist: niet')."""
    groepen = {}
    for r in rijen:
        k = r["oordeel"] or "geen"
        g = groepen.setdefault(k, {"oordeel": k, "n": 0, "tp": 0, "sl": 0, "onbeslist": 0,
                                   "nooit_gevuld": 0, "open": 0, "hyp_r": 0.0})
        g["n"] += 1
        u = r["uitkomst"]
        if u in ("tp", "sl", "onbeslist", "nooit_gevuld"):
            g[u] += 1
        else:
            g["open"] += 1
        if r["hyp_r"] is not None:
            g["hyp_r"] = round(g["hyp_r"] + r["hyp_r"], 2)
    for g in groepen.values():
        beslist = g["tp"] + g["sl"]
        g["winrate"] = round(100.0 * g["tp"] / beslist) if beslist else None
    volgorde = ["genomen", "niet", "gemist_wel", "gemist_niet", "geen"]
    return [groepen[k] for k in volgorde if k in groepen]


def dataset_csv(van=None, tot=None, alles=False):
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(DATASET_KOLOMMEN)
    for r in dataset(van, tot, alles):
        rij = dict(r)
        rij["opmerkingen"] = " | ".join(f"{o['ts'][:16].replace('T', ' ')}: {o['tekst']}" for o in r["opmerkingen"])
        w.writerow(["" if rij.get(k) is None else rij.get(k) for k in DATASET_KOLOMMEN])
    return "﻿" + buf.getvalue()


def chart_svg(sid, force=False):
    """SVG van het signaal (tekent hem zo nodig opnieuw), of None."""
    import signaal_chart
    cfg = lees_config()
    con = conn()
    try:
        r = con.execute("SELECT * FROM signalen WHERE id=?", (sid,)).fetchone()
        if r is None:
            return None
        o = oordeel_van(r)
        label = OORDELEN[o][2] if o in OORDELEN else ""
        rel = signaal_chart.herteken(con, sid, entry_max_candles=cfg["entry_max_candles"],
                                     oordeel_label=label, force=force)
    finally:
        con.close()
    if not rel:
        return None
    with open(os.path.join(HIER, rel), encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------ webroutes
try:
    import re
    from fastapi import APIRouter, HTTPException
    from fastapi.responses import HTMLResponse, Response
    from pydantic import BaseModel

    router = APIRouter()

    class _OordeelIn(BaseModel):
        oordeel: str

    class _OpmerkingIn(BaseModel):
        tekst: str

    @router.get("/api/signalen")
    def api_signalen(datum: str = None):
        datum = datum or datetime.now().date().isoformat()
        con = conn()
        try:
            rijen = [dict(r) for r in con.execute(
                "SELECT * FROM signalen WHERE datum=? ORDER BY impuls_tot_tijd", (datum,))]
        finally:
            con.close()
        for r in rijen:
            r.pop("candles", None)
        return {"datum": datum, "status": status(), "signalen": rijen}

    @router.get("/api/signalen/replay")
    def api_replay(datum: str):
        return replay_aanvraag(datum)

    @router.get("/api/signalen/dataset")
    def api_dataset(van: str = None, tot: str = None, oordeel: str = None,
                    uitkomst: str = None, alles: int = 0):
        rijen = dataset(van, tot, bool(alles))
        stat = statistiek(rijen)
        if oordeel:
            rijen = [r for r in rijen if (r["oordeel"] or "geen") == oordeel]
        if uitkomst:
            rijen = [r for r in rijen if r["uitkomst"] == uitkomst]
        return {"signalen": rijen, "statistiek": stat,
                "oordelen": {k: {"knop": v[1], "lang": v[2]} for k, v in OORDELEN.items()}}

    @router.post("/api/signalen/{sid}/oordeel")
    def api_oordeel(sid: int, body: _OordeelIn):
        try:
            zet_oordeel(sid, body.oordeel)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except LookupError as e:
            raise HTTPException(404, str(e))
        return {"ok": True, "oordeel": body.oordeel}

    @router.post("/api/signalen/{sid}/opmerking")
    def api_opmerking(sid: int, body: _OpmerkingIn):
        try:
            return {"ok": True, "opmerkingen": voeg_opmerking_toe_aan_signaal(sid, body.tekst)}
        except ValueError as e:
            raise HTTPException(400, str(e))
        except LookupError as e:
            raise HTTPException(404, str(e))

    @router.get("/api/signalen/{sid}/chart.svg")
    def api_chart(sid: int, force: int = 0):
        svg = chart_svg(sid, force=bool(force))
        if svg is None:
            raise HTTPException(404, "Geen chart: het signaal was nog niet klaar of er zijn geen candles.")
        return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "no-cache"})

    @router.get("/export/signalen.csv")
    def export_signalen(van: str = None, tot: str = None, alles: int = 0):
        naam = f"cbr-signalen-{datetime.now():%Y%m%d}.csv"
        return Response(dataset_csv(van, tot, bool(alles)), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{naam}"'})

    @router.get("/signalen")
    def signalen_pagina():
        sd = os.path.join(HIER, "static")
        with open(os.path.join(sd, "signalen.html"), encoding="utf-8") as f:
            html = f.read()
        try:
            v = str(int(max(os.path.getmtime(os.path.join(sd, n))
                            for n in ("signalen.html", "signalen.js", "signalen.css"))))
        except OSError:
            v = "1"
        html = re.sub(r'(/static/[\w./-]+\.(?:css|js))"', r'\1?v=' + v + '"', html)
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
except Exception:          # pragma: no cover  (tests zonder fastapi)
    router = None
