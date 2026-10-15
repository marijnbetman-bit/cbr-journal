# -*- coding: utf-8 -*-
"""15 okt 2026: een break-even trade (#81: +0,04 bruto, -0,26 kosten, RR 2,79) gaf geen R uit MT5 en het journal maakte er via
'winst / RR' een risico van 0,014 van, dus -15R; het dagtotaal werd -7,58R in plaats van +7,78R. Deze test borgt:
  1 mt5_koppeling.bereken: bij (bijna) break-even het risico uit de lotgrootte (per_lot_referentie), R ~ 0
  2 app/edge.r_van_trade: break-even zonder R wordt 0R, niet een enorme min-R; gewone winst blijft 'afgeleid'
  3 herstel_r: zet alleen MT5-trades zonder R recht
    python test_r_breakeven.py"""
import sqlite3
import sys

import mt5_koppeling as mk
from app import edge

fouten = []


def check(ok, tekst):
    print(("  OK   " if ok else "  FOUT ") + tekst)
    if not ok:
        fouten.append(tekst)


print("1. bereken")
pos = {"entry": 4144.67, "exit": 4144.66, "richting": "short", "bruto": 0.04, "lot": 0.05}
m = mk.bereken(pos, 4145.56, 4142.19)
check(m["resultaat_r"] is None, "zonder referentie: geen R (oud gedrag)")
m = mk.bereken(pos, 4145.56, 4142.19, per_lot=89.23)
check(m["risico_eur"] == 3.97 and abs(m["resultaat_r"]) < 0.05, "met referentie: risico 3,97, R %s" % m["resultaat_r"])
m = mk.bereken({"entry": 4141.01, "exit": 4142.32, "richting": "short", "bruto": -5.84, "lot": 0.05}, 4144.13, 4138.9, per_lot=89.23)
check(m["resultaat_r"] == -0.42, "gewone trade: ongewijzigd (%s)" % m["resultaat_r"])

print("2. edge.r_van_trade")
check(edge.r_van_trade({"resultaat_eur": 0.04, "charges": -0.26, "rr": 2.79})[0] == 0.0, "break-even zonder R: 0R")
r, h = edge.r_van_trade({"resultaat_eur": 20.0, "charges": -0.26, "rr": 2.0})
check(h == "afgeleid" and r > 1.9, "gewone winst zonder R: afgeleid (%.2f)" % r)
check(edge.r_van_trade({"resultaat_eur": 0.04, "charges": -0.26, "rr": 2.79, "resultaat_r": 0.01})[0] == 0.01, "gemeten R gaat altijd voor")

print("3. herstel_r")
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE trades(id INTEGER PRIMARY KEY, richting TEXT, entry_prijs REAL, exit_prijs REAL, sl_prijs REAL, lot REAL, resultaat_eur REAL, "
            "risico_eur REAL, resultaat_r REAL, tags TEXT, verwijderd_op TEXT)")
con.execute("INSERT INTO trades VALUES(80,'short',4141.01,4142.32,4144.13,0.05,-5.84,13.91,-0.42,'mt5-auto',NULL)")
con.execute("INSERT INTO trades VALUES(81,'short',4144.67,4144.66,4145.56,0.05,0.04,NULL,NULL,'mt5-auto',NULL)")
con.execute("INSERT INTO trades VALUES(82,'short',4144.67,4144.66,4145.56,0.05,0.04,NULL,NULL,'handmatig',NULL)")
h = mk.herstel_r(con)
check([x[0] for x in h] == [81], "alleen #81 (MT5, zonder R) hersteld: %s" % h)
check(con.execute("SELECT resultaat_r FROM trades WHERE id=80").fetchone()[0] == -0.42, "trade met R blijft ongewijzigd")

print("\nALLES GOED" if not fouten else "\n%d FOUT(EN)" % len(fouten))
sys.exit(1 if fouten else 0)
