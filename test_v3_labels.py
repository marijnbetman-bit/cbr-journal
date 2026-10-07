# -*- coding: utf-8 -*-
"""Test plan v3 fase 2 (v3_labels.py) op een KOPIE van cbr_journal.db en de echte candles van 6 okt 2026 (marktdata.db).
Telegram wordt nagebootst: er gaat niets de deur uit, de echte database blijft onaangeroerd.
  1 6 okt nagespeeld minuut voor minuut: v3-berichten alleen binnen het venster, één per sweep, met grafiekje.
  2 Knop A op een bericht: label op alle kandidaten van die sweep; knoppen tonen het gekozen label.
  3 Trades 62/63/65: start-SL/TP uit mt5_positie_events (of de trade), voorstel TP-type en expansie-begin.
  4 Knoppen en antwoord op een trade-bericht: TP-type, 'klopt', prijs als begin van de expansie.
    python test_v3_labels.py"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile

import v3_labels as V

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HIER = os.path.dirname(os.path.abspath(__file__))
fouten = []


def check(ok, tekst):
    print(("  OK   " if ok else "  FOUT ") + tekst)
    if not ok:
        fouten.append(tekst)


tmp = tempfile.mkdtemp(prefix="v3t_")
DB = os.path.join(tmp, "j.db")
src = sqlite3.connect(f"file:{os.path.join(HIER, 'cbr_journal.db')}?mode=ro", uri=True)
dst = sqlite3.connect(DB)
src.backup(dst)
src.close()
dst.close()
V.DB_PAD = DB                                   # alles hierna op de kopie

# --- Telegram nabootsen
VERSTUURD, API = [], []


class NepBot:
    @staticmethod
    def cfg():
        return {"aan": True, "token": "x", "chat_id": 1}

    @staticmethod
    def api(token, methode, data=None, timeout=35):
        API.append((methode, data))
        return {"ok": True, "result": {"message_id": 9000 + len(API)}}

    @staticmethod
    def _ssl_ctx():
        return None


def nep_stuur(tekst, knoppen, png=None, stil=False, antwoord_op=None):
    VERSTUURD.append({"tekst": tekst, "knoppen": knoppen, "png": png})
    return 5000 + len(VERSTUURD)


V._bot = lambda: NepBot
V._stuur = nep_stuur

# --- 1. 6 oktober nagespeeld
cfg = V.lees_config()
dag_van = int(V.datetime(2026, 10, 6, 0, 0, tzinfo=V.AMS).timestamp())
dag_tot = int(V.datetime(2026, 10, 6, 22, 0, tzinfo=V.AMS).timestamp())
alle = V._candles_md(dag_van - 400 * 60, dag_tot)
check(len(alle) > 1000, f"candles van 6 okt uit marktdata.db: {len(alle)}")
V._EERSTE_LIVE = None
con = V.conn(DB)
con.execute("DELETE FROM v3_labels")
con.commit()
start = next(i for i, b in enumerate(alle) if b[0] >= dag_van)
for i in range(start, len(alle)):
    bars = alle[max(0, i - cfg["candles"] + 1):i + 1]                    # de laatste candle 'loopt nog'
    if V._EERSTE_LIVE is None:
        V._EERSTE_LIVE = bars[-1][0]
    nu = bars[-1][0]
    kands = [k for k in V.S.kandidaten(bars) if k["order_tijd"] >= nu - 4 * 3600]
    V.verwerk(con, kands, bars, nu, cfg)
rijen = con.execute("SELECT * FROM v3_labels WHERE datum='2026-10-06' ORDER BY order_ts").fetchall()
groepen = {r["groep"] for r in rijen}
buiten = [r for r in rijen if not V.in_venster(r["order_ts"], cfg)]
print(f"     {len(rijen)} kandidaten in het venster, {len(groepen)} sweeps, {len(VERSTUURD)} berichten")
for r in rijen[:40]:
    print(f"     {r['tijd']} {r['trade']:5s} sweep {r['sweep']:.2f} entry {r['entry']:.2f} SL {r['sl']:.2f} groep {r['groep']} bericht {r['bericht_id']}")
check(len(rijen) > 0 and not buiten, "alleen kandidaten binnen het venster opgeslagen")
check(len(VERSTUURD) == len(groepen), f"één bericht per sweep ({len(VERSTUURD)} berichten, {len(groepen)} sweeps)")
check(all(v["png"] and v["png"][:4] == b"\x89PNG" for v in VERSTUURD), "elk bericht heeft een grafiekje (PNG)")
check(all(len(v["knoppen"]["inline_keyboard"][0]) == 3 and len(v["knoppen"]["inline_keyboard"][1]) == 2 for v in VERSTUURD),
      "knoppen A / B / C / nee / niet gezien")
with open(os.path.join(tmp, "voorbeeld_signaal.png"), "wb") as f:
    f.write(VERSTUURD[0]["png"] if VERSTUURD else b"")
print("     voorbeeld: " + (VERSTUURD[0]["tekst"].replace("\n", " | ") if VERSTUURD else "-"))

# trades 62/63/65 zien: zit er een v3-bericht kort voor hun entry?
for tid in (62, 63, 65):
    t = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
    ets = V._entry_ts(t)
    raak = [r for r in rijen if r["trade"] == t["richting"] and r["order_ts"] - 12 * 60 <= ets <= r["order_ts"] + 33 * 60
            and abs(r["sl"] - t["sl_prijs"]) <= 0.3]
    check(bool(raak and raak[0]["bericht_id"]), f"trade {tid} ({t['tijd_entry']}): v3-bericht om {raak[0]['tijd'] if raak else '-'}")

# --- 2. knop A
if rijen:
    r0 = next(r for r in rijen if r["bericht_id"])
    API.clear()
    V.callback(NepBot.cfg(), {"id": "q", "data": f"v:{r0['id']}:a", "message": {"chat": {"id": 1}, "message_id": r0["bericht_id"]}})
    lab = {x["label"] for x in con.execute("SELECT label FROM v3_labels WHERE groep=?", (r0["groep"],))}
    check(lab == {"A"}, f"label A op de hele sweep {r0['groep']}: {lab}")
    km = [d for m, d in API if m == "editMessageReplyMarkup"]
    check(bool(km) and km[0]["reply_markup"]["inline_keyboard"][0][0]["text"].startswith("●"), "knop A toont ●")
    check(any(m == "answerCallbackQuery" for m, _ in API), "tik bevestigd")
    print("     " + V.telling_tekst(DB).replace("\n", " | "))

# --- 3. trades
VERSTUURD.clear()
for tid in (62, 63, 65):
    mid = V.meld_trade(tid, pad=DB)
    t = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
    print(f"     #{tid}: entry {t['entry_prijs']} start-SL {t['sl_start']} start-TP {t['tp_start']} -> {t['tp_type']} "
          f"({t['tp_type_bron']}), begin {t['expansie_begin']} ({t['expansie_bron']}), v3 {t['v3_sleutel']}")
    check(mid and t["sl_start"] and t["tp_type"] in ("1:1", "50%") and t["expansie_begin"] is not None,
          f"trade {tid}: voorstel TP-type {t['tp_type']}, begin {t['expansie_begin']}")
check(all(v["png"] for v in VERSTUURD), "trade-berichten hebben een grafiekje")
if VERSTUURD:
    with open(os.path.join(tmp, "voorbeeld_trade.png"), "wb") as f:
        f.write(VERSTUURD[-1]["png"])

# --- 4. knoppen en antwoord op de trade
API.clear()
V.callback(NepBot.cfg(), {"id": "q", "data": "t:63:11", "message": {"chat": {"id": 1}, "message_id": 1}})
t = con.execute("SELECT * FROM trades WHERE id=63").fetchone()
check(t["tp_type"] == "1:1" and t["tp_type_bron"] == "marijn", "knop 1:1 -> tp_type 1:1 (marijn)")
V.callback(NepBot.cfg(), {"id": "q", "data": "t:63:ok", "message": {"chat": {"id": 1}, "message_id": 1}})
t = con.execute("SELECT * FROM trades WHERE id=63").fetchone()
check(t["expansie_bron"] == "marijn", "klopt -> expansie-begin bevestigd")
mid65 = con.execute("SELECT message_id FROM v3_berichten WHERE soort='trade' AND ref='65'").fetchone()[0]
zin = V.antwoord(mid65, "4141,5", pad=DB)
t = con.execute("SELECT * FROM trades WHERE id=65").fetchone()
check(t["expansie_begin"] == 4141.5 and t["expansie_bron"] == "marijn", f"antwoord '4141,5' -> begin 4141.5 ({zin})")
check(V.antwoord(123456789, "hallo", pad=DB) is None, "antwoord op een ander bericht: v3 laat het liggen")
V.meld_trade(65, pad=DB)
t = con.execute("SELECT * FROM trades WHERE id=65").fetchone()
check(t["expansie_begin"] == 4141.5, "opnieuw melden overschrijft jouw bevestiging niet")

con.close()
print(f"\n     grafiekjes: {tmp}")
print("\nALLES GOED" if not fouten else f"\n{len(fouten)} FOUT(EN)")
sys.exit(1 if fouten else 0)
