# -*- coding: utf-8 -*-
"""
v3_labels.py -- labels van Marijn voor de structuurdetector v3 (plan v3, fase 2, 7 okt 2026).

Twee dingen, allebei via de journal-bot:
  * Elk v3-signaal binnen je venster komt met een grafiekje en vijf knoppen: A / B / C / nee / niet gezien.
    Eén tik. Kandidaten van dezelfde sweep delen één bericht en één label (rustig: nooit twee berichten per sweep).
  * Bij elke eigen trade: welk TP-type (1:1 / 50% / anders) en waar begon de expansie? De bot doet een voorstel
    (uit je eerste SL/TP in MT5, mt5_positie_events); jij tikt 'klopt' of antwoordt met de juiste prijs.

Opslag in cbr_journal.db: tabel v3_labels (één rij per kandidaat) en de kolommen tp_type, expansie_begin, ... in trades.
Het station leest dit alleen. Alleen lezen uit MT5, nooit handelen. Instellingen: journal_config.json -> "v3_labels".
"""

import io
import json
import os
import sqlite3
import threading
import traceback
import uuid
from datetime import datetime, timedelta

import structuur_detector as S

HIER = os.path.dirname(os.path.abspath(__file__))
DB_PAD = os.path.join(HIER, "cbr_journal.db")
MD_PAD = os.path.join(HIER, "marktdata.db")
CONFIG_PAD = os.path.join(HIER, "journal_config.json")
AMS = S.AMS                                     # met terugval als er geen tzdata is

RUNTIME = {
    "aan": True,
    "candles": 400,              # zoveel minuten terug kijken (expansie tot 90 + BOS 15 + ATR)
    "vers_seconden": 180,        # bij een (her)start geen oude kandidaten pushen
    "max_leeftijd_min": 10,      # een order die al langer klaarligt, niet meer melden
    "stil": False,               # True = berichten altijd zonder geluid
    "stil_tussen": ["22:00", "08:00"],   # 's nachts (Asia-blok) zonder geluid
    "venster": None,             # eigen lijst blokken voor v3, bv. [["10:00","15:00"]]; None = je journal-venster
    "chart": True,               # False = alleen tekst
    "match_sl_points": 3,        # trade hoort bij een v3-kandidaat: SL binnen 3 points ...
    "match_voor_min": 12,        # ... en je entry van 12 min vóór de order ...
    "match_na_min": 33,          # ... tot 33 min erna (30 candles orderduur + 3)
}

LABELS = {"a": ("A", "A"), "b": ("B", "B"), "c": ("C", "C"), "n": ("nee", "❌ nee"), "z": ("niet_gezien", "👀 niet gezien")}
LABEL_CODE = {v[0]: k for k, v in LABELS.items()}
TP_TYPES = {"11": "1:1", "50": "50%", "an": "anders"}

_STATUS = {"melding": "nog niet gestart", "laatste_ronde": None, "fout": None, "verstuurd": 0}
_EERSTE_LIVE = None
_LOCK = threading.Lock()


# ------------------------------------------------------------------ config en database

def lees_config():
    try:
        with open(CONFIG_PAD, encoding="utf-8") as f:
            root = json.load(f)
    except (FileNotFoundError, ValueError):
        root = {}
    import signalen
    basis = signalen.lees_config()               # venster, handelsdagen, symbool
    eigen = {k: v for k, v in (root.get("v3_labels") or {}).items() if not k.startswith("_")}
    uit = {**basis, **RUNTIME, **eigen}
    if not eigen.get("venster"):
        uit["venster"] = basis.get("venster")    # standaard: hetzelfde venster als je journal
    return uit


SCHEMA = """
CREATE TABLE IF NOT EXISTS v3_labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sleutel TEXT UNIQUE,            -- kandidaat-sleutel van structuur_detector: trade-sweep_ts-bos_ts
    groep TEXT,                     -- trade-sweep_ts: kandidaten van dezelfde sweep delen bericht en label
    datum TEXT, tijd TEXT,          -- Amsterdam; tijd = de minuut waarop de order klaarligt
    trade TEXT, geveegd REAL, structuur REAL, sweep REAL, bos_laag REAL, entry REAL, sl REAL,
    tp_11 REAL, tp_50 REAL, begin REAL, sweep_tijd TEXT, bos_tijd TEXT, begin_tijd TEXT, order_ts INTEGER,
    kenmerken TEXT,
    label TEXT, label_ts TEXT, bron TEXT,
    bericht_id INTEGER, aangemaakt TEXT
);
CREATE INDEX IF NOT EXISTS idx_v3_groep ON v3_labels(groep);
CREATE INDEX IF NOT EXISTS idx_v3_datum ON v3_labels(datum);
CREATE TABLE IF NOT EXISTS v3_berichten (
    message_id INTEGER PRIMARY KEY, soort TEXT, ref TEXT, ts TEXT
);
"""

# bij elke eigen trade (worden aan 'trades' toegevoegd als ze er nog niet zijn)
TRADE_KOLOMMEN = {"tp_type": "TEXT", "tp_type_bron": "TEXT", "expansie_begin": "REAL", "expansie_bron": "TEXT",
                  "sl_start": "REAL", "tp_start": "REAL", "v3_sleutel": "TEXT"}
_GEMIGREERD = set()


def conn(pad=None):
    pad = pad or DB_PAD
    con = sqlite3.connect(pad, timeout=20)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    if pad not in _GEMIGREERD:
        try:
            aanwezig = {r[1] for r in con.execute("PRAGMA table_info(trades)")}
            if aanwezig:
                for kol, typ in TRADE_KOLOMMEN.items():
                    if kol not in aanwezig:
                        con.execute(f"ALTER TABLE trades ADD COLUMN {kol} {typ}")
                con.commit()
        except sqlite3.OperationalError as e:
            print("[v3] kolommen trades:", e)
        _GEMIGREERD.add(pad)
    return con


def status():
    return dict(_STATUS)


# ------------------------------------------------------------------ opmaak

def _p(x):
    return "–" if x is None else f"{x:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _ams(ts):
    return datetime.fromtimestamp(int(ts), AMS).replace(tzinfo=None)


def _hm(ts):
    return None if ts is None else _ams(ts).strftime("%H:%M")


def tekst_signaal(r, aantal=1):
    pts = (r["sl"] - r["entry"]) / S.STANDAARD["punt"]
    regels = [f"🔷 <b>v3 {(r['trade'] or '').upper()}</b> · order klaar {r['tijd']}",
              f"sweep {_p(r['sweep'])} ({r['sweep_tijd']}) · BOS {r['bos_tijd']}",
              f"entry <b>{_p(r['entry'])}</b> · SL {_p(r['sl'])} · risico {abs(pts):.0f} pts",
              f"TP 1:1 {_p(r['tp_11'])} · 50% {_p(r['tp_50'])} (expansie vanaf {_p(r['begin'])}, {r['begin_tijd']})"]
    if aantal > 1:
        regels.append(f"<i>{aantal} orders bij deze sweep; je label geldt voor allemaal.</i>")
    regels.append("Zou jij deze nemen? Eén tik. <i>Niet gezien = je keek op dat moment niet.</i>")
    return "\n".join(regels)


def knoppen_signaal(groep_id, label=None):
    def k(code):
        waarde, tekst = LABELS[code]
        return {"text": ("● " if label == waarde else "") + tekst, "callback_data": f"v:{groep_id}:{code}"}
    return {"inline_keyboard": [[k("a"), k("b"), k("c")], [k("n"), k("z")]]}


# ------------------------------------------------------------------ grafiekje (PNG, Pillow)

def chart_png(bars, lijnen, markeringen=(), titel=""):
    """bars = [(ts, o, h, l, c), ...]; lijnen = [(prijs, kleur, tekst, gestippeld)]; markeringen = [(ts, kleur, tekst)].
    Geeft PNG-bytes of None (geen Pillow / geen candles)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    if not bars:
        return None
    B, Hh, links, rechts, boven, onder = 960, 540, 10, 130, 30, 40
    img = Image.new("RGB", (B, Hh), "#0f1419")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=14)
    except TypeError:
        font = ImageFont.load_default()
    prijzen = [b[2] for b in bars] + [b[3] for b in bars] + [p for p, *_ in lijnen if p is not None]
    hi, lo = max(prijzen), min(prijzen)
    marge = (hi - lo) * 0.05 or 1.0
    hi, lo = hi + marge, lo - marge
    y = lambda p: boven + (hi - p) / (hi - lo) * (Hh - boven - onder)            # noqa: E731
    w = (B - links - rechts) / len(bars)
    x = lambda i: links + (i + 0.5) * w                                           # noqa: E731
    for p, kleur, tekst, stip in lijnen:
        if p is None:
            continue
        yy = y(p)
        if stip:
            for xx in range(links, B - rechts, 12):
                d.line([(xx, yy), (xx + 6, yy)], fill=kleur, width=1)
        else:
            d.line([(links, yy), (B - rechts, yy)], fill=kleur, width=1)
        d.text((B - rechts + 4, yy - 8), f"{tekst} {p:.2f}", fill=kleur, font=font)
    ts_index = {int(b[0]): i for i, b in enumerate(bars)}
    for i, (_, o, h, l, c) in enumerate(bars):
        kleur = "#3ecf8e" if c >= o else "#ef5b5b"
        d.line([(x(i), y(h)), (x(i), y(l))], fill=kleur, width=1)
        y1, y2 = sorted((y(o), y(c)))
        d.rectangle([x(i) - max(1, w * 0.35), y1, x(i) + max(1, w * 0.35), max(y2, y1 + 1)], fill=kleur)
    for n, (ts, kleur, tekst) in enumerate(markeringen):
        i = ts_index.get(int(ts)) if ts is not None else None
        if i is None:
            continue
        d.line([(x(i), boven), (x(i), Hh - onder)], fill=kleur, width=1)
        d.text((x(i) + 3, Hh - onder + 3 + 18 * (n % 2)), tekst, fill=kleur, font=font)   # om en om: geen overlap
    stap = max(1, len(bars) // 8)
    for i in range(0, len(bars), stap):
        d.text((x(i) - 16, 8), _ams(bars[i][0]).strftime("%H:%M"), fill="#8a8f98", font=font)
    if titel:
        d.text((B - rechts + 4, 8), titel, fill="#e6e6e6", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def chart_kandidaat(bars, k):
    """Van 10 candles vóór het begin van de expansie tot nu (minstens 60 candles)."""
    T = [int(b[0]) for b in bars]
    i0 = T.index(int(k["begin_tijd"])) if int(k["begin_tijd"]) in T else 0
    i0 = max(0, min(i0 - 10, len(bars) - 60))                 # minstens een uur in beeld
    stuk = [tuple(b[:5]) for b in bars[i0:]]
    lijnen = [(k["geveegd"], "#8a8f98", "high", True), (k["structuur"], "#5aa9e6", "structuur", True),
              (k["sl"], "#ef5b5b", "SL", False), (k["entry"], "#f0f0f0", "entry", False),
              (k["tp_11"], "#3ecf8e", "TP 1:1", False), (k.get("tp_50"), "#3ecf8e", "TP 50%", True),
              (k["begin"], "#c9a227", "begin", True)]
    mark = [(k["begin_tijd"], "#c9a227", "begin"), (k["sweep_tijd"], "#ff9f43", "sweep"),
            (k["bos_tijd"], "#5aa9e6", "BOS")]
    return chart_png(stuk, lijnen, mark, titel=f"v3 {k['trade'].upper()}")


# ------------------------------------------------------------------ Telegram

def _bot():
    import journal_bot
    return journal_bot


def _stuur(tekst, knoppen, png=None, stil=False, antwoord_op=None):
    """sendPhoto (met grafiekje) of sendMessage. Geeft message_id of None."""
    jb = _bot()
    c = jb.cfg()
    if not (c["aan"] and c["token"] and c["chat_id"]):
        return None
    if png:
        try:
            velden = {"chat_id": str(c["chat_id"]), "caption": tekst, "parse_mode": "HTML",
                      "disable_notification": "true" if stil else "false",
                      "reply_markup": json.dumps(knoppen)}
            if antwoord_op:
                velden["reply_to_message_id"] = str(antwoord_op)
                velden["allow_sending_without_reply"] = "true"
            r = _multipart(c["token"], "sendPhoto", velden, ("photo", "v3.png", png))
            mid = (r.get("result") or {}).get("message_id")
            if mid:
                return mid
        except Exception as e:
            print("[v3] foto sturen mislukt, dan tekst:", e)
    data = {"chat_id": c["chat_id"], "text": tekst, "parse_mode": "HTML", "disable_notification": bool(stil),
            "reply_markup": knoppen}
    if antwoord_op:
        data.update(reply_to_message_id=antwoord_op, allow_sending_without_reply=True)
    r = jb.api(c["token"], "sendMessage", data)
    return (r.get("result") or {}).get("message_id")


def _multipart(token, methode, velden, bestand, timeout=60):
    import urllib.request
    jb = _bot()
    grens = uuid.uuid4().hex
    delen = []
    for k, v in velden.items():
        delen.append(f'--{grens}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
    naam, bestandsnaam, inhoud = bestand
    delen.append(f'--{grens}\r\nContent-Disposition: form-data; name="{naam}"; filename="{bestandsnaam}"\r\n'
                 f'Content-Type: image/png\r\n\r\n'.encode("utf-8") + inhoud + b"\r\n")
    delen.append(f"--{grens}--\r\n".encode("utf-8"))
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{methode}", data=b"".join(delen),
                                 headers={"Content-Type": f"multipart/form-data; boundary={grens}"})
    with urllib.request.urlopen(req, timeout=timeout, context=jb._ssl_ctx()) as r:
        return json.loads(r.read().decode("utf-8"))


def _onthoud_bericht(con, mid, soort, ref):
    con.execute("INSERT OR REPLACE INTO v3_berichten VALUES (?,?,?,?)",
                (mid, soort, str(ref), datetime.now().isoformat(timespec="seconds")))


# ------------------------------------------------------------------ signalen: elke ronde van de MT5-koppeling

def _bars_live(koppeling, cfg):
    mt5 = koppeling.mt5
    offset = koppeling.offset if koppeling.offset is not None else 3
    sym = cfg["symbool"]
    try:
        mt5.symbol_select(sym, True)
    except Exception:
        pass
    r = mt5.copy_rates_from_pos(sym, getattr(mt5, "TIMEFRAME_M1", 1), 0, int(cfg["candles"]))
    if r is None or len(r) < 120:
        return None
    try:
        punt = float(mt5.symbol_info(sym).point)
    except Exception:
        punt = 0.01
    namen = getattr(getattr(r, "dtype", None), "names", None) or ()
    # servertijd -> echte epoch (UTC); spread in prijs. De laatste candle loopt nog: de detector kijkt er niet in vooruit.
    return [(int(x["time"]) - int(offset) * 3600, float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"]),
             (float(x["spread"]) * punt) if "spread" in namen else 0.0) for x in r]


def in_venster(ts, cfg):
    import signalen
    return signalen.venster_label(_ams(ts), cfg) == ""


def _stil(ts, cfg):
    if cfg.get("stil"):
        return True
    van, tot = (cfg.get("stil_tussen") or [None, None])[:2]
    if not van or not tot:
        return False
    hm = _ams(ts).strftime("%H:%M")
    return (van <= hm or hm < tot) if van > tot else (van <= hm < tot)


def _rij_velden(k):
    return dict(sleutel=k["sleutel"], groep=f"{k['trade']}-{k['sweep_tijd']}", datum=k["datum"], tijd=_hm(k["order_tijd"]),
                trade=k["trade"], geveegd=k["geveegd"], structuur=k["structuur"], sweep=k["sweep"], bos_laag=k["bos_laag"],
                entry=k["entry"], sl=k["sl"], tp_11=k["tp_11"], tp_50=k["tp_50"], begin=k["begin"],
                sweep_tijd=_hm(k["sweep_tijd"]), bos_tijd=_hm(k["bos_tijd"]), begin_tijd=_hm(k["begin_tijd"]),
                order_ts=int(k["order_tijd"]), kenmerken=json.dumps(k["kenmerken"]),
                aangemaakt=datetime.now().isoformat(timespec="seconds"))


def verwerk(con, kands, bars, nu_ts, cfg, stuur=True):
    """Nieuwe kandidaten binnen het venster opslaan en (vers) melden: één bericht per sweep. Geeft [groep] terug."""
    global _EERSTE_LIVE
    if _EERSTE_LIVE is None:
        _EERSTE_LIVE = nu_ts
    verstuurd = []
    for k in kands:
        if not in_venster(k["order_tijd"], cfg):
            continue
        if con.execute("SELECT 1 FROM v3_labels WHERE sleutel=?", (k["sleutel"],)).fetchone():
            continue
        v = _rij_velden(k)
        broer = con.execute("SELECT bericht_id, label, label_ts, bron FROM v3_labels WHERE groep=? "
                            "ORDER BY id LIMIT 1", (v["groep"],)).fetchone()
        if broer is not None:                     # zelfde sweep: geen nieuw bericht, wel hetzelfde label
            v.update(bericht_id=broer["bericht_id"], label=broer["label"], label_ts=broer["label_ts"], bron=broer["bron"])
        con.execute(f"INSERT INTO v3_labels ({', '.join(v)}) VALUES ({', '.join('?' * len(v))})", list(v.values()))
        con.commit()
        if broer is not None:
            continue
        vers = (k["order_tijd"] >= _EERSTE_LIVE - cfg["vers_seconden"]
                and k["order_tijd"] >= nu_ts - 60 * cfg["max_leeftijd_min"])
        if not (stuur and vers):
            continue
        rij = con.execute("SELECT * FROM v3_labels WHERE sleutel=?", (k["sleutel"],)).fetchone()
        png = None
        if cfg.get("chart", True):
            try:
                png = chart_kandidaat(bars, k)
            except Exception as e:
                print("[v3] grafiekje:", e)
        try:
            mid = _stuur(tekst_signaal(rij), knoppen_signaal(rij["id"]), png=png, stil=_stil(k["order_tijd"], cfg))
        except Exception as e:
            _STATUS["fout"] = f"Telegram: {e}"
            mid = None
        if mid:
            con.execute("UPDATE v3_labels SET bericht_id=? WHERE groep=?", (mid, v["groep"]))
            _onthoud_bericht(con, mid, "signaal", rij["id"])
            con.commit()
            verstuurd.append(v["groep"])
            _STATUS["verstuurd"] += 1
    return verstuurd


def ronde(koppeling, cfg=None, stuur=True):
    cfg = cfg or lees_config()
    if not cfg.get("aan", True):
        _STATUS["melding"] = "uitgezet in journal_config.json (v3_labels.aan)"
        return []
    bars = _bars_live(koppeling, cfg)
    if bars is None:
        _STATUS.update(melding="geen candles ontvangen", fout=None)
        return []
    nu_ts = bars[-1][0]
    kands = [k for k in S.kandidaten(bars) if k["order_tijd"] >= nu_ts - 4 * 3600]
    with _LOCK:
        con = conn()
        try:
            uit = verwerk(con, kands, bars, nu_ts, cfg, stuur=stuur)
        finally:
            con.close()
    _STATUS.update(melding="actief", fout=None, laatste_ronde=datetime.now().isoformat(timespec="seconds"))
    return uit


def na_ronde(koppeling):
    """Haakje voor mt5_koppeling.Koppeling.na_ronde (zelfde thread als MT5)."""
    try:
        ronde(koppeling)
    except Exception as e:
        _STATUS.update(melding="fout (zie console)", fout=str(e))
        print("[v3] ronde:", traceback.format_exc())


def zet_label(groep_id, label, bron="telegram", pad=None):
    """Label op alle kandidaten van dezelfde sweep als kandidaat groep_id."""
    if label not in LABEL_CODE:
        raise ValueError(f"onbekend label {label}")
    with _LOCK:
        con = conn(pad)
        try:
            r = con.execute("SELECT groep FROM v3_labels WHERE id=?", (int(groep_id),)).fetchone()
            if r is None:
                raise ValueError(f"kandidaat {groep_id} bestaat niet")
            con.execute("UPDATE v3_labels SET label=?, label_ts=?, bron=? WHERE groep=?",
                        (label, datetime.now().isoformat(timespec="seconds"), bron, r["groep"]))
            con.commit()
        finally:
            con.close()


# ------------------------------------------------------------------ eigen trades: TP-type en begin van de expansie

def start_niveaus(con, t):
    """Eerste SL en TP van de positie uit mt5_positie_events (soort open/sl_tp); anders wat in de trade staat."""
    sl = tp = None
    if t["positie_id"]:
        try:
            for e in con.execute("SELECT sl, tp FROM mt5_positie_events WHERE positie_id=? AND soort IN ('open','sl_tp') "
                                 "ORDER BY id", (t["positie_id"],)):
                if sl is None and e["sl"]:
                    sl = e["sl"]
                if tp is None and e["tp"]:
                    tp = e["tp"]
                if sl is not None and tp is not None:
                    break
        except sqlite3.OperationalError:
            pass
    return sl if sl is not None else t["sl_prijs"], tp if tp is not None else t["tp_prijs"]


def _candles_md(van_ts, tot_ts, md_pad=None, symbool="XAUUSD+"):
    pad = md_pad or MD_PAD
    if not os.path.exists(pad):
        return []
    md = sqlite3.connect(f"file:{pad}?mode=ro", uri=True, timeout=10)
    try:
        return [(int(r[0]), r[1], r[2], r[3], r[4], ((r[5] or 0) * 0.01))
                for r in md.execute("SELECT ts_utc, o, h, l, c, spread FROM candles_m1 WHERE symbool=? AND ts_utc>=? "
                                    "AND ts_utc<=? ORDER BY ts_utc", (symbool, int(van_ts), int(tot_ts)))]
    finally:
        md.close()


def _entry_ts(t):
    dt = datetime.strptime(f"{t['datum']} {t['tijd_entry']}", "%Y-%m-%d %H:%M").replace(tzinfo=AMS)
    return int(dt.timestamp())


def voorstel(t, sl0, tp0, bars, cfg=None):
    """Wat de bot denkt: tp_type, expansie_begin, bijpassende v3-kandidaat (of None)."""
    cfg = {**RUNTIME, **(cfg or {})}
    punt = S.STANDAARD["punt"]
    entry = t["entry_prijs"] if t["entry_prijs"] is not None else t["entry"]
    short = (t["richting"] or "").lower() == "short"
    tp_type = None
    if entry is not None and sl0 and tp0 and abs(entry - sl0) > 0:
        rr = abs(tp0 - entry) / abs(entry - sl0)
        tp_type = "1:1" if 0.85 <= rr <= 1.15 else "50%"
    kand = None
    if bars and sl0 and t["tijd_entry"]:
        ets = _entry_ts(t)
        beste = None
        for k in S.kandidaten(bars):
            if k["trade"] != ("short" if short else "long"):
                continue
            if not (k["order_tijd"] - 60 * cfg["match_voor_min"] <= ets <= k["order_tijd"] + 60 * cfg["match_na_min"]):
                continue
            afst = abs(k["sl"] - sl0) / punt
            if afst <= cfg["match_sl_points"] and (beste is None or afst < beste[0]):
                beste = (afst, k)
        kand = beste[1] if beste else None
    begin = None
    if tp_type == "50%" and sl0 and tp0:
        sweep = sl0 - S.STANDAARD["sl_marge_points"] * punt if short else sl0 + S.STANDAARD["sl_marge_points"] * punt
        begin = round(2 * tp0 - sweep, 2)         # TP = midden van begin en sweep
    elif kand is not None:
        begin = round(kand["begin"], 2)
    return tp_type, begin, kand


def tekst_trade(t):
    sl0, tp0 = t["sl_start"], t["tp_start"]
    entry = t["entry_prijs"] if t["entry_prijs"] is not None else t["entry"]
    def bron(b):
        return " ✔" if b == "marijn" else " <i>(voorstel)</i>" if b == "voorstel" else ""
    regels = [f"📐 <b>Trade #{t['id']}</b> · {(t['richting'] or '').upper()} {t['tijd_entry'] or ''} · entry {_p(entry)}",
              f"start-SL {_p(sl0)} · start-TP {_p(tp0)} <i>(eerste niveaus in MT5)</i>",
              f"TP-type: <b>{t['tp_type'] or '?'}</b>{bron(t['tp_type_bron'])}",
              f"Expansie begon op: <b>{_p(t['expansie_begin'])}</b>{bron(t['expansie_bron'])}"]
    if t["v3_sleutel"]:
        regels.append("<i>v3 vond deze setup ook.</i>")
    regels.append("Tik het TP-type en ✅ als het begin klopt. Klopt het begin niet? "
                  "Antwoord op dit bericht met de prijs, bv. <code>4150.2</code>.")
    return "\n".join(regels)


def knoppen_trade(t):
    def k(code):
        waarde = TP_TYPES[code]
        return {"text": ("● " if t["tp_type"] == waarde else "") + waarde, "callback_data": f"t:{t['id']}:{code}"}
    ok = "✅ klopt" + (" ✔" if t["expansie_bron"] == "marijn" and t["tp_type_bron"] == "marijn" else "")
    return {"inline_keyboard": [[k("11"), k("50"), k("an")], [{"text": ok, "callback_data": f"t:{t['id']}:ok"}]]}


def bereid_trade(tid, pad=None, md_pad=None):
    """Zet start-SL/TP en het voorstel in de trade (raakt niets dat jij al bevestigde). Geeft (trade, bars, kand)."""
    with _LOCK:
        con = conn(pad)
        try:
            t = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
            if t is None or not t["tijd_entry"] or not t["datum"]:
                return None, [], None
            sl0, tp0 = start_niveaus(con, t)
            ets = _entry_ts(t)
            bars = _candles_md(ets - 200 * 60, ets + 40 * 60, md_pad)
            tp_type, begin, kand = voorstel(t, sl0, tp0, bars)
            zet = {"sl_start": sl0, "tp_start": tp0, "v3_sleutel": kand["sleutel"] if kand else None}
            if t["tp_type_bron"] != "marijn":
                zet.update(tp_type=tp_type, tp_type_bron="voorstel" if tp_type else None)
            if t["expansie_bron"] != "marijn":
                zet.update(expansie_begin=begin, expansie_bron="voorstel" if begin is not None else None)
            con.execute(f"UPDATE trades SET {', '.join(k + '=?' for k in zet)} WHERE id=?", list(zet.values()) + [tid])
            con.commit()
            return con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone(), bars, kand
        finally:
            con.close()


def chart_trade(t, bars, kand):
    if not bars:
        return None
    ets = _entry_ts(t)
    stuk = [b[:5] for b in bars if ets - 120 * 60 <= b[0] <= ets + 30 * 60]
    entry = t["entry_prijs"] if t["entry_prijs"] is not None else t["entry"]
    lijnen = [(t["sl_start"], "#ef5b5b", "SL", False), (entry, "#f0f0f0", "entry", False),
              (t["tp_start"], "#3ecf8e", "TP", False), (t["expansie_begin"], "#c9a227", "begin?", True)]
    mark = [((ets // 60) * 60, "#f0f0f0", "entry")]
    if kand:
        mark += [(kand["sweep_tijd"], "#ff9f43", "sweep"), (kand["begin_tijd"], "#c9a227", "begin")]
    return chart_png(stuk, lijnen, mark, titel=f"#{t['id']} {(t['richting'] or '').upper()}")


def meld_trade(tid, pad=None, md_pad=None, stuur=True):
    """Na elke nieuwe trade uit MT5 (en via /tptype): voorstel opslaan en het bericht sturen."""
    t, bars, kand = bereid_trade(tid, pad, md_pad)
    if t is None or not stuur:
        return None
    png = None
    try:
        png = chart_trade(t, bars, kand)
    except Exception as e:
        print("[v3] grafiekje trade:", e)
    mid = _stuur(tekst_trade(t), knoppen_trade(t), png=png)
    if mid:
        with _LOCK:
            con = conn(pad)
            try:
                _onthoud_bericht(con, mid, "trade", tid)
                con.commit()
            finally:
                con.close()
    return mid


def zet_trade(tid, tp_type=None, expansie_begin=None, klopt=False, pad=None):
    with _LOCK:
        con = conn(pad)
        try:
            t = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
            if t is None:
                raise ValueError(f"trade {tid} bestaat niet")
            zet = {}
            if tp_type is not None:
                if tp_type not in TP_TYPES.values():
                    raise ValueError(f"onbekend TP-type {tp_type}")
                zet.update(tp_type=tp_type, tp_type_bron="marijn")
                if tp_type == "50%" and t["expansie_bron"] != "marijn" and t["sl_start"] and t["tp_start"]:
                    short = (t["richting"] or "").lower() == "short"
                    m = S.STANDAARD["sl_marge_points"] * S.STANDAARD["punt"]
                    sweep = t["sl_start"] - m if short else t["sl_start"] + m
                    zet.update(expansie_begin=round(2 * t["tp_start"] - sweep, 2), expansie_bron="voorstel")
            if expansie_begin is not None:
                zet.update(expansie_begin=float(expansie_begin), expansie_bron="marijn")
            if klopt:
                if t["tp_type"] and "tp_type" not in zet:
                    zet["tp_type_bron"] = "marijn"
                if t["expansie_begin"] is not None and "expansie_begin" not in zet:
                    zet["expansie_bron"] = "marijn"
            if zet:
                con.execute(f"UPDATE trades SET {', '.join(k + '=?' for k in zet)} WHERE id=?", list(zet.values()) + [tid])
                con.commit()
            return con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
        finally:
            con.close()


# ------------------------------------------------------------------ knoppen en antwoorden uit de journal-bot

def callback(c, cb):
    """'v:{id}:{a|b|c|n|z}' (signaal) of 't:{trade}:{11|50|an|ok}' (eigen trade)."""
    jb = _bot()
    antwoord = "Opgeslagen"
    try:
        soort, ref, code = (cb.get("data") or "").split(":")
        msg = cb.get("message") or {}
        doel = {"chat_id": msg.get("chat", {}).get("id"), "message_id": msg.get("message_id")}
        if soort == "v":
            label = LABELS[code][0]
            zet_label(int(ref), label)
            jb.api(c["token"], "editMessageReplyMarkup", {**doel, "reply_markup": knoppen_signaal(int(ref), label)})
            antwoord = f"Label {LABELS[code][1]} ✓"
        else:
            if code == "ok":
                t = zet_trade(int(ref), klopt=True)
            else:
                t = zet_trade(int(ref), tp_type=TP_TYPES[code])
            veld = "caption" if msg.get("photo") else "text"
            methode = "editMessageCaption" if veld == "caption" else "editMessageText"
            jb.api(c["token"], methode, {**doel, veld: tekst_trade(t), "parse_mode": "HTML", "reply_markup": knoppen_trade(t)})
            antwoord = "Klopt ✓" if code == "ok" else f"TP-type {TP_TYPES[code]} ✓"
    except Exception as e:
        antwoord = "Kon dit niet opslaan"
        print("[v3] callback:", e)
    jb.api(c["token"], "answerCallbackQuery", {"callback_query_id": cb.get("id"), "text": antwoord})


def antwoord(message_id, tekst, pad=None):
    """Reply op een v3-trade-bericht met een prijs = het begin van de expansie. Geeft een zin terug, of None als
    het bericht niet van v3 is (dan doet de journal-bot zijn eigen ding)."""
    with _LOCK:
        con = conn(pad)
        try:
            r = con.execute("SELECT soort, ref FROM v3_berichten WHERE message_id=?", (int(message_id),)).fetchone()
        finally:
            con.close()
    if r is None or r["soort"] != "trade":
        return None
    import re
    m = re.search(r"(\d{3,5}(?:[.,]\d+)?)", tekst or "")
    if not m:
        return "Stuur alleen de prijs waar de expansie begon, bv. 4150.2"
    prijs = float(m.group(1).replace(",", "."))
    t = zet_trade(int(r["ref"]), expansie_begin=prijs, pad=pad)
    return f"✅ Trade #{t['id']}: expansie begon op {_p(prijs)} (opgeslagen)."


def telling(pad=None, dagen=14):
    """Labels per dag (voor /v3 en de controle): {datum: {totaal, A, B, C, nee, niet_gezien, open}}."""
    con = conn(pad)
    try:
        van = (datetime.now() - timedelta(days=dagen)).strftime("%Y-%m-%d")
        uit = {}
        for r in con.execute("SELECT datum, groep, MAX(label) AS label FROM v3_labels WHERE datum>=? GROUP BY datum, groep", (van,)):
            d = uit.setdefault(r["datum"], {"totaal": 0, "open": 0, **{v[0]: 0 for v in LABELS.values()}})
            if r["label"]:
                d["totaal"] += 1
                d[r["label"]] += 1
            else:
                d["open"] += 1
        return uit
    finally:
        con.close()


def telling_tekst(pad=None):
    t = telling(pad)
    if not t:
        return "Nog geen v3-signalen in je venster."
    regels = ["<b>v3-labels</b> (per sweep)"]
    tot = ab = 0
    for d in sorted(t):
        x = t[d]
        tot += x["totaal"]
        ab += x["A"] + x["B"]
        regels.append(f"{d}: {x['totaal']} gelabeld (A {x['A']} · B {x['B']} · C {x['C']} · nee {x['nee']} · "
                      f"niet gezien {x['niet_gezien']}) · open {x['open']}")
    regels.append(f"<b>14 dagen: {tot} labels, {ab} A/B</b> (doel na 2 weken: 150, waarvan 20 A/B)")
    return "\n".join(regels)
