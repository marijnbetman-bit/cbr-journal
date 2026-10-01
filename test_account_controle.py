# -*- coding: utf-8 -*-
"""
Test voor de account-controle in mt5_koppeling.py (update 7). Draait zonder MT5:
    python test_account_controle.py
Werkt op een kopie van cbr_journal.db in een tijdelijke map; log en marktdata
worden omgeleid, dus er verandert niets aan je echte bestanden.
"""
import os, shutil, sqlite3, sys, tempfile, types
from types import SimpleNamespace as NS

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)
sys.modules["marktdata"] = types.SimpleNamespace(          # niet in de echte marktdata.db
    verzamel_candles=lambda *a, **k: 0, verrijk_trades=lambda *a, **k: 0,
    log_positie=lambda *a, **k: None)
import mt5_koppeling as mk
from test_mt5_koppeling import NepMT5

LIVE, DEMO = 12345678, 99999999


class Nep(NepMT5):
    def __init__(self, login=LIVE, pad_werkt=True):
        super().__init__()
        self.login = login
        self.pad_werkt = pad_werkt
        self.init_aanroepen = []

    def initialize(self, *a):
        self.init_aanroepen.append(a)
        return self.pad_werkt if a else True

    def account_info(self):
        return NS(login=self.login, server="Vantage", currency="EUR", balance=None)


def tellingen(db):
    con = sqlite3.connect(db)
    try:
        tabellen = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tabellen}
    finally:
        con.close()


def main():
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "cbr_journal.db")
    shutil.copy(os.path.join(HIER, "cbr_journal.db"), db)
    mk.SCREENSHOTS_DIR = os.path.join(tmp, "screenshots")
    mk.LOG_PAD = os.path.join(tmp, "mt5_koppeling.log")
    fouten = []

    def check(cond, tekst):
        print(("  OK   " if cond else "  FOUT ") + tekst)
        if not cond:
            fouten.append(tekst)

    def ronde(k, cfg):
        try:
            return k.ronde(cfg), None
        except mk.VerbindFout as e:
            k.verbreek()                       # zoals loop() doet
            return None, e

    basis = dict(mk.STANDAARD, sync_vanaf="2026-09-22")

    print("1. verkeerd account vanaf de start")
    nep = Nep(login=DEMO)
    k = mk.Koppeling(mt5=nep, db_pad=db)
    meldingen = []
    k.bij_waarschuwing.append(meldingen.append)
    cfg = dict(basis, account_login=LIVE)
    voor = tellingen(db)
    _, fout = ronde(k, cfg)
    check(isinstance(fout, mk.AccountFout), f"ronde stopt met AccountFout ({fout})")
    check(tellingen(db) == voor, "niets in de database veranderd (trades, saldo, posities, ...)")
    check(len(meldingen) == 1 and "VERKEERD" in meldingen[0], "één waarschuwing verstuurd")
    check("999" in str(fout) and "678" in str(fout), "melding noemt verwacht en ingelogd (laatste 3 cijfers)")
    check(str(DEMO) not in str(fout) and str(LIVE) not in str(fout), "volledige accountnummers niet in de melding")
    ronde(k, cfg)
    check(len(meldingen) == 1, "tweede ronde: geen tweede waarschuwing")
    check(tellingen(db) == voor, "tweede ronde: nog steeds niets veranderd")

    print("2. weer ingelogd op live")
    nep.login = LIVE
    nieuw, fout = ronde(k, cfg)
    check(fout is None, f"ronde loopt weer ({fout})")
    check(len(meldingen) == 2 and "weer goed" in meldingen[1], "bericht 'weer goed' verstuurd")
    check(tellingen(db) != voor, "nu wordt er wel gelogd")
    check(k.status.get("account_controle") == "aan: juiste account", "status: juiste account")

    print("3. tijdens het draaien gewisseld naar demo")
    voor = tellingen(db)
    nep.login = DEMO
    check(k.verbonden, "(was verbonden)")
    _, fout = ronde(k, cfg)
    check(isinstance(fout, mk.AccountFout), "wissel wordt in de volgende ronde opgemerkt")
    check(tellingen(db) == voor, "niets in de database veranderd")
    check(len(meldingen) == 3, "nieuwe waarschuwing")

    print("4. terminal_pad gezet maar werkt niet: geen terugval")
    nep2 = Nep(login=LIVE, pad_werkt=False)
    k2 = mk.Koppeling(mt5=nep2, db_pad=db)
    _, fout = ronde(k2, dict(basis, account_login=LIVE, terminal_pad=r"C:\Nergens\terminal64.exe"))
    check(fout is not None and "terminal_pad werkt niet" in str(fout), f"duidelijke fout ({fout})")
    check(nep2.init_aanroepen == [(r"C:\Nergens\terminal64.exe",)],
          f"alleen met het pad geprobeerd, niet 'de MT5 die openstaat' ({nep2.init_aanroepen})")

    print("5. zonder account_login: zoals vroeger, met waarschuwing")
    k3 = mk.Koppeling(mt5=Nep(login=DEMO), db_pad=db)
    _, fout = ronde(k3, dict(basis))
    check(fout is None, "ronde loopt")
    check("niet ingesteld" in (k3.status.get("account_controle") or ""), "status meldt: controle staat uit")

    print("6. account_login als tekst of als 12345678.0 werkt ook")
    for waarde in (str(LIVE), float(LIVE), f" {LIVE} "):
        k4 = mk.Koppeling(mt5=Nep(login=LIVE), db_pad=db)
        _, fout = ronde(k4, dict(basis, account_login=waarde))
        check(fout is None, f"account_login={waarde!r} geaccepteerd")

    print("\nALLES GOED" if not fouten else f"\n{len(fouten)} FOUT(EN)")
    return 1 if fouten else 0


if __name__ == "__main__":
    sys.exit(main())
