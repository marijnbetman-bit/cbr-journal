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
- `structuur_detector.py` (plan v3, fase 1, 7 okt 2026; plan in `C:\CBR-Data\rapporten\PLAN-V3-LEREN-VAN-MARIJN.md`): de CBR-setup zoals Marijn hem traded (sweep van de high van 1-10 min geleden, expansie 4-90 candles, BOS type 3 op een wick, entry = midden van sweep en BOS-been, SL 1 point). Pure functies `kandidaten(bars)` en `simuleer(bars, k, tp, doorlopend)`. Wordt door het station gelezen (`structuur.py`, LEERLING v2); het journal gebruikt hem (nog) niet. `setup_detector.py` blijft ongewijzigd. Test `test_structuur_detector.py`. Heeft een eigen terugval voor Europe/Amsterdam (de journal-venv had geen tzdata).
- `v3_labels.py` (plan v3, fase 2): v3 op de live candles elke MT5-ronde (na_ronde), één Telegram-bericht per sweep binnen het venster met PNG-grafiekje en knoppen A/B/C/nee/niet gezien (callback 'v:'); bij elke nieuwe trade TP-type + expansie-begin (voorstel uit de eerste SL/TP in `mt5_positie_events`, knoppen 't:', reply met prijs). Tabellen `v3_labels`, `v3_berichten`; kolommen tp_type, tp_type_bron, expansie_begin, expansie_bron, sl_start, tp_start, v3_sleutel in trades. Config `journal_config.json > v3_labels` (aan, stil, stil_tussen, venster, chart). Bot: /v3, /tptype. Test `test_v3_labels.py` (kopie van de db, Telegram nagebootst).
