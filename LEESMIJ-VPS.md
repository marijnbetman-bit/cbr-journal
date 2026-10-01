# Journal naar de VPS (v2.1, 29 sep 2026)

Vanaf nu is de **VPS de journal**: hij draait 24/7, ziet elke trade (ook van je telefoon)
terwijl hij openstaat — dus SL/TP worden altijd gezien — en de Telegram-bot meldt meteen.
De laptop wordt alleen nog de plek waar je code aanpast.

## Stappen
1. **Laptop** — sluit het journal-venster. Dubbelklik `MAAK-VPS-PAKKET.bat`.
   Er komt `CBR-journal-VPS-<datum>.zip` op je bureaublad (code + database + marktdata + charts).
2. **VPS** (Extern bureaublad) — plak de zip, bv. in `C:\CBR\`.
   Staat daar al een oude journal-map? Hernoem die naar `journal-oud` (niet weggooien).
   Pak de zip uit zodat je `C:\CBR\journal\app\main.py` hebt.
3. **VPS** — MT5 van Vantage open en ingelogd op je account (…040).
   Draait er ook een MT5 voor de signal copier? Dan gewoon een tweede MT5 ernaast;
   het installatiescript vraagt welke bij de journal hoort.
4. **VPS** — dubbelklik `INSTALLEER-OP-VPS.bat` (wachtwoord, MT5 kiezen, pakketten, autostart).
5. **VPS** — dubbelklik `START-JOURNAL.bat`. In Telegram: `/status` → "MT5: verbonden".
6. **Laptop** — dubbelklik `AUTOSTART-UIT.bat` en start de journal daar niet meer.
   (Twee journals = twee bots op hetzelfde token = Telegram-conflict + twee databases.)

## Later code aanpassen
Code wijzigen op de laptop → alleen de gewijzigde **code**bestanden naar de VPS kopiëren
(`app/`, `static/`, `*.py`) en de journal op de VPS herstarten.
**Nooit** `cbr_journal.db`, `marktdata.db`, `journal_config.json` of `screenshots/` van de
laptop over de VPS heen zetten — de VPS heeft vanaf nu de echte data.

## De journal openen
- Op de VPS zelf: http://localhost:8010
- Vanaf laptop/telefoon: nette oplossing is een Cloudflare Tunnel (volgende stap).
  Tot die tijd: via Extern bureaublad, en loggen gaat gewoon via Telegram.
