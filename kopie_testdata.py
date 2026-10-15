# -*- coding: utf-8 -*-
"""Journal v2 (test): verse kopie van de live data naar deze map (alleen lezen uit ../cbr-journal).
De tabel mt5_orders (niet-gevulde orders, nieuw in v2) bestaat nog niet in de live journal; die blijft uit de vorige
testkopie behouden. Gebruikt door START-GAMEMODE-TEST.bat."""
import os
import sqlite3

HIER = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(os.path.dirname(HIER), "cbr-journal")

oud_orders = []
pad = os.path.join(HIER, "cbr_journal.db")
if os.path.exists(pad):
    try:
        c = sqlite3.connect(pad)
        oud_orders = c.execute("SELECT * FROM mt5_orders").fetchall()
        kolommen = [r[1] for r in c.execute("PRAGMA table_info(mt5_orders)")]
        c.close()
    except sqlite3.Error:
        oud_orders = []

for f in ("cbr_journal.db", "marktdata.db", "signalen.db"):
    bron = os.path.join(LIVE, f)
    if not os.path.exists(bron):
        continue
    s = sqlite3.connect("file:%s?mode=ro" % bron.replace("\\", "/"), uri=True)
    d = sqlite3.connect(os.path.join(HIER, f))
    s.backup(d)
    d.close()
    s.close()

if oud_orders:
    import sys
    sys.path.insert(0, HIER)
    import mt5_koppeling
    c = sqlite3.connect(pad)
    c.row_factory = sqlite3.Row
    mt5_koppeling.zorg_schema(c)
    c.executemany("INSERT OR REPLACE INTO mt5_orders(%s) VALUES(%s)" % (",".join(kolommen), ",".join("?" * len(kolommen))), oud_orders)
    c.commit()
    c.close()
print("testdata vernieuwd (%d niet-gevulde orders behouden)" % len(oud_orders))
