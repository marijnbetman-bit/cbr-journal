# -*- coding: utf-8 -*-
"""Test plan v3 fase 2 (v3_labels.py) op een KOPIE van cbr_journal.db en de echte candles van 6 okt 2026 (marktdata.db).
Telegram wordt nagebootst: er gaat niets de deur uit, de echte database blijft onaangeroerd.
  0 Migratie (8 okt 2026) op de kopie van de echte database: A/B/C -> ja + grade, nee -> nee zonder reden, niet gezien ->
    niet_gezien; label blijft gelijk; tweede keer verandert er niets; geen back-up van een kopie.
  1 6 okt nagespeeld minuut voor minuut: v3-berichten alleen binnen het venster, één per sweep, met grafiekje en stap 1.
  2 Getrapte knoppen met een nep-signaal: ja -> A/B/C, nee -> redenen (aan/uit) + klaar, niet gezien, wijzig, oude knoppen;
    alleen editMessageReplyMarkup (geen nieuwe berichten); reply = opmerking; signalenpagina-API en CSV.
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

# --- 0. migratie op de kopie van de echte database
ruw = sqlite3.connect(DB)
ruw.row_factory = sqlite3.Row
kol_voor = {r[1] for r in ruw.execute("PRAGMA table_info(v3_labels)")}
voor = {r["sleutel"]: r["label"] for r in ruw.execute("SELECT sleutel, label FROM v3_labels")} if kol_voor else {}
ruw.close()
backups_voor = set(os.listdir(os.path.join(HIER, "backups"))) if os.path.isdir(os.path.join(HIER, "backups")) else set()
con = V.conn(DB)
na = {r["sleutel"]: r for r in con.execute("SELECT * FROM v3_labels")}
al_gemigreerd = "oordeel" in kol_voor             # het echte journal draait de nieuwe code al: dan alleen de samenhang toetsen
goed = all((na[s]["label"] == l) and (
    (l in ("A", "B", "C") and na[s]["oordeel"] == "ja" and na[s]["grade"] == l) or
    (l == "nee" and na[s]["oordeel"] == "nee" and na[s]["grade"] is None and (al_gemigreerd or json.loads(na[s]["redenen"]) == [])) or
    (l == "niet_gezien" and na[s]["oordeel"] == "niet_gezien") or
    (l is None and na[s]["oordeel"] in (None, "ja"))) and (al_gemigreerd or l is None or na[s]["afgerond"] == 1) for s, l in voor.items())
tel = {}
for l in voor.values():
    tel[l] = tel.get(l, 0) + 1
check(bool(voor) and goed, f"{'al gemigreerd, samenhang' if al_gemigreerd else 'migratie'} van {sum(1 for l in voor.values() if l)} labels "
      f"{json.dumps(tel)}: ja + grade / nee / niet_gezien, label gelijk")
V._GEMIGREERD.discard(DB)
V.conn(DB).close()                                  # tweede keer
na2 = {r["sleutel"]: tuple(r) for r in con.execute("SELECT * FROM v3_labels")}
check(na2 == {s: tuple(r) for s, r in na.items()}, "migratie twee keer: niets verandert")
backups_na = set(os.listdir(os.path.join(HIER, "backups"))) if os.path.isdir(os.path.join(HIER, "backups")) else set()
check(backups_na == backups_voor, "geen back-up gemaakt van een kopie (alleen de echte database krijgt er een)")

# --- 1. 6 oktober nagespeeld
cfg = V.lees_config()
dag_van = int(V.datetime(2026, 10, 6, 0, 0, tzinfo=V.AMS).timestamp())
dag_tot = int(V.datetime(2026, 10, 6, 22, 0, tzinfo=V.AMS).timestamp())
alle = V._candles_md(dag_van - 400 * 60, dag_tot)
check(len(alle) > 1000, f"candles van 6 okt uit marktdata.db: {len(alle)}")
V._EERSTE_LIVE = None
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
check(all([b["text"] for b in sum(v["knoppen"]["inline_keyboard"], [])] == ["✅ ja", "❌ nee", "👀 niet gezien"] for v in VERSTUURD),
      "stap 1 onder elk nieuw bericht: ✅ ja | ❌ nee | 👀 niet gezien")
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

# --- 2. getrapte knoppen met een nep-signaal (een sweep met meerdere orders, als die er is)
def tik(rid, code, mid):
    API.clear()
    V.callback(NepBot.cfg(), {"id": "q", "data": f"v:{rid}:{code}", "message": {"chat": {"id": 1}, "message_id": mid, "photo": [{}]}})
    km = [d["reply_markup"]["inline_keyboard"] for m, d in API if m == "editMessageReplyMarkup"]
    antw = [d["text"] for m, d in API if m == "answerCallbackQuery"]
    return (km[-1] if km else None), (antw[-1] if antw else None), [m for m, _ in API]


def teksten(km):
    return [b["text"] for rij in (km or []) for b in rij]


def groep_rijen(g):
    return con.execute("SELECT * FROM v3_labels WHERE groep=?", (g,)).fetchall()


if rijen:
    per_groep = {}
    for r in rijen:
        per_groep.setdefault(r["groep"], []).append(r)
    g0 = max(per_groep, key=lambda g: len(per_groep[g]))
    r0 = per_groep[g0][0]
    mid = r0["bericht_id"]
    print(f"     nep-signaal: {r0['tijd']} {r0['trade']} groep {g0} ({len(per_groep[g0])} orders), bericht {mid}")
    alle_methoden = []

    km, a, m = tik(r0["id"], "j", mid); alle_methoden += m
    check(teksten(km) == ["A", "B", "C"], f"ja -> knoppen A | B | C ({a})")
    check(all(x["oordeel"] == "ja" and x["label"] is None and not x["afgerond"] for x in groep_rijen(g0)), "ja zonder grade: nog niet klaar (geen label)")
    km, a, m = tik(r0["id"], "b", mid); alle_methoden += m
    check(teksten(km) == ["✅ ja · B", "↩ wijzig"], f"B -> klaar, bericht toont '{teksten(km)[0] if km else '-'}' + ↩ wijzig")
    check(all(x["oordeel"] == "ja" and x["grade"] == "B" and x["label"] == "B" and x["afgerond"] == 1 for x in groep_rijen(g0)),
          "opgeslagen voor de hele sweep: oordeel ja, grade B, label B")

    km, a, m = tik(r0["id"], "w", mid); alle_methoden += m
    check(teksten(km) == ["✅ ja", "❌ nee", "👀 niet gezien"], "↩ wijzig -> terug naar stap 1")
    km, a, m = tik(r0["id"], "n", mid); alle_methoden += m
    check(teksten(km) == [t for t in V.REDENEN.values()] + ["klaar"], "nee -> %d redenen + klaar" % len(V.REDENEN))
    km, a, m = tik(r0["id"], "rbos", mid); alle_methoden += m
    km, a, m = tik(r0["id"], "rcons", mid); alle_methoden += m
    check(teksten(km)[0] == "✓ Geen goede BOS" and teksten(km)[3] == "✓ Te veel consolidatie" and not teksten(km)[1].startswith("✓"),
          "redenen aan met ✓ (meerdere tegelijk)")
    km, a, m = tik(r0["id"], "rexp", mid); alle_methoden += m
    km, a, m = tik(r0["id"], "rexp", mid); alle_methoden += m
    check(not teksten(km)[1].startswith("✓"), "zelfde reden nog eens = weer uit (toggle)")
    km, a, m = tik(r0["id"], "k", mid); alle_methoden += m
    check(teksten(km) == ["❌ nee · geen goede BOS, te veel consolidatie", "↩ wijzig"], f"klaar -> '{teksten(km)[0] if km else '-'}'")
    x = groep_rijen(g0)[0]
    check(x["oordeel"] == "nee" and x["grade"] is None and json.loads(x["redenen"]) == ["bos", "cons"] and x["label"] == "nee" and x["afgerond"] == 1,
          "opgeslagen: oordeel nee, grade leeg, redenen [bos, cons], label nee")

    km, a, m = tik(r0["id"], "w", mid); alle_methoden += m
    km, a, m = tik(r0["id"], "z", mid); alle_methoden += m
    check(teksten(km) == ["👀 niet gezien", "↩ wijzig"], "niet gezien -> meteen klaar")
    x = groep_rijen(g0)[0]
    check(x["oordeel"] == "niet_gezien" and x["grade"] is None and json.loads(x["redenen"]) == [] and x["label"] == "niet_gezien",
          "opgeslagen: oordeel niet_gezien, oude redenen gewist")
    km, a, m = tik(r0["id"], "i", mid); alle_methoden += m
    check(km is None and a == "👀 niet gezien", "tik op de samenvatting: niets verandert")

    r1 = next(r for g, rs in per_groep.items() if g != g0 for r in rs[:1])
    km, a, m = tik(r1["id"], "a", r1["bericht_id"]); alle_methoden += m
    check(teksten(km) == ["✅ ja · A", "↩ wijzig"] and groep_rijen(r1["groep"])[0]["grade"] == "A", "oude knop A (berichten van vóór vandaag): ja · A")
    check(set(alle_methoden) <= {"editMessageReplyMarkup", "answerCallbackQuery"},
          f"alleen hetzelfde bericht aangepast, nooit een nieuw bericht ({sorted(set(alle_methoden))})")

    zin = V.antwoord(mid, "te vroeg, wachtte op de 1H", pad=DB)
    opm = con.execute("SELECT * FROM v3_opmerkingen WHERE groep=?", (g0,)).fetchall()
    check(len(opm) == 1 and opm[0]["tekst"] == "te vroeg, wachtte op de 1H", f"reply op het signaalbericht = opmerking ({zin})")

    d = V.api_v3_signalen()
    s0 = next(s for s in d["signalen"] if s["groep"] == g0)
    check(s0["oordeel"] == "niet_gezien" and s0["orders"] == len(per_groep[g0]) and s0["opmerkingen"][0]["tekst"].startswith("te vroeg"),
          f"signalenpagina-API: één rij per sweep met oordeel, grade, redenen, opmerkingen (telling {json.dumps(d['telling'])})")
    tik(r0["id"], "w", mid); tik(r0["id"], "n", mid); tik(r0["id"], "rtp", mid)
    km, a, m = tik(r0["id"], "k", mid)
    check(teksten(km)[0] == "❌ nee · TP al gehit voor ik kon enteren", f"reden 'TP al gehit voor ik kon enteren' ({teksten(km)[0] if km else '-'})")
    tik(r0["id"], "w", mid); tik(r0["id"], "n", mid); tik(r0["id"], "rt3", mid); tik(r0["id"], "k", mid)
    csv_tekst = V.export_v3().body.decode("utf-8-sig")
    kop = csv_tekst.splitlines()[0].split(";")
    regel = next(l for l in csv_tekst.splitlines() if g0 in l).split(";")
    check({"oordeel", "grade", "redenen"} <= set(kop) and regel[kop.index("oordeel")] == "nee"
          and regel[kop.index("redenen")] == "Geen goede type 3 shift" and "te vroeg" in regel[kop.index("opmerkingen")],
          "CSV-export: kolommen oordeel, grade, redenen (+ opmerkingen en kenmerken)")
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
