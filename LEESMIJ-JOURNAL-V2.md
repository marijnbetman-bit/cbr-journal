# CBR Journal v2 — één geheel (29 sep 2026)

## Wat er veranderd is
- **Homepage = de journal.** Saldo (gelijk aan MT5), *Nog te loggen*, vandaag/week/maand,
  per uur / per sessie / weekdag×uur, R-verdeling, MFE/MAE, rollende expectancy, duur,
  proces tegen uitkomst, wat je liet liggen, discipline, kalender, maanden, recente trades.
- **Eruit:** /hoe-sta-ik-ervoor, /prestaties, /watals, /beoordelen (sturen door naar /).
- **Loggen** = op de homepage (of Telegram-knoppen): 6 setup-punten van het bias-vrije model
  (bepalen de grade), 4 discipline-punten (automatisch uit MT5), emotie vooraf (verplicht),
  uitvoering 1–5, opnieuw nemen?, fouttags, les. Proces-score = % goed.
- **Saldo:** tabel `kasstromen` (storting/opname/correctie/aansluiting). ⚙ Saldo op de homepage.
  Met `mt5.saldo_volgen: true` (standaard) leest de koppeling je MT5-balans, boekt stortingen
  automatisch en zet het verschil per dag als "MT5-aansluiting". Rendement = alleen trading.

## Data voor later (AI / automatiseren)
- `marktdata.db` — elke XAU-minuutcandle (OHLC, tick-volume, spread), UTC + NL-tijd.
- `mt5_account_log` — balans/equity/margin; `mt5_positie_events` — SL/TP-tijdlijn per positie.
- Trade-kolommen: sessie_markt, atr_m1, spread_entry, vorige_1h_high/low.
- `/export/dataset.csv` — gelabelde dataset (feiten + context + jouw oordeel).

## VPS
Alles blijft in deze map. Mee verhuizen: code + `cbr_journal.db` + `marktdata.db` +
`journal_config.json`. Migraties draaien vanzelf bij de start. Back-ups: `*.bak-voor-v2-20260929`.
