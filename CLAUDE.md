# CBR Journal

Daytrading-journal voor Marijn (XAUUSD, CBR-model), FastAPI + SQLite + vanilla JS. Draait op de VPS (`START-JOURNAL.bat`, poort 8010). Deze map is de meesterkopie van de CODE; de VPS heeft eigen data en config.
Hoort bij CBR Station (`C:\Dev\cbr-station`, zie daar CLAUDE.md). Het station leest `cbr_journal.db` alleen-lezen.

## Werkafspraken
- Nederlands, concreet. Marijn is geen programmeur: Windows-stappen met exacte commando's.
- Noem onduidelijkheden eerst. Eerlijk over wat data bewijst.
- **Werkwijze nu (vanaf 1 okt 2026, VPS wordt opnieuw geïnstalleerd):** geen update-zips of LEES-MIJ-UPDATE-bestanden meer. Na elke wijziging die werkt: meteen committen hier, daarna de code kopiëren naar `C:\Users\marij\OneDrive\Afbeeldingen\AI AGENTS\journal` met `git archive HEAD | tar -x -C "/c/Users/marij/OneDrive/Afbeeldingen/AI AGENTS/journal"` (alleen getrackte code, geen data). Nooit los in `AI AGENTS` zelf zetten: dat is de map van het station (main.py, venster.py en CLAUDE.md bestaan daar ook).
- Later, als de VPS weer bijgewerkt wordt: updates als zip met alleen code (`VPS-UPDATE-N-naam.zip` + `LEES-MIJ-UPDATE-N.txt`). NOOIT `cbr_journal.db`, `signalen.db`, `journal_config.json`, screenshots of andere data overschrijven; configwijzigingen via een klein script dat alleen de nodige sleutels zet (met backup).
- Geen sleutels/tokens in code of chat (staan in journal_config.json op de machine zelf; niet uitlezen).
- Laatste updates: 4 (donker thema + signaaloordeel), 5 (venster blokken via venster.py), 6 (detector-knoppen), 7 (account-controle MT5). Nog niet allemaal op de VPS.

## Structuur
- `app/main.py` (FastAPI), `app/*.py` (stats, fouten, proces, watals, cbr, ...), `static/` (html/js/css), modules in de hoofdmap (signalen.py, setup_detector.py, mt5_koppeling.py, journal_bot.py, beoordelen.py, venster.py), elk ingehaakt in app/main.py met try/except.
- `journal_config.json` = bron van waarheid voor venster (lijst blokken, Amsterdamse tijd), handelsdagen, mt5, telegram, signalen (detector-instellingen, elke ronde herlezen).
- `mt5_koppeling.py` leest MT5 alleen-lezen (nooit handelen) en zet gesloten XAU-trades in het journal. `terminal_pad` in de config kiest de terminal.

## Account-controle MT5 (update 7, klaar)
`mt5.account_login` = verwacht live-account. `Koppeling.controleer_account()` draait bij verbinden en elke ronde; ander account -> `AccountFout`, niets gelogd (ook geen saldo/marktdata/signalen), één melding via `bij_waarschuwing` -> `journal_bot.meld_tekst`. `terminal_pad` gezet = geen terugval. Zonder account_login: oud gedrag + waarschuwing. Tests: `test_account_controle.py`.
Let op: `test_mt5_koppeling.py` gaf al 6 fouten vóór update 7 (verwacht dat #35/#36 in de lokale db nog niet gekoppeld zijn).
