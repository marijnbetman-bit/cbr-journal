# -*- coding: utf-8 -*-
"""
Test voor mt5_koppeling.py met een nep-MetaTrader. Draait zonder MT5:
    python test_mt5_koppeling.py
Speelt 22 sep 2026 na: twee SL-trades die je al logde (moeten GEKOPPELD
worden), de 17:21-winnaar (moet NIEUW binnenkomen), plus een open positie,
een EURUSD-trade en een oude trade die genegeerd moeten worden.
"""
import os, shutil, sqlite3, sys, tempfile, time
from datetime import datetime, timezone
from types import SimpleNamespace as NS

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)
import mt5_koppeling as mk

OFFSET = 3  # Vantage-server = UTC+3 in de zomer


def sts(jaar, maand, dag, uur, minuut):
    """Servertijd als epoch (MT5 geeft servertijd 'alsof het UTC is')."""
    return int(datetime(jaar, maand, dag, uur, minuut, tzinfo=timezone.utc).timestamp())


def deal(pid, entry, typ, vol, prijs, t, profit=0.0, comm=-0.05, sym="XAUUSD+",
         reason=0, comment="", order=None):
    return NS(position_id=pid, entry=entry, type=typ, volume=vol, price=prijs, time=t,
              profit=profit, commission=comm, swap=0.0, fee=0.0, symbol=sym,
              reason=reason, comment=comment, order=order or pid * 10)


class NepMT5:
    TIMEFRAME_M1 = 1

    def __init__(self):
        B, S = mk.TYPE_BUY, mk.TYPE_SELL
        IN, OUT = mk.ENTRY_IN, mk.ENTRY_OUT
        self.deals = [
            # 11:12 Amsterdam = 12:12 server -- short, SL geraakt, -5,64 (staat al als #35)
            deal(101, IN, S, 0.01, 4340.20, sts(2026, 9, 22, 12, 12), order=1010),
            deal(101, OUT, B, 0.01, 4345.84, sts(2026, 9, 22, 12, 19), profit=-5.64,
                 reason=4, comment="[sl 4345.84]"),
            # 11:16 -> 12:16 server -- short, SL, -8,15 (staat al als #36)
            deal(102, IN, S, 0.01, 4341.00, sts(2026, 9, 22, 12, 16), order=1020),
            deal(102, OUT, B, 0.01, 4349.15, sts(2026, 9, 22, 12, 31), profit=-8.15,
                 reason=4, comment="[sl 4349.15]"),
            # 17:21 -> 18:21 server -- short, TP geraakt, +8,32 (NIEUW)
            deal(103, IN, S, 0.01, 4352.40, sts(2026, 9, 22, 18, 21), order=1030),
            deal(103, OUT, B, 0.01, 4344.08, sts(2026, 9, 22, 18, 44), profit=8.32,
                 reason=5, comment="[tp 4344.08]"),
            # open positie: alleen een in-deal
            deal(104, IN, B, 0.01, 4350.00, sts(2026, 9, 22, 19, 5), order=1040),
            # EURUSD: moet genegeerd worden
            deal(105, IN, B, 0.10, 1.1700, sts(2026, 9, 22, 13, 0), sym="EURUSD"),
            deal(105, OUT, S, 0.10, 1.1710, sts(2026, 9, 22, 13, 30), profit=8.5, sym="EURUSD"),
            # oude trade van 20 sep: voor sync_vanaf, moet genegeerd worden
            deal(106, IN, B, 0.01, 4300.0, sts(2026, 9, 20, 12, 0), order=1060),
            deal(106, OUT, S, 0.01, 4303.0, sts(2026, 9, 20, 12, 10), profit=3.0, reason=5),
            # balanspost (geen positie)
            deal(0, 2, 2, 0, 0, sts(2026, 9, 22, 8, 0), profit=100.0),
        ]
        self.orders = {
            101: [NS(ticket=1010, sl=0.0, tp=4334.56, time_setup=1)],   # SL pas later gezet
            102: [NS(ticket=1020, sl=4349.15, tp=4333.0, time_setup=1)],
            103: [NS(ticket=1030, sl=4360.72, tp=4344.08, time_setup=1)],
        }
        self.open = [NS(identifier=104, ticket=104, symbol="XAUUSD+", type=mk.TYPE_BUY,
                        sl=4345.0, tp=4360.0)]

    def initialize(self, *a): return True
    def shutdown(self): pass
    def last_error(self): return (0, "ok")
    def account_info(self): return NS(login=12345678, server="VantageInternational-Live", currency="EUR")
    def terminal_info(self): return NS(connected=True)
    def symbol_select(self, s, v): return True
    def symbol_info_tick(self, s): return NS(time=int(time.time()) + OFFSET * 3600)
    def positions_get(self): return tuple(self.open)
    def history_deals_get(self, van, tot): return tuple(self.deals)
    def history_orders_get(self, position=None): return tuple(self.orders.get(position, []))

    def copy_rates_range(self, sym, tf, van, tot):
        a, b = int(van.timestamp()), int(tot.timestamp())
        uit, p, t = [], 4345.0, a - a % 60
        while t <= b:
            p += 0.3 if (t // 60) % 7 < 3 else -0.25
            uit.append({"time": t, "open": p, "high": p + 0.8, "low": p - 0.8, "close": p + 0.1})
            t += 60
        return uit


def main():
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "cbr_journal.db")
    shutil.copy(os.path.join(HIER, "cbr_journal.db"), db)
    mk.SCREENSHOTS_DIR = os.path.join(tmp, "screenshots")

    con = sqlite3.connect(db)
    voor = con.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    con.close()

    k = mk.Koppeling(mt5=NepMT5(), db_pad=db)
    meldingen = []
    k.bij_nieuwe_trade.append(meldingen.append)
    cfg = dict(mk.STANDAARD, sync_vanaf="2026-09-22")
    nieuw = k.ronde(cfg)

    con = sqlite3.connect(db); con.row_factory = sqlite3.Row
    na = con.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    fouten = []

    def check(cond, tekst):
        print(("  OK   " if cond else "  FOUT ") + tekst)
        if not cond:
            fouten.append(tekst)

    print(f"trades voor {voor}, na {na}; nieuw: {nieuw}; meldingen: {meldingen}")
    check(na == voor + 1, "precies 1 trade erbij (de 17:21-winnaar)")
    check(k.status["offset_uur"] == 3, "serverklok automatisch op UTC+3 bepaald")

    t35 = con.execute("SELECT * FROM trades WHERE id=35").fetchone()
    check(t35["positie_id"] == 101, "#35 gekoppeld aan MT5-positie 101")
    check(t35["resultaat_eur"] == -5.64 and abs(t35["charges"] + 0.10) < 1e-9,
          "#35 resultaat -5,64 en charges -0,10 van de broker")
    check(t35["sl_prijs"] == 4345.84, "#35 SL uit de sluitregel ('SL pas later gezet')")
    check(t35["beoordeeld"] == 1, "#35 telt als beoordeeld (jij vulde al criteria in)")
    check("DXY" in (t35["notities"] or ""), "#35 je eigen notitie is blijven staan")

    t36 = con.execute("SELECT * FROM trades WHERE id=36").fetchone()
    check(t36["positie_id"] == 102, "#36 gekoppeld aan MT5-positie 102")

    n = con.execute("SELECT * FROM trades WHERE positie_id=103").fetchone()
    check(n is not None, "17:21-trade staat erin")
    if n:
        check(n["datum"] == "2026-09-22" and n["tijd_entry"] == "17:21",
              f"datum/tijd Amsterdams: {n['datum']} {n['tijd_entry']} (exit {n['tijd_exit']})")
        check(n["richting"] == "short" and n["resultaat_eur"] == 8.32, "short, +8,32")
        check(abs(n["charges"] + 0.10) < 1e-9, "charges -0,10")
        check(n["sl"] == 4360.72 and n["tp"] == 4344.08, "SL/TP uit je order")
        check(n["rr"] == round(83.2 / 83.2, 2), f"RR {n['rr']} (83,2 pts risico / 83,2 pts doel)")
        check(n["resultaat_r"] is not None and abs(n["resultaat_r"] - 1.0) < 0.02,
              f"resultaat {n['resultaat_r']}R")
        check(n["duur_minuten"] == 23, f"duur {n['duur_minuten']} min")
        check(n["exit_reden"] == "TP geraakt", "exit-reden 'TP geraakt'")
        check(n["beoordeeld"] == 0 and n["grade"] == "C", "wacht op beoordeling, grade C")
        check(n["sessie"] == "buiten venster", "sessie: buiten venster (17:21)")
        check(n["mfe_points"] is not None, f"MFE {n['mfe_points']} / MAE {n['mae_points']} pts")
        sc = con.execute("SELECT pad FROM screenshots WHERE trade_id=?", (n["id"],)).fetchall()
        check(len(sc) == 1, f"chart gemaakt: {sc[0]['pad'] if sc else '-'}")
        check(meldingen == [n["id"]], "melding (voor Telegram) afgevuurd voor alleen deze trade")

    check(con.execute("SELECT COUNT(*) FROM trades WHERE positie_id IN (104,105,106)").fetchone()[0] == 0,
          "open positie, EURUSD en oude trade genegeerd")
    op = con.execute("SELECT * FROM mt5_posities WHERE positie_id=104").fetchone()
    check(op is not None and op["eerste_sl"] == 4345.0, "open positie: SL onthouden")

    # tweede ronde: niets nieuws, niets dubbel
    nieuw2 = k.ronde(cfg)
    na2 = con.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    check(nieuw2 == [] and na2 == na, "tweede ronde: niets dubbel")
    con.close()

    # los: tijd-rekensom winter
    w = mk.server_naar_amsterdam(sts(2026, 12, 1, 12, 0), 2)
    check(w.strftime("%H:%M") == "11:00", f"wintertijd: server 12:00 (UTC+2) -> {w:%H:%M} Amsterdam")

    print("\nALLES GOED" if not fouten else f"\n{len(fouten)} FOUT(EN)")
    shutil.copy(os.path.join(mk.SCREENSHOTS_DIR, "2026-09-22", "mt5_103.svg"),
                os.path.join(tmp, "..", "voorbeeld_mt5_chart.svg")) if not fouten else None
    return 1 if fouten else 0


if __name__ == "__main__":
    sys.exit(main())
