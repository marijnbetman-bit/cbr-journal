# Signalen in de journal (23 sep 2026)

Sinds vandaag is er **één programma en één bot**. De journal leest elke 15
seconden MetaTrader 5 en zoekt daarbij ook je setup. Alles gaat via de
journal-bot in Telegram. De oude signaalwachter (map `signaalwachter`) en
@CBR_signals_bot worden niet meer gebruikt.

## Het model dat de bot zoekt (setup_detector.py)

1. **Impuls**: alleen de impuls zelf. Minstens 4 candles, minstens 4× de
   gemiddelde candle (ATR), hoogstens 45% overlap, efficiëntie ≥ 0,6.
   De impuls moet bovendien de **high/low van de vorige 1H-candle breken**:
   staat de high van 8-9u op 250, dan moet een impuls in het uur 9-10u die 250
   breken, anders geen valide setup. Uit te zetten met `eis_1h_break` in
   journal_config.json.
2. **Top + mini-pullback**: het uiterste van de impuls, daarna een terugval.
3. **Sweep**: prijs tikt voorbij die top (wick is genoeg), binnen 10 minuten
   na de top en hoogstens 30 points erdoor. Verder dan 30 = nieuwe impuls.
4. **BOS**: een candle SLUIT voorbij de low (high) van de mini-pullback.
5. **Entry**: 50% tussen het sweep-extreme en de low (high) van de mini-pullback.
6. **SL** 5 points voorbij het sweep-extreme, **TP** altijd 1:1.
7. **Ongeldig**: raakt prijs de 50% van de impuls vóór de entry, dan is de impuls weg.

Na een impuls omhoog zoekt hij een short, na een impuls omlaag een long.
Geen bias, geen DXY.

Twee eigen aannames (in te stellen in `journal_config.json` → `"signalen"`):
de BOS moet binnen 15 min na de sweep komen (`bos_max_candles`), en de entry
blijft 30 min na de BOS geldig (`entry_max_candles`). Ook vervalt een setup
als het TP-niveau al geraakt wordt voordat de entry er is.

## Wat je in Telegram krijgt

- 🟡 **Impuls**: ik zoek de sweep.
- 🟠 **Klaar**: entry, SL en TP staan vast, met knoppen *Genomen* / *Niet genomen*.
- 🟢 **Entry geraakt**.
- 🎯 / 🛑 TP of SL, en ⚪ vervallen met de reden. Deze drie komen zonder geluid.

Neem je de trade in MT5, dan koppelt de journal hem zelf aan het signaal
(zelfde richting, binnen 60 min na de BOS, entry binnen 20 points).

## Commando's

`/status` · `/signalen` · `/log` (of `/log 40`) · `/replay 2026-09-22` ·
`/open` · `/vandaag` · `/test` · `/help`

## Log

`logs/signalen_JJJJ-MM-DD.log`: alleen regels die iets nieuws zeggen. Als er
niets gebeurt, hoogstens elke 5 minuten één regel met de sterkste beweging en
waarom die (nog) geen impuls is.


## Oordeel per signaal + dataset (1 okt 2026)
Onder elk 'klaar'-signaal in Telegram staan vier knoppen: **Genomen · Niet genomen · Gemist: wel · Gemist: niet**
('gemist' = je zag het niet op tijd; wel/niet = had je het genomen als je had gekeken). Een reply op het
signaalbericht wordt als **opmerking** bij dat signaal bewaard. Neem je de trade in MT5, dan koppelt de journal
hem zelf en staat het oordeel op 'genomen'. Een signaal waarvan de entry nooit geraakt werd, krijgt geen
oordeel-knoppen meer (er valt niets te beoordelen).

De journal rekent zelf uit wat elk klaar-signaal zou zijn geworden (TP, SL, nooit gevuld). Alles staat op de pagina
**/signalen** (menu Leren): chart per signaal in dezelfde stijl als je trades, oordeel en opmerking ook daar aan
te passen, en de statistiek 'jouw oordeel tegenover wat er gebeurde'. De dataset is te downloaden als CSV
(/export/signalen.csv): kenmerken van de setup, uitkomst, jouw oordeel en je opmerkingen.
Nieuwe kolommen/tabellen (oordeel, opmerkingen) worden bij de eerste start vanzelf toegevoegd.
