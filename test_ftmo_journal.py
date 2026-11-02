# -*- coding: utf-8 -*-
"""Test ftmo_journal.py met nagebootste MT5-data op een lege tijdelijke database (raakt cbr_journal.db niet).
    python test_ftmo_journal.py"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace as NS

os.environ["CBR_GEEN_MT5"] = "1"
import ftmo_journal as F  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
fouten = []


def check(ok, tekst):
    print(("  OK   " if ok else "  FOUT ") + tekst)
    if not ok:
        fouten.append(tekst)


UUR = 3600
OFF = 2                                                   # FTMO-servertijd = UTC+2 in de winter
NU = int(datetime(2026, 11, 3, 13, 0, tzinfo=timezone.utc).timestamp())   # 14:00 Amsterdam


def srv(u, m):                                            # servertijd op 3 nov 2026, u:m Amsterdam
    return int(datetime(2026, 11, 3, u - 1, m, tzinfo=timezone.utc).timestamp()) + OFF * UUR


def deal(pid, entry, typ, prijs, t, magic, profit=0.0, reden=None, order=None):
    return {"ticket": pid * 10 + entry, "position_id": pid, "entry": entry, "type": typ, "volume": 0.45, "price": prijs, "time": t,
            "profit": profit, "commission": -1.5 if entry == 0 else 0.0, "swap": 0.0, "fee": 0.0, "symbol": "XAUUSD", "reason": reden,
            "comment": "", "order": order or pid * 10, "magic": magic}


data = {"ok": True, "offset": OFF, "acc": {"login": F.FTMO_LOGIN, "server": F.FTMO_SERVER, "balans": 10040.0, "equity": 9990.0, "valuta": "EUR"},
        "deals": [
            {"ticket": 1, "position_id": 0, "entry": 0, "type": 2, "volume": 0, "price": 0, "time": srv(8, 0), "profit": 10000.0,
             "commission": 0, "swap": 0, "fee": 0, "symbol": "", "reason": 0, "comment": "", "order": 0, "magic": 0},
            # bot: short 4155 -> TP 4145, SL 4157: +5R
            deal(11, 0, 1, 4155.0, srv(10, 2), F.MAGIC_BOT, order=110), deal(11, 1, 0, 4145.0, srv(10, 40), F.MAGIC_BOT, 450.0, 5),
            # zelf: long 4100 -> SL 4098 (eerste SL 4098 gezien, later naar 4099 geschoven): -1R volgens de eerste SL
            deal(12, 0, 0, 4100.0, srv(11, 5), 0, order=120), deal(12, 1, 1, 4099.0, srv(11, 30), 0, -45.0, 4),
            # zelf, nog open
            deal(13, 0, 0, 4120.0, srv(13, 50), 0, order=130)],
        "orders": {110: {"ticket": 110, "sl": 4157.0, "tp": 4145.0, "magic": F.MAGIC_BOT}, 120: {"ticket": 120, "sl": 0.0, "tp": 0.0, "magic": 0}},
        "posities": [{"ticket": 13, "type": 0, "volume": 0.45, "price_open": 4120.0, "sl": 4115.0, "tp": 4130.0, "profit": -50.0, "magic": 0,
                      "time": srv(13, 50), "symbol": "XAUUSD"}]}

tmp = tempfile.mkdtemp(prefix="ftmo_")
con = sqlite3.connect(os.path.join(tmp, "j.db"))
con.row_factory = sqlite3.Row

print("1. Eerste SL van een eigen trade zien terwijl hij open staat")
vooraf = dict(data, deals=data["deals"][:4], posities=[{"ticket": 12, "type": 0, "volume": 0.45, "price_open": 4100.0, "sl": 4098.0, "tp": 4104.0,
                                                         "profit": 0.0, "magic": 0, "time": srv(11, 5), "symbol": "XAUUSD"}])
F.verwerk(con, vooraf, nu=lambda: NU - 2 * UUR)
F.verwerk(con, dict(vooraf, posities=[dict(vooraf["posities"][0], sl=4099.0)]), nu=lambda: NU - 2 * UUR + 60)
g = con.execute("SELECT eerste_sl, laatste_sl FROM ftmo_gezien WHERE positie_id=12").fetchone()
check(tuple(g) == (4098.0, 4099.0), "eerste SL 4098 bewaard, laatste 4099 (%s)" % (tuple(g),))

print("2. Gesloten trades")
uit = F.verwerk(con, data, nu=lambda: NU)
t = {r["positie_id"]: dict(r) for r in con.execute("SELECT * FROM ftmo_trades")}
check(set(t) == {11, 12}, "alleen gesloten posities, storting en open positie niet (%s)" % sorted(t))
check(t[11]["bron"] == "bot" and t[12]["bron"] == "zelf", "bot of zelf via het magic number")
check(t[11]["r"] == 5.0 and t[11]["sl"] == 4157.0, "bot: short 4155 -> 4145 met SL 4157 = +5R (%s)" % t[11]["r"])
check(t[12]["r"] == -0.5 and t[12]["sl"] == 4098.0, "zelf: R tegen de EERSTE SL 4098: exit 4099 = -0,5R (%s)" % t[12]["r"])
check(t[11]["datum"] == "2026-11-03" and t[11]["tijd"] == "10:02", "servertijd -> Amsterdam (%s %s)" % (t[11]["datum"], t[11]["tijd"]))
check(t[11]["netto"] == 448.5 and t[11]["reden"] == "TP", "netto met kosten en reden TP (%s, %s)" % (t[11]["netto"], t[11]["reden"]))
F.verwerk(con, data, nu=lambda: NU + 60)
check(con.execute("SELECT COUNT(*) FROM ftmo_trades").fetchone()[0] == 2, "tweede ronde: geen dubbele trades")

print("3. Pagina-samenvatting")
s = F.samenvatting(con, nu=lambda: NU)
check(s["per_bron"]["bot"]["n"] == 1 and s["per_bron"]["zelf"]["n"] == 1 and s["per_bron"]["alles"]["n"] == 2, "telling per bron")
check(s["per_bron"]["alles"]["r_som"] == 4.5, "som R alles = 4,5 (%s)" % s["per_bron"]["alles"]["r_som"])
v = s["vandaag"]
check(v["start"] == 10040.0 - 448.5, "dagstart (eerste ronde van de dag) = saldo min wat toen al gesloten was (%s)" % v["start"])
check(v["grens"] == 300.0 and v["verlies"] == round(max(0, v["start"] - 9990.0), 2), "dagverlies tegen de grens van 3%% van 10.000 (%s van %s)" % (v["verlies"], v["grens"]))
check(s["totaal"]["vloer"] == 9000.0 and s["totaal"]["ruimte"] == 990.0, "max verlies 10%%: vloer 9000, ruimte %s" % s["totaal"]["ruimte"])
check(len(s["kromme"]) == 2 and s["kromme"][-1][1] == round(10000 + 448.5 - 46.5, 2), "saldokromme uit de trades")

print("4. Alleen het FTMO-account wordt gelezen")


class NepMT5:
    def __init__(self, login, server):
        self.acc = NS(login=login, server=server, balance=10000.0, equity=10000.0, currency="EUR")
        self.gevraagd = []

    def initialize(self, pad):
        return True

    def account_info(self):
        return self.acc

    def last_error(self):
        return (0, "")

    def symbol_select(self, *a):
        return True

    def symbol_info_tick(self, s):
        return NS(time=int(datetime.now().timestamp()) + OFF * UUR)

    def history_deals_get(self, *a):
        self.gevraagd.append("deals")
        return []

    def history_orders_get(self, *a):
        return []

    def positions_get(self):
        return []

    def shutdown(self):
        pass

    def order_send(self, *a):
        raise AssertionError("order_send mag nooit")


m = NepMT5(1705040, "VantageMarkets-Live")
d = F.lees_mt5(m)
check(not d["ok"] and "ander account" in d["fout"] and not m.gevraagd, "live-account 1705040: niets gelezen (%s)" % d["fout"])
m = NepMT5(F.FTMO_LOGIN, "FTMO-Demo")
check(not F.lees_mt5(m)["ok"], "FTMO-login op een andere server: niets gelezen")
m = NepMT5(F.FTMO_LOGIN, F.FTMO_SERVER)
d = F.lees_mt5(m)
check(d["ok"] and d["acc"]["balans"] == 10000.0, "FTMO-account: gelezen, saldo 10000")

con.close()
print("\nALLES GOED" if not fouten else "\n%d FOUT(EN)" % len(fouten))
sys.exit(1 if fouten else 0)
