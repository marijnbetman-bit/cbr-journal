# -*- coding: utf-8 -*-
"""Sandboxtest voor week_review.py: bouwt een tijdelijke journal-DB en toetst de cijfers."""

import os
import sqlite3
import tempfile
import week_review as wr


def _maak_db(pad):
    conn = sqlite3.connect(pad)
    conn.execute("""CREATE TABLE trades (
        id INTEGER PRIMARY KEY, datum TEXT, tijd_entry TEXT, richting TEXT,
        resultaat_eur REAL, charges REAL, grade TEXT, fase TEXT, status TEXT,
        foutcodes TEXT, notities TEXT)""")
    rijen = [
        # deze week (ma 15 - vr 19 sep)
        ("2026-09-15", "10:27", "short", -8.62, -0.46, "C", "fase2_actief", "genomen", "E9", "SL binnen sweep"),
        ("2026-09-15", "16:53", "long", 3.47, -0.06, "A", "fase2_actief", "genomen", "", "nette entry"),
        ("2026-09-16", "07:55", "short", 2.26, -0.06, "C", "fase2_actief", "genomen", "", "snel TP"),
        ("2026-09-16", "14:30", "long", -7.72, -0.10, "C", "fase2_actief", "genomen", "E9", "slippage sweep"),
        ("2026-09-17", "10:29", "long", -4.38, -0.10, "C", "fase2_actief", "genomen", "E9", "te graag gewild"),
        # een overgeslagen no-trade -- mag NIET meetellen
        ("2026-09-16", "12:00", "short", 0.0, 0.0, "C", "fase2_actief", "overgeslagen", "", "niet genomen"),
        # vorige week -- buiten het venster
        ("2026-09-12", "11:00", "short", 5.0, -0.06, "A", "fase2_actief", "genomen", "", "vorige week"),
    ]
    conn.executemany(
        "INSERT INTO trades (datum,tijd_entry,richting,resultaat_eur,charges,grade,"
        "fase,status,foutcodes,notities) VALUES (?,?,?,?,?,?,?,?,?,?)", rijen)
    conn.commit()
    conn.close()


def test_weekcijfers():
    fd, pad = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _maak_db(pad)
        conn = sqlite3.connect(pad)
        wc = wr.haal_week(conn, "2026-09-15", "2026-09-19")
        conn.close()

        assert wc.n == 5, f"verwacht 5 genomen trades, kreeg {wc.n}"   # no-trade + vorige week eruit
        assert wc.wins == 2 and wc.verlies == 3
        assert abs(wc.winrate - 0.4) < 1e-9
        netto = round(wc.pnl, 2)
        assert netto == round(-8.62-0.46 + 3.47-0.06 + 2.26-0.06 - 7.72-0.10 - 4.38-0.10, 2), netto
        assert wc.grades["A"] == 1 and wc.grades["C"] == 4
        assert abs(wc.valide_ratio - 1/5) < 1e-9
        assert wc.beste["datum"] == "2026-09-15" and wc.beste["grade"] == "A"
        assert wc.grootste_fout == "E9" and wc.fout_telling["E9"] == 3
        print(f"  cijfers OK: {wc.n} trades, netto {netto:+.2f}, winrate {wc.winrate*100:.0f}%, "
              f"grootste fout {wc.grootste_fout}")

        # narratief zonder API-sleutel -> feitelijke fallback, geen crash
        os.environ.pop("ANTHROPIC_API_KEY", None)
        verhaal = wr.narratief(wc, {"gebruik": True})
        assert "trades" in verhaal and "winrate" in verhaal

        # de nieuwe mail: drie getallen met trend t.o.v. vorige week
        conn = sqlite3.connect(pad)
        drie = wr.drie_getallen(conn, "2026-09-15", "2026-09-19")
        conn.close()
        assert drie["nu"]["kansen"] == 5          # 5 genomen, geen 'bewust gelaten'
        html = wr.bouw_html(wc, verhaal, drie)
        for moet in ("Schone trades", "Gemiddelde R", "Kansen", "Weekbespreking",
                     "Foutcodes", "De trades"):
            assert moet in html, moet
        assert "Winrate" not in html            # bewust weg: stuurt niet aan
        assert "t.o.v. vorige week" in html or "geen vergelijking" in html
        assert html.count("short") + html.count("long") >= 5
        print("  drie getallen + trend + html-bouw OK (kansen=%d)" % drie["nu"]["kansen"])
    finally:
        os.remove(pad)


def test_lege_week():
    fd, pad = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _maak_db(pad)
        conn = sqlite3.connect(pad)
        wc = wr.haal_week(conn, "2026-10-01", "2026-10-05")  # geen trades
        conn.close()
        assert wc.n == 0 and wc.winrate is None
        html = wr.bouw_html(wc, wr.narratief(wc, {"gebruik": False}), None)
        assert "Geen trades" in html
        print("  lege week geeft nette mail OK")
    finally:
        os.remove(pad)


if __name__ == "__main__":
    test_weekcijfers()
    test_lege_week()
    print("alle week_review-tests geslaagd")
