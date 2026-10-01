# -*- coding: utf-8 -*-
"""Zet het nieuwe handelsvenster in journal_config.json (maakt eerst een backup)."""
import json, os, shutil, time
pad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal_config.json")
shutil.copy2(pad, pad + ".bak-voor-asia-" + time.strftime("%Y%m%d-%H%M%S"))
d = json.load(open(pad, encoding="utf-8"))
d["venster"] = [["01:00", "09:00"], ["10:00", "15:00"]]
d["venster_van"] = "01:00"      # omhullende voor oude code
d["venster_tot"] = "15:00"
d["_venster_uitleg"] = "Handelsvenster = lijst met blokken in Amsterdamse tijd (vast, ook in de winter). 09:00-10:00 is dicht."
json.dump(d, open(pad, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("Klaar. Venster is nu 01:00-09:00 en 10:00-15:00. Backup staat naast het bestand.")
