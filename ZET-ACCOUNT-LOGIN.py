# -*- coding: utf-8 -*-
"""Zet mt5 > account_login in journal_config.json (maakt eerst een backup).
Alleen deze ene sleutel verandert; de rest van je config blijft zoals hij is."""
import json, os, shutil, time
pad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal_config.json")
if not os.path.exists(pad):
    print("journal_config.json niet gevonden in deze map. Staat dit bestand in de journal-map?")
    raise SystemExit(1)
d = json.load(open(pad, encoding="utf-8"))
mt5 = d.get("mt5") or {}
if mt5.get("account_login"):
    print(f"Nu ingesteld: {mt5['account_login']}")
print("Typ het nummer van je LIVE-account (staat in MT5 links bij Navigator > Accounts).")
print("Leeg laten + Enter = accountcontrole uitzetten.")
nr = input("Live-accountnummer: ").strip()
if nr and not nr.isdigit():
    print("Dat is geen nummer (alleen cijfers). Er is niets veranderd.")
    raise SystemExit(1)
shutil.copy2(pad, pad + ".bak-voor-accountcontrole-" + time.strftime("%Y%m%d-%H%M%S"))
mt5["account_login"] = int(nr) if nr else ""
d["mt5"] = mt5
json.dump(d, open(pad, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
if nr:
    print(f"Klaar. De journal logt alleen nog trades van account {nr}. Backup staat naast het bestand.")
else:
    print("Klaar. Accountcontrole staat uit. Backup staat naast het bestand.")
print("Herstart nu START-JOURNAL.bat.")
