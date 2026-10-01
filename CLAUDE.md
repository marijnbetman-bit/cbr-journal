# CBR Journal

Daytrading-journal voor Marijn (XAUUSD, CBR-model), FastAPI + SQLite + vanilla JS. Draait op de VPS (`START-JOURNAL.bat`, poort 8010). Deze map is de meesterkopie van de CODE; de VPS heeft eigen data en config.
Hoort bij CBR Station (`C:\Dev\cbr-station`, zie daar CLAUDE.md). Het station leest `cbr_journal.db` alleen-lezen.

## Werkafspraken
- Nederlands, concreet. Marijn is geen programmeur: Windows-stappen met exacte commando's.
- Noem onduidelijkheden eerst. Eerlijk over wat data bewijst.
- Updates naar de VPS als zip met alleen code (`VPS-UPDATE-N-naam.zip` + `LEES-MIJ-UPDATE-N.txt`). NOOIT `cbr_journal.db`, `signalen.db`, `journal_config.json`, screenshots of andere data overschrijven; configwijzigingen via een klein script dat alleen de nodige sleutels zet (met backup).
- Geen sleutels/tokens in code of chat (staan in journal_config.json op de machine zelf; niet uitlezen).
- Laatste updates: 4 (donker thema + signaaloordeel), 5 (venster blokken via venster.py), 6 (detector-knoppen). Nog niet allemaal op de VPS.

## Structuur
- `app/main.py` (FastAPI), `app/*.py` (stats, fouten, proces, watals, cbr, ...), `static/` (html/js/css), modules in de hoofdmap (signalen.py, setup_detector.py, mt5_koppeling.py, journal_bot.py, beoordelen.py, venster.py), elk ingehaakt in app/main.py met try/except.
- `journal_config.json` = bron van waarheid voor venster (lijst blokken, Amsterdamse tijd), handelsdagen, mt5, telegram, signalen (detector-instellingen, elke ronde herlezen).
- `mt5_koppeling.py` leest MT5 alleen-lezen (nooit handelen) en zet gesloten XAU-trades in het journal. `terminal_pad` in de config kiest de terminal.

## Open taak (eerst)
Account-controle in mt5_koppeling.py: straks staan er twee MT5-terminals op de VPS (live handmatig + Vantage-demo voor het station). Nu valt `verbind()` terug op "de MT5 die openstaat" als terminal_pad niet werkt; dan kan het journal demo-trades als live loggen. Gewenst: config `mt5.account_login` (verwacht live-accountnummer); bij een ander ingelogd account niets loggen + duidelijke melding (log + Telegram via de bestaande bot); geen terugval naar een andere terminal als terminal_pad gezet is. Zonder account_login: huidig gedrag + waarschuwing.
