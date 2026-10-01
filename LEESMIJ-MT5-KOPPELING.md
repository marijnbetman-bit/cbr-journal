# MT5-koppeling — je trades vanzelf in de journal

Zolang de journal op je laptop draait, kijkt hij elke 30 seconden in de
MetaTrader 5 die ernaast open staat. Elke gesloten goud-trade komt er
vanzelf in: tijden (Amsterdams), richting, lot, entry/exit/SL/TP,
resultaat en charges zoals de broker ze boekte, RR, R, MFE/MAE en een chart
met je in- en uitstapmoment. **Alleen lezen — er wordt nooit een order geplaatst.**

Je hoeft dus geen `/trade` meer te sturen. Het enige wat jij nog doet: je
**5 checks + 5 CBR-criteria** tikken. Venster en dagmaximum vult de journal
zelf in (feiten), dus in de praktijk tik je er 8.

## Eenmalig instellen (±5 minuten)

1. **Sluit de journal** als hij open staat (venster dicht).
2. **Open MetaTrader 5 op je laptop** en log in bij Vantage. Je mag op
   hetzelfde account ingelogd zijn als de VPS; dat kan tegelijk.
3. **Dubbelklik `START-JOURNAL.bat`.** Die installeert één keer het
   MetaTrader-pakket (even geduld).
4. **Kijk rechtsboven in de journal:** het lampje `MT5` is groen. Twijfel?
   Dubbelklik `MT5-CHECK.bat` — die laat zien wat hij ziet, en verandert niets.
5. **Telegram (aanrader):** dubbelklik `TELEGRAM-BOT-INSTELLEN.bat` en volg
   de 4 stappen. Dit wordt een *tweede* bot naast @CBR_signals_bot.
6. **Laptop de hele dag aan?** Dubbelklik `AUTOSTART-AAN.bat`. Dan start de
   journal vanzelf (geminimaliseerd) als je inlogt, en start hij MT5 mee.

## Dagelijks

- Trade gesloten → binnen ±30 sec een Telegram-bericht met tien knoppen.
  Tik ze af; de grade staat meteen in het bericht. **Antwoord** op het
  bericht met tekst = notitie bij die trade.
- Liever op de laptop? Menu **Loggen → Beoordelen** (of sneltoets `o`).
- Telegram-commando's: `/open` (wat nog wacht), `/vandaag`, `/help`.

## Hoe de grade nu werkt

Je 5 CBR-criteria bepalen de grade, net als altijd (`kritisch nee → C`).
Nieuw: de drie kwaliteitscriteria worden afgeleid, zodat een **A** via
Telegram haalbaar is:
entry op 50% = je check "entry op de 50%", SL op het extreme = je check
"SL 5+ pts voorbij de sweep", TP = RR ≥ 1,0.

## Exporteren

Menu **Meer → Exporteren**:
- **Journal als los bestand (HTML)** — alles erin, opent op elk apparaat
  zonder dat de journal draait. Zet 'm in OneDrive, dan heb je 'm op je telefoon.
- **Trades voor Excel (CSV)** — opent direct goed in Nederlandse Excel.

## Goed om te weten

- Trades van vóór 22 sep blijven zoals ze zijn (`"sync_vanaf"` in
  `journal_config.json`).
- Logde je een trade al zelf? Dan wordt hij **gekoppeld** en aangevuld met
  de brokercijfers, niet dubbel toegevoegd. Jouw notities blijven staan.
- Verwijder je een automatische trade, dan komt hij niet terug.
- De serverklok wordt automatisch bepaald; zomer-/wintertijd gaat vanzelf.
- Logboek bij problemen: `mt5_koppeling.log` in deze map.
- `journal_config.json` bevat nu je bot-token. De sync naar de VPS slaat
  dit bestand al over; stuur het nooit door.

## Telefoon

Thuis op wifi: `http://<ip-van-je-laptop>:8010` (Windows vraagt de eerste keer
of Python op het privénetwerk mag — kies Toestaan). Buiten de deur: de
Telegram-bot doet het overal, en de HTML-export in OneDrive ook.
