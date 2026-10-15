# -*- coding: utf-8 -*-
"""Journal v2, game mode (15 okt 2026). Draait op een KOPIE van de journal-database, zonder MT5 en zonder Telegram.
  1 sim(): SL/TP op de candles (SL eerst bij twijfel), break-even, afrekenen na de horizon
  2 _beheer(): SL naar BE, SL verruimd, TP verplaatst uit de MT5-events
  3 endpoints: /api/game/trades, /simulatie, /gemist, /replay, /account; /game geeft de pagina; klassiek '/' blijft gelijk
    python test_game_mode.py"""
import os
import shutil
import sqlite3
import sys
import tempfile

os.environ["CBR_GEEN_MT5"] = "1"
fouten = []


def check(ok, tekst):
    print(("  OK   " if ok else "  FOUT ") + tekst)
    if not ok:
        fouten.append(tekst)


from app import game  # noqa: E402

print("1. sim")
C = [("d 10:00", 0, 100.5, 99.5, 100), ("d 10:01", 0, 101.2, 99.9, 101), ("d 10:02", 0, 103.1, 100.8, 103)]   # (tijd, ts, h, l, c)
check(game.sim(C, 0, False, 100, 99, 102)[:2] == (2.0, "TP"), "long: TP op 2R geraakt")
check(game.sim(C, 0, True, 100, 101, 98)[:2] == (-1.0, "SL"), "short: SL geraakt in candle 2")
check(game.sim([("d", 0, 101.5, 98.5, 100)], 0, False, 100, 99, 101)[1] == "SL", "één candle raakt SL én TP: SL telt (voorzichtig)")
check(game.sim(C, 0, False, 100, 99, 110, be_bij_r=1.0)[1] in ("open", "BE"), "break-even na 1R: geen verlies meer mogelijk")
check(game.sim(C, 0, False, 100, 99, 110, horizon=2)[1] == "open", "na de horizon: afgerekend op de slotkoers")

print("2. beheer")
ev = [{"ts": "2026-10-15T10:31:40", "soort": "open", "sl": 4159.03, "tp": 4151.07, "prijs": 4157.67},
      {"ts": "2026-10-15T10:31:55", "soort": "sl_tp", "sl": 4159.31, "tp": 4151.07, "prijs": 4157.88},
      {"ts": "2026-10-15T10:35:30", "soort": "sl_tp", "sl": 4158.11, "tp": 4152.18, "prijs": 4154.16}]
b = game._beheer(ev, {"entry_prijs": 4158.13, "sl_prijs": 4159.03, "richting": "short"})
check(b["sl_verruimd"] == 1 and b["sl_moves"] == 2 and b["tp_moves"] == 1, "trade #83: SL 1x verruimd, 2x verplaatst, TP 1x")
check(b["be_min"] == 3.8, "SL naar break-even na 3,8 min")

print("3. endpoints (kopie van de data)")
hier = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix="journal_v2_")
for f in ("cbr_journal.db", "marktdata.db"):
    if os.path.exists(os.path.join(hier, f)):
        s, d = sqlite3.connect(os.path.join(hier, f)), sqlite3.connect(os.path.join(tmp, f))
        s.backup(d); d.close(); s.close()
from app import db  # noqa: E402
db.DB_PATH = os.path.join(tmp, "cbr_journal.db")
game.MARKT_DB = os.path.join(tmp, "marktdata.db")
game.STATION = "http://127.0.0.1:9"                          # station 'uit': de journal moet gewoon werken
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
c = TestClient(app)
t = c.get("/api/game/trades").json()
check(len(t["trades"]) > 0 and all({"r", "uur", "weekdag", "sl_verruimd", "kosten_r"} <= set(x) for x in t["trades"]), "trades: %d met filtervelden" % len(t["trades"]))
check(all(x["uur"] is None or 0 <= x["uur"] <= 23 for x in t["trades"]), "uren genormaliseerd (ook '7:05')")
s = c.get("/api/game/simulatie").json()
check(s["totaal"]["n"] > 0 and "1R" in s["totaal"]["var"], "simulatie: %d trades, plan %sR tegen echt %sR" % (s["totaal"]["n"], s["totaal"]["plan"], s["totaal"]["echt"]))
g = c.get("/api/game/gemist").json()
check(g["station"] is False and "orders" in g, "gemist werkt ook zonder station (orders: %d)" % len(g["orders"]))
r = c.get("/api/game/replay/%d" % t["trades"][-1]["id"]).json()
check("candles" in r and r["trade"]["id"] == t["trades"][-1]["id"], "replay: %d candles" % len(r["candles"]))
check(c.get("/api/game/station/teams").json().get("error"), "station uit: nette foutmelding, geen crash")
check(c.get("/api/game/station/geheim").json().get("error") == "onbekend", "alleen bekende station-endpoints")
p = c.get("/game")
check(p.status_code == 200 and "game2.js" in p.text and "game-modus" in p.text, "/game geeft de pagina")
k = c.get("/").text
check("index.html" not in k and "homepage.js" in k and 'href="/static/game.css' in k, "klassiek overzicht blijft, game.css alleen als extra laag")

print("4. ronde 2: risico, instap, datakwaliteit, tradepagina")
check(all({"risico_pct", "saldo_voor", "instap_na_bos_min", "order_soort", "slippage_points"} <= set(x) for x in t["trades"]), "trades hebben risico- en instapvelden")
rp = [x["risico_pct"] for x in t["trades"] if x["risico_pct"] is not None]
check(len(rp) > 0 and all(0 < v < 100 for v in rp), "risico %% van saldo voor %d trades (%.2f%% tot %.2f%%)" % (len(rp), min(rp or [0]), max(rp or [0])))
kw = c.get("/api/game/kwaliteit").json()
check({"trades", "met_punten", "punten", "sessies"} <= set(kw) and kw["trades"] == len(t["trades"]), "datakwaliteit: %d van %d trades met een punt" % (kw["met_punten"], kw["trades"]))
check(all(x["sessie"] in kw["sessies"]["groepen"] for x in t["trades"]), "sessienamen samengevoegd tot vaste groepen")
for f in ("game3.js", "game4.js", "gamereplay.js"):
    check(c.get("/static/" + f).status_code == 200, "/static/%s bestaat" % f)
check("game3.js" in p.text and "game4.js" in p.text, "/game laadt game3.js en game4.js")
check("gamereplay.js" in c.get("/trade?id=%d" % t["trades"][-1]["id"]).text, "tradepagina laadt de game-replay")

print("5. instap_order (MT5-orderdata, zonder MT5)")
import mt5_koppeling as mk  # noqa: E402


class O:
    def __init__(self, **kw):
        self.__dict__.update(kw)


lim = [O(ticket=7, type=2, price_open=4100.0, time_setup=1)]
check(mk.instap_order(lim, {"order_id": 7, "richting": "long", "entry": 4100.2}) == ("limiet", 4100.0, 2.0), "buy limit: 0,20 slechter = 2 points slippage")
check(mk.instap_order(lim, {"order_id": 7, "richting": "short", "entry": 4100.2}) == ("limiet", 4100.0, -2.0), "sell limit hoger gevuld = beter (negatief)")
markt = [O(ticket=8, type=1, price_open=0, time_setup=1, time_setup_msc=0)]
check(mk.instap_order(markt, {"order_id": 8, "richting": "short", "entry": 4100.0}) == ("markt", None, None), "marktorder zonder ticks: soort bekend, slippage onbekend")
check(mk.instap_order([], {"order_id": 1}) == (None, None, None), "geen orders: niets")
shutil.rmtree(tmp, ignore_errors=True)

print("\nALLES GOED" if not fouten else "\n%d FOUT(EN)" % len(fouten))
sys.exit(1 if fouten else 0)
