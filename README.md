# CBR Trading Journal

Een **lokaal** daytrading-journal voor het CBR-model (TomTrades).
XAUUSD-only, 2e uur Londense sessie. Volledig losstaand van je aandelen-tracker —
eigen map, eigen database, eigen server. Deelt alleen de stijl en de stack.

**Stack:** FastAPI + SQLite + vanilla JS.

**Thema:** licht en strak, met TradingView als maatstaf. Witte panelen op een lichtgrijze
ondergrond, dunne grijze lijnen in plaats van dozen, kleine radii (3–4 px), compacte typografie
(13 px) en geen schaduwen of verlopen. Elke kleur heeft twee tinten: een donkere voor tekst
(contrast ≥ 4,7 op wit) en de heldere TradingView-tint voor grafiekmarkeringen. Alles staat als
CSS-variabelen in de kop van `static/style.css`; de grafieken lezen ze daaruit, dus je past het
thema op één plek aan.

## Starten (Windows)

Dubbelklik **`START-JOURNAL.bat`**. De eerste keer zet hij meteen een snelkoppeling
**CBR Journal** op je bureaublad — daarna start je de journal gewoon vanaf je bureaublad
en hoef je nooit meer door mappen te zoeken. (Werkt de snelkoppeling niet? Dubbelklik
`SNELKOPPELING-op-bureaublad.bat`.)

De starter:

1. maakt bij de eerste keer een virtuele omgeving aan en installeert de dependencies;
2. start de lokale server (uvicorn);
3. opent automatisch `http://localhost:8010` in je browser.

> Deze journal heeft bewust **niet** `start.bat` — die naam is van je stock tracker.
> De journal draait op **poort 8010** omdat je aandelen-tracker poort 8000 gebruikt.
> Een andere poort nodig? Pas `set PORT=...` bovenin `start-cbr-journal.bat` aan.

Sluit het zwarte venster om de server te stoppen.

## Wat er nu in zit

**Snel een trade toevoegen (+ Trade)**
- **`/nieuw`** is het eenvoudige formulier: datum, richting, de vijf regels als klikbare knoppen
  (**goed / twijfel / niet**), resultaat en kosten, screenshot slepen, en één of twee zinnen
  omschrijving. Meer niet. Niets zit op slot; je kunt in elke volgorde invullen.
- De grade verschijnt live bovenaan zodra je de regels aanklikt.
- De **⋯**-knop ernaast opent het uitgebreide formulier (foutcodes, zekerheid, MAE/MFE,
  planmodus, entry/SL/TP). Daar zit het uitkomstpaneel wél op slot tot je de checklist hebt
  ingevuld — dat is bewust, maar het hoeft je nooit in de weg te zitten.

**Trading log (📒 Log)**
- Eén **map per handelsdag**, met de datum, het netto resultaat, de grades, een thumbnail van je
  eerste screenshot en of je die dag hebt afgesloten.
- Klik een map open en je ziet **alle trades van die dag** onder elkaar: tijd, richting, RR,
  netto, de vijf criteria als vinkjes, je omschrijving en je screenshots (klikbaar voor groot).
  Plus je dagreview als je die hebt ingevuld.
- Bovenin de totalen over alles: handelsdagen, trades, netto, netto R en perfecte trades.

**Fase 1 — journallen**
- **Database** met drie tabellen: `trades`, `no_trades`, `screenshots` (+ `settings`).
- **Trade toevoegen/bewerken** met de CBR-checklist en een **live meeveranderende grade**.
  Zodra een kritisch criterium ✗ of ? wordt, verschijnt de rode markering *"dit was geen trade"*.
- **Dagoverzicht** (landingspagina): kies een datum → alle trades en no-trades als kaarten,
  met grade-badge, resultaat, de drie kritische criteria als icoontjes, thumbnail en dagsamenvatting.
- **No-trades** vastleggen (bewust weggebleven = net zo waardevol).

**Fase 2 — screenshots**
- **Drag-and-drop** upload in het trade- én no-trade-formulier. Sleep afbeeldingen erin,
  typ een beschrijving, kies het type (pre-entry / entry / post-exit). Opslag in
  `screenshots/<datum>/`, alleen het pad in de database.

**Fase 3 — dashboard (📊 knop bovenin)**
- **MetaTrader-achtige account-bar**: balance, netto P/L, winrate, ★ perfecte trades, valide %, totaal R.
- **"🏆 Wat ging goed"**: beloont perfecte setups, valide setups, beste trade, bewuste no-trades,
  groene dagen — plus badges die je unlockt.
- **Veel grafieken**: spaarverloop (equity €, met instelbaar startkapitaal), equity in R,
  cumulatieve kosten, resultaat per trade, netto per dag, winrate valide vs. C, grade-verdeling,
  foutfrequentie en criterium-kwaliteit (welk criterium chronisch ? krijgt).
- **Trade-historie** als MT-stijl tabel. Filter op Alles / Deze week / Deze maand.

**Fase 4 — foutenanalyse (⚠ Fouten)**
- **Patroon-detectie**: komt een foutcode **3× binnen 10 opeenvolgende trades** terug, dan is het
  geen incident maar een patroon. Die krijgt een eigen rode kaart mét de corrigerende regel.
- **Trend**: fouten per trade over tijd, plus een banner die zegt of je in je laatste 10 trades
  minder fouten maakt dan daarvoor.
- **Per categorie** (E/R/M/P/D) zie je waar je zwakke plek zit.
- **Alle foutcodes** in één tabel met aantal, laatste voorkomen en de corrigerende regel.

**Fase 5 — heb ik een edge? (op het dashboard)**
- **Expectancy in R** met beoordelingsband (>+0,5R uitstekend · +0,3–0,5R solide · +0,15–0,3R
  marginaal · <0 stoppen). Kosten zitten in de berekening.
- **Profit factor**, gemiddelde winst en verlies in R, **max drawdown** en hersteltijd.
- **Welk criterium levert je geld op**: per criterium de expectancy mét ✓ tegenover zonder ✓,
  en het verschil. Dit kan alleen omdat je één vaste checklist hebt.
- **Lichte MAE/MFE**: twee klikken na afloop (hoe dicht bij je SL, hoe liep je TP) met
  automatische signalen als je stop structureel te krap staat of je TP te vroeg is.
- **Betrouwbaarheidsmelding**: onder 20 trades is alles ruis, vanaf 100 mag je oordelen.

**Fase 6 — de journal als poortwachter**
- **Checklist-slot**: het uitkomstpaneel zit op slot tot je alle vijf criteria hebt beoordeeld.
  Zodra je het bedrag ziet, kleurt dat je oordeel over de setup — dus eerst graden, dan invullen.
- **Planmodus** (◎ Plan trade): vul de checklist in *vóór* je entry. Je krijgt meteen
  "✓ Mag je nemen" of "✕ Niet nemen". Het plan komt als kaart op je dagoverzicht met twee knoppen:
  *ik heb 'm genomen* of *toch weggebleven*.
  Een C-plan dat je tóch neemt krijgt automatisch **E5** (C-setup geforceerd).
  Een overgeslagen setup telt als **discipline-winst** in het beloningspaneel.
- **Zekerheid 1–5** bij de entry, om later te zien of je onderbuik gekalibreerd is.
- **Balans-check**: vul in wat je broker écht laat zien. Wijkt de journal af, dan waarschuwt het
  dashboard — meestal een trade die je vergeten bent te loggen.

**Fase 10.2–10.4 — wanneer ben ik goed? (op het dashboard)**
- **Welk kwartier van het uur betaalt.** Je handelt één uur per dag; binnen dat uur zitten vier
  kwartieren. Je eigen regel zegt: zoek entries pas na ongeveer twintig minuten in de hourly candle.
  Deze grafiek zegt of dat klopt. Bakken met minder dan tien trades worden doorzichtig getekend —
  zichtbaar, maar niet als feit.
- **Weekdag**: expectancy per dag van de week, met dezelfde eerlijkheidsregel.
- **Is je onderbuik gekalibreerd?** Je zekerheid 1–5 tegenover wat die trades opleverden. Als je
  vijven slechter presteren dan je drieën, is overtuiging jouw waarschuwingssignaal.
- **Emotie tegenover resultaat**: welke mentale staat je geld kost, uit de chips die je aanklikt.
- **Discipline-meter**: een score per handelsdag, afgeleid uit wat er al in de journal staat —
  geforceerde C-setups, trades boven je dagmaximum, doorgaan na je stoploss-regel,
  psychologie-fouten, ontbrekende screenshots. Bewust overgeslagen setups leveren punten óp.
  De netto-lijn per dag ligt eroverheen: het gat tussen "discipline zakt" en "curve zakt" is
  meestal een paar dagen. Je hoeft er zelf niets voor in te vullen.

**Fase 11.1 — volg ik mijn eigen regels? (op het dashboard)**
- **Regel-adherentie**: het percentage trades waarbij je je eigen regels volgde. De toets is drieledig —
  de checklist was valide (A of B), RR minstens 1, en geen discipline-fout in het foutenblok
  (E4, E5, E7, R1, R3, R4, M2, P1–P4, D4).
- **Bandindeling** met advies: onder 60% *"het systeem klopt niet — snoei je regels terug tot er drie
  overblijven die je wél volgt"*, 60–75% op weg, 75–85% sterk, 85%+ elite-discipline.
- **Regels gevolgd vs. gebroken** naast elkaar: trades, winrate, expectancy, profit factor en netto.
  Dit is het cijfer waar het om gaat — als links beter presteert dan rechts, is discipline geen moraal
  maar rendement.
- **Waarom je ze brak**: je overtredingen op volgorde van hoe vaak ze voorkomen.

**Fase 11.3 — hoe zeker is zeker? (op het dashboard)**
- **Wilson-interval op je winrate**: 80% over vijf trades klinkt mooi, maar je échte winrate ligt
  met 95% zekerheid ergens tussen 38% en 96%. De journal tekent die band en zegt in gewone taal
  wat je eraan hebt (voorlopig: niets, je hebt meer trades nodig).
- **Monte-Carlo**: 10.000 keer je eigen trades opnieuw trekken. Je ziet waar je had kunnen staan
  (p5 / mediaan / p95), hoe groot de kans op een negatieve uitkomst was, en wat de verwachte
  grootste drawdown onderweg is. Plus een vooruitblik over twintig trades — met de expliciete
  waarschuwing dat een kleine, goed gevallen steekproef zijn eigen geluk meeprojecteert.

**Fase 11.4 — regel-changelog (op 📋 Regels)**
- Wijzig je iets aan je model, dan leg je dat vast met een datum. Je krijgt een **verticale streep
  in je equity-curve** op die dag, en een filter **Sinds regelwijziging** bovenin het dashboard.
- Zonder dit vervuilen je oude cijfers je nieuwe model — en dat is precies waarom journals na een
  jaar in de la belanden.

**Fase 11.2 — gemiste setups**
- Een setup overslaan vraagt nu **waarom**. Bij grade C hoeft dat niet (de checklist zei nee); bij een
  A of B krijg je vijf knoppen: de checklist zei nee · twijfel · te laat gezien · buiten het tijdvenster ·
  andere reden.
- Het dashboard splitst ze: **discipline-winst** tegenover **gemiste valide setups**. Op je dagoverzicht
  krijgt een terecht overgeslagen setup een 🛡 en een gemiste een amberkleurige ◌.
- **Geschatte kosten van aarzelen** in R: aantal gemiste valide setups × je expectancy op trades waarbij
  je je regels wél volgde. Nadrukkelijk een schatting — de journal zegt er zelf bij dat we niet weten
  wat die trades hadden gedaan.

**Fase 9 — snelheid (doel: onder 45 seconden per trade)**
- **Kopieer vorige trade**: één knop bovenin het formulier neemt richting, tijd, zekerheid en je
  emotie-chips over van je laatste trade — alles behalve de uitkomst. Instrument, sessie, charges en
  risk worden sowieso al voorgevuld vanaf je vorige trade.
- **Sneltoetsen**: <kbd>1</kbd>–<kbd>5</kbd> kiest een criterium, <kbd>J</kbd> zet ✓, <kbd>T</kbd> zet ?,
  <kbd>N</kbd> zet ✗ — en springt meteen door naar het volgende. <kbd>Ctrl</kbd>+<kbd>S</kbd> slaat op.
  De hele checklist zonder muis.
- **Emotie-chips** in plaats van een tekstveld: rustig · scherp · geduldig · gehaast · twijfelend ·
  overmoedig · revenge · verveeld · moe · afgeleid. Klikken duurt een halve seconde en levert data op
  waar je later op kunt filteren; vrije tekst levert niets op. Het tekstveld blijft staan voor
  wat er niet tussen staat. Ook op **📱 Snel**.
- **Dagregels als vangrail**: stel op het dashboard in hoeveel trades je per dag maximaal neemt en
  na hoeveel verliezers je stopt. Het dagoverzicht toont je stand als een metertje, en als je erover
  heen gaat zegt het formulier het hardop — met de foutcode die erbij hoort (P2 overtrading,
  P1 revenge). Hij blokkeert niets; hij houdt je alleen aan je eigen woord.

**Fase 8 — volume en eigenaarschap**
- **Backtest-modus**: log setups uit het verleden met de bron **Backtest**. Ze tellen mee voor je
  checklist- en foutenstatistiek, maar **niet** voor je portfolio in euro's. Zo kom je sneller richting
  de honderd trades die je nodig hebt voor een echt oordeel. Schakelaar Live / Backtest / Alles staat
  bovenin het dashboard, de kalender en de foutenpagina.
- **Exporteer alles** (knop op het dashboard): een zip met een CSV per tabel — trades, no-trades,
  screenshots, reviews, notities, regelwijzigingen en instellingen (puntkomma-gescheiden, opent
  direct in Excel) — plus al je screenshots. Je data blijft van jou.

**Fase 10.1 — kalender-heatmap (🗓 Kalender)**
- Een **maandrooster** van handelsdagen, gekleurd naar netto R: hoe donkerder groen of rood, hoe groter
  de dag. Een ★ bij een perfecte setup, een 🛡 bij een bewust overgeslagen setup. Klik een dag → dat dagoverzicht.
- Daaronder de **jaarstrook**: twaalf maanden naast elkaar in netto R. Klik een maand om erheen te springen.
- Pijltjes ← en → bladeren door de maanden.

**Fase 13 — overzicht terugwinnen**
- **Dashboard in vier lagen**: *Vandaag* (account-bar, instellingen, back-ups, beloningen, verloop,
  historie) · *Edge* (expectancy, criterium-edge, MAE/MFE, Wilson-interval, Monte-Carlo) ·
  *Discipline* (adherentie, gemiste setups, discipline-meter, winrate en grades) ·
  *Patronen* (kwartier, weekdag, zekerheid, emotie, tags, fouten, criterium-kwaliteit).
- **★ Setup-bibliotheek**: je grade-A (en desgewenst B) setups als beeldgalerij, met de checklist
  erboven en de screenshots eronder. Klik een chart aan voor een grote weergave. Blader hier
  vijf minuten doorheen vóór de sessie.
- **Zoeken over alles** (`/api/zoek`): één query over trades, lessen, notities, reviews,
  foutcodes, tags en regelwijzigingen. Zit in het commandopalet.

**Fase 14 — snelheid**
- **Commandopalet** met <kbd>Ctrl</kbd>+<kbd>K</kbd> vanaf elk scherm. Typ een pagina, een datum
  ("4 sep", "gisteren", "06-09"), of een woord uit een les of notitie — alles in hetzelfde veld.
- **Sneltoetsen overal**: <kbd>N</kbd> nieuwe trade · <kbd>P</kbd> plan · <kbd>D</kbd> dagoverzicht ·
  <kbd>K</kbd> kalender · <kbd>F</kbd> fouten · <kbd>W</kbd> week · <kbd>R</kbd> rapport ·
  <kbd>B</kbd> bibliotheek. Het trade-formulier houdt zijn eigen J/T/N en 1–5.
- **Voorbereidingschecklist** op het dagoverzicht: 1H-levels getekend · agenda gecheckt · risk
  bepaald · dagregels bevestigd · pre-trade plan. Niet af betekent dat D3, R4, P2 en D4 in beeld
  komen, en het telt mee in je discipline-score.
- **Spraaknotitie**: een 🎤-knop bij *Les* en *Notities* (en op 📱 Snel). Spraak wordt in de browser
  zelf omgezet — er gaat niets naar een server.

**Fase 16 — houdbaar bij vijfhonderd trades**
- **Prullenbak**: verwijderen is niet meer definitief. Trades en no-trades blijven 30 dagen staan,
  tellen nergens in mee, en zijn met één klik terug te zetten (🗑 Prullenbak, via het dashboard).
- **Statistiek per laag**: `/api/stats?deel=…` rekent alleen uit wat het geopende tabblad nodig
  heeft. De Monte-Carlo van 10.000 trekkingen draait nu alleen op de Edge-laag.
- **Lege staten die iets zeggen**: elk paneel dat nog niets kan zeggen, zegt wát het nodig heeft
  en vanaf hoeveel trades, met een voortgangsbalkje.

**Fase 12.2 — rapportkaart (📄 Rapport)**
- Eén printbare pagina per **maand** of per **jaar**: trades, winrate, valide %, perfecte setups,
  expectancy, profit factor, regel-adherentie, discipline-score en hoe vaak je bewust wegbleef.
- Je **beste en slechtste trade** met de les die je er zelf bij schreef, je **grootste lek**
  (de vaakste foutcode mét de corrigerende regel), je tags, al je lessen en al je dag- en
  weekreviews uit die periode.
- Onder de twintig trades zegt hij er zelf bij dat winrate en expectancy nog ruis zijn, en dat
  adherentie en discipline dat níet zijn.
- De knop **🖨 Printen** geeft een schone zwart-op-wit versie zonder navigatie.

**Fase 12.3 — notitieboek (📓 Notities)**
- Voor alles wat niet aan één trade hangt: marktobservaties, ideeën, iets uit een video, een vraag
  om later uit te zoeken. Met datum, tags, zoekveld en bewerken.

**Fase 12.4 — vrije tags**
- Onderin het trade-formulier een **tagveld** met suggesties van wat je eerder gebruikte
  (klikken voegt toe of haalt weg). Tags worden ontdubbeld en naar kleine letters gehaald,
  zodat "Sweep" en "sweep" niet uit elkaar lopen.
- Op het dashboard en in je rapportkaart krijgt **elke tag zijn eigen winrate, expectancy en netto**.
  Zo trek je varianten binnen het CBR-model uit elkaar zonder dat er code bij hoeft. Tags met
  minder dan drie trades worden grijs getoond.

**Fase 12.1 — je data veilig**
- **Automatische back-up** bij elke start: een zip van de database plus je screenshots in `backups/`,
  dertig dagen bewaard (en altijd minstens de laatste drie). Er is ook een knop *Nu back-uppen*.
- **Dubbel-detectie**: twee trades op dezelfde dag met dezelfde entry-tijd, of met hetzelfde resultaat,
  RR én richting, worden op het dashboard gemeld. De journal verwijdert nooit zelf iets.

**Fase 7 — ritme en gemak**
- **📱 Snel** — een duimvriendelijke invoerpagina voor je telefoon. Richting, checklist, RR,
  resultaat, foto, één zin les. Binnen dertig seconden gelogd, direct na je trade.
- **Dag afsluiten** — onderaan het dagoverzicht: wat ging goed, wat kon beter, waar let ik morgen op.
- **🗓 Week** — weekreview met een automatische samenvatting (perfecte setups, overgeslagen setups,
  expectancy, vaakste fout met de corrigerende regel, en of je valide-% steeg of daalde t.o.v.
  vorige week). De **focus** die je invult verschijnt de week erna bovenaan je dagoverzicht.

**Lean journallen**
- Per trade log je alleen wat telt: richting (long/short), de checklist, **RR** en **risk (€)**,
  resultaat, foutcodes, één zin les, mentale staat en screenshots.
  Entry/SL/TP-prijzen zitten achter een inklapbaar blokje — ze zijn optioneel.

**Portfolio & beloning**
- **Portfolio-groei vanaf je startkapitaal** (standaard €50), met daarnaast een gestippelde lijn
  "alleen valide setups (A/B)" — het gat tussen beide lijnen is wat je discipline oplevert.
- **Mijlpalen** (€75 → €100 → €150 …) met voortgangsbalk, en **streaks** (wins op rij,
  valide setups op rij).

**📋 Regels — je spiekbriefje**
- Al je CBR-regels uit je notitieboek op één scherm: tijdvenster, voorbereiding, de drie
  kritische criteria, entry & exit, goede vs. slechte overextensie, SL-regels en leren van fouten.

**Startdag 3 sep 2026** is al ingevoerd: 4 trades + 3 no-trades (incl. de gemiste valide setup).
De startdag wordt automatisch geseed zodra de database nog niet bestaat (`cbr_journal.db`).
Verwijder dat bestand om opnieuw te beginnen.

## De grade-logica

De grade volgt **altijd** uit de checklist, nooit uit onderbuik:

```
een kritisch criterium (1, 2 of 3) is ✗ of ?   ->  grade C  ("dit was geen trade")
alle vijf criteria ✓                           ->  grade A
drie kritische ✓ (maar niet alle vijf)         ->  grade B
```

Kritische criteria (alle drie vereist):
1. Trending range met 2+ legs (geen schone trend)
2. Overextensie die de vorige 1H high/low sweept
3. Type-3 shift (beide kanten geraakt)

Kwaliteitscriteria (niet-kritisch):
4. Entry op 50% van de shift
5. TP op 50% van de extensie, RR ≥ 1 (harde vloer)

## Nog te bouwen

Verbeterplan II is af (fase 8 t/m 12); uit **Verbeterplan III** staan fase 13, 14 en 16.
Bewust in de wacht tot er ongeveer twintig trades zijn — analyse zonder data zegt niets:
- **Fase 15** — eigen dimensies met vaste opties, risk of ruin, doelen/KPI-targets,
  en what-if-scenario's op je eigen trades.
- **13.3** — R-verdeling als histogram (een histogram van vijf staafjes is geen verdeling).
- **16.4** — jaarwissel: archiefweergave en een "vorig jaar"-kolom in de rapportkaart.

Bewust **niet** gebouwd, met reden: AI-coach (vereist je trades op een externe server; deze
journal is lokaal en dat is het punt), trade-sharing community, een app in de App Store,
tick-replay op de chart, broker-sync, Sharpe/Sortino, what-if-scenario's op exits
(vereisen entry/SL/TP-prijzen die je bewust niet logt), screenshots plakken uit het klembord
en een positiegrootte-calculator.

## Bijwerken naar een nieuwe versie

De zip maakt een eigen map **`CBR-Journal-app`**. Pak hem uit waar je wilt — bij voorkeur
ergens vast, zoals `C:\CBR-Journal-app` of je bureaublad — en start hem daar.

**Je oude gegevens gaan vanzelf mee.** Bij de eerste start zoekt de journal in de mappen
eromheen naar een bestaande `cbr_journal.db` en neemt de nieuwste over. Hij *kopieert* alleen;
je oude map blijft ongemoeid staan. In het zwarte venster staat uit welke map hij is overgenomen.

Rechtsboven in de app staat een versiestempel (bijvoorbeeld `v2026.09.05 · licht`), en de
starter toont dezelfde versie in het zwarte venster. Komen die niet overeen met wat je
verwacht, dan is het uitpakken niet gelukt.

Pak de zip uit **over** je bestaande map `cbr-journal` heen. Je database (`cbr_journal.db`) zit
bewust niet in de zip en blijft dus staan; ontbrekende kolommen en tabellen worden bij de eerstvolgende
start automatisch toegevoegd, zonder dat er iets van je oude data verloren gaat. En vlak vóór dat alles
maakt de journal sowieso een back-up in `backups/`.

## Mapstructuur

```
cbr-journal/
  START-JOURNAL.bat       # lokale start (Windows) + snelkoppeling op je bureaublad
  SNELKOPPELING-op-bureaublad.bat
  snelkoppeling.ps1
  requirements.txt
  cbr_journal.db          # ontstaat bij eerste start (niet inchecken)
  app/
    main.py               # FastAPI + API-endpoints + pagina's
    db.py                 # SQLite-schema + seed van de startdag + settings
    cbr.py                # criteria, foutentaxonomie, auto-grade-logica
    stats.py              # aggregatie voor het dashboard
    fouten.py             # foutenanalyse + patroon-detectie
    edge.py               # expectancy, profit factor, drawdown, criterium-edge
    kalender.py           # maandrooster + jaarstrook voor de heatmap
    adherentie.py         # regel-adherentie + gemiste setups
    simulatie.py          # Wilson-interval + Monte-Carlo
    inzicht.py            # timing, kalibratie en discipline-meter
    rapport.py            # rapportkaart per maand/jaar + tag-statistiek
    backup.py             # automatische back-up + dubbel-detectie
  static/                 # vanilla JS frontend
    index.html / overview.js    # dagoverzicht
    trade.html  / trade.js      # trade toevoegen/bewerken (live grade + screenshots)
    notrade.html/ notrade.js    # no-trade toevoegen/bewerken (+ screenshots)
    dashboard.html/ dashboard.js # performance-dashboard met grafieken
    regels.html / regels.js     # spiekbriefje + regel-changelog
    week.html   / week.js       # weekreview met automatische samenvatting
    snel.html   / snel.js       # snelinvoer voor de telefoon
    fouten.html / fouten.js     # foutenanalyse + patroon-detectie
    rapport.html/ rapport.js    # printbare rapportkaart per maand/jaar
    notities.html/ notities.js  # notitieboek
    setups.html / setups.js     # setup-bibliotheek met beeld
    prullenbak.html/ prullenbak.js # herstelbaar verwijderen
    kalender.html/ kalender.js  # kalender-heatmap + jaarstrook
    style.css / common.js
    vendor/chart.umd.min.js     # Chart.js, lokaal (werkt offline)
  screenshots/            # <datum>/... (drag-and-drop uploads)
  backups/                # automatische zips (ontstaat vanzelf, niet inchecken)
```

---

## Ronde 2 — de sweep meten (v2026.09.07.1)

Aanleiding: twee van de eerste acht trades verloren op precies dezelfde manier —
SL geraakt met een minimale marge, waarna prijs alsnog het TP-niveau haalde.
Bij trade 8 kwam prijs 3,0 points boven de vorige high uit terwijl de SL op
2,5 points stond. De stop lag dus *binnen* de sweep.

**1 point = 0,10 in prijs.** 0,30 boven de high = 3 points.

### Nieuwe velden per trade
| Veld | Betekenis |
|---|---|
| `sweep_overshoot_points` | hoe ver ging prijs voorbij de vorige 1H high/low, op het extreme punt |
| `sl_afstand_points` | afstand entry → SL |
| `tp_afstand_points` | afstand entry → TP |
| `sl_marge` *(berekend)* | `sl_afstand − overshoot`. Negatief = stop lag binnen de sweep |
| `sl_dan_tp` | SL geraakt en daarna alsnog het TP-niveau geraakt (ja/nee) |
| `shift_kwaliteit` | duidelijk / soft / onduidelijk — staat náást `crit3_shift` |
| `volume_hoog` | hoog / laag volume bij de overextensie |
| `overextensie_kwaliteit` | goed / slecht |
| `minuten_in_hourly` | minuut in de hourly candle bij entry |

Vul de meetvelden bij **élke** trade in, ook winnaars. Alleen verliezers meten
geeft een scheve steekproef — dan lijkt elke sweep groter dan hij is. Het
dashboard waarschuwt zichtbaar zolang je winnaars ontbreken.

### Retro-simulatie van de SL-afstand
Op **Dashboard → Edge**: een schuifregelaar van 2 tot 8 points die over je eigen
trades doorrekent hoeveel er de sweep zouden hebben overleefd, wat de winrate
wordt en wat de RR wordt. Overleving volgt puur uit de meting; een verliezer telt
alleen als winnaar wanneer jij hebt gelogd dat prijs daarna alsnog TP haalde —
er wordt niets aangenomen.

Omdat bij goud rond 4500 het verschil tussen een SL van 0,25 en 0,50
verwaarloosbaar is t.o.v. de prijs, hoeft de TP meestal niet mee te schuiven en
blijft de RR vaak gewoon boven 1. De simulator toont daarom **apart** bij hoeveel
trades de RR onder 1 zakt — dat is je harde vloer.

Daarnaast een histogram van de overshoot met een verticale lijn op de gekozen
SL-afstand: in één oogopslag welk deel van je sweeps binnen je stop past.

> **Toon en interpretatie.** "SL geraakt, daarna TP" is *SL-plaatsingsdata*, geen
> gemiste winst. Als gemiste winst gepresenteerd wordt het een uitnodiging om de
> stop structureel te verruimen, en dat is meestal de verkeerde les: het echte
> probleem zit vaker in de setup-kwaliteit of in waar de stop stond ten opzichte
> van de sweep dan in de breedte van de stop. De app zegt dit ook zelf, in het
> paneel.

### Shift-kwaliteit, volume en timing
Op **Dashboard → Patronen**: winrate en expectancy van duidelijke tegenover softe
shifts, van hoog tegenover laag volume, en van de minuut in de hourly candle.
Tooltip in het formulier: stijgt prijs te lang en te snel vóór de return, dan
wordt de shift zachter en minder duidelijk.

### Grade-integriteit
Staat een kritisch criterium op ✓ terwijl je in je notitie "soft", "twijfel",
"niet echt" of "niet heel duidelijk" schrijft — of markeer je de shift als soft —
dan vraagt het formulier: *"Weet je zeker dat dit een ✓ is? Twijfel telt als ?."*
Geen blokkade, jij beslist. Reden: de grade hoort uit de checklist te volgen en
niet uit de uitkomst, anders wordt dezelfde softe shift bij winst een B en bij
verlies een C.

### Correctie in de bestaande data
Trade 8 (7 sep, −€3,40) stond op grade B terwijl de shift een soft break was.
`crit3_shift` gaat naar `?`, waardoor de auto-grade **C** oplevert. Dit gebeurt
automatisch bij de eerste start van deze versie, en is idempotent.

---

## Prestatie-tracker en vaste navigatie (v2026.09.07.2)

### Eén menu, altijd bovenin
De navigatielinks stonden per scherm in een eigen rijtje, waardoor je via-via
moest lopen. Nu staat op **elk** scherm dezelfde balk, die bovenin blijft plakken
bij het scrollen, met vier dropdowns: **Loggen · Overzicht · Analyse · Meer**.
Op de telefoon klapt hij open via het hamburgermenu. Het commandopalet (Ctrl+K)
en "＋ Trade" zitten rechts. Paginaeigen knoppen (datumkiezer, periodetabs,
printen) zijn op hun eigen scherm blijven staan.

### Nieuw scherm: Prestaties (`/prestaties`, sneltoets `s`)
| Blok | Wat je ziet |
|---|---|
| Hoe sta ik ervoor | saldo, netto P/L, rendement, winrate, gem. per dag en per trade, expectancy, kosten |
| Saldoverloop | je saldo per trade vanaf je startkapitaal |
| Per maand | staafgrafiek + tabel met maandrendement en eindsaldo |
| Per dag | staafgrafiek + tabel met dagrendement en lopend saldo |
| Per uur van de dag | waar je geld vandaan komt, als check op je Londense uur |
| Waar in het uur | kwartieren én blokjes van vijf minuten, met je venster 30–45 gemarkeerd |
| Waar komt het vandaan | per weekdag, long tegenover short, per grade |
| Reeksen en uitschieters | langste winst-/verliesreeks, grootste terugval, payoff, beste en slechtste dag |

### Percentages, en waarom dat een apart kopje verdient
Dit gaat in de meeste journals mis, dus expliciet:

- een periodepercentage rekent over het saldo aan het **begin** van die periode
  — niet over je startkapitaal en niet over je eindsaldo;
- percentages van losse periodes worden **gestapeld, niet opgeteld**. Twee
  maanden van +10% is +21%, niet +20%. De app rekent `(1+r₁)·(1+r₂)−1`;
- zonder startkapitaal toont de app **"–"** en geen `0%`, want een percentage
  zonder basis betekent niets.

Ter controle staat het totaalrendement naast de samengestelde maanden op het
scherm. Wijken die af, dan klopt er iets niet.

### Extra signalen
- **Aandeel grootste winnaar.** Draagt één trade meer dan de helft van je netto,
  dan zegt de app dat dit een meevaller is en nog geen edge.
- **Payoff naast winrate.** Met een winrate-first model mag de payoff onder 1
  liggen — zolang je winrate dat draagt. Beide staan er daarom naast elkaar.
- **Grootste terugval** in euro's, over het saldoverloop.

---

## Ronde 3 — proces, mens en vangrails (v2026.09.07.3)

De journal was sterk in data en zwak in discipline, staat en reflectie. Deze
ronde vult die drie gaten, en sluit af met een beloning.

### 1. Proces boven uitkomst
Op **Dashboard → Vandaag** staat nu een tweede scorebord naast de winrate:

| Cijfer | Wat het zegt |
|---|---|
| Valide-setup-ratio | aandeel A- en B-setups. Dít is wat je kunt sturen |
| Winrate zonder luck | je winrate met de trades die je zelf als geluk markeerde eruit |
| Reeks valide setups | de streak die er toe doet — een winstreeks kun je niet sturen |
| Uit valide setups | welk deel van je netto uit door je checklist goedgekeurde setups komt |

Per trade is er een vinkje **"voelde als luck, zonder duidelijke edge"**
(`luck_flag`). Een winst die jij zelf niet aan je edge toeschrijft hoort niet
stilzwijgend als vaardigheid in je winrate te glippen.

### 2. Discipline-kaart per sessie
Op het dagoverzicht: **"Hoe ging het vandaag?"** — bewust op dagniveau en
bewust klein. Twee toggles (alleen in mijn venster getraded / plan gevolgd,
niets geforceerd), je staat vooraf (rustig / gehaast / moe) en één regel
"belangrijkste les vandaag". Per trade een stemming bijhouden is een klus die
je na een week laat vallen; dit houd je vol. Tabel `sessies`.

Op **Dashboard → Discipline** komt daaruit terug of je staat vooraf je
financieel iets kost, plus je eigen lessen op een rij.

### 3. Venster-bewaking en overtrading-rem
- In het trade-formulier rekent de entrytijd live om naar Londen en zegt of je
  binnen je venster zit (standaard 10:00–11:00 bij jou = 09:00–10:00 Londen,
  instelbaar via `venster_van` / `venster_tot`). Daarbuiten: suggestie **E4**.
- Zit je op je dagmaximum, dan meldt het formulier dat vóórdat je invult.
  Zacht, niet blokkerend — jij beslist.
- Op het dashboard: binnen tegenover buiten je venster, met winrate,
  valide-ratio en netto naast elkaar.

### 4. SL-plaatsing-guardrail
Zat al in ronde 2: tijdens het invullen tonen overshoot en SL-afstand live de
`sl_marge`, met een melding zodra die negatief is (stop lag binnen de sweep).
Altijd als plaatsingsdata, nooit als "verruim je SL".

### 9. Muntje en pling
Bij een **winst die ook grade A is** komt een muntje van onderen omhoog, spint,
*pling*, en valt weer uit beeld. Bewust niet bij elke winst: belonen op uitkomst
alleen leert je van uitkomsten houden, en dat is precies de gewoonte die deze
journal probeert af te leren. Een A die verliest krijgt niets, een C die wint al
helemaal niet.

```js
// direct na het succesvol opslaan van een trade:
maybeCelebrate({ result: trade.result, grade: trade.grade });
```

Het geluid wordt in de browser zelf opgewekt (WebAudio, geen bestand) en de
animatie respecteert `prefers-reduced-motion`.

### Bewust niet gebouwd
Geen moodtracking per trade (blijft op sessieniveau), geen entry/exit-prijzen,
geen DXY go/no-go, en de SL-simulator suggereert nooit "verruimen".

### 5–8 — reflectie, patronen, gemiste setups en mijlpalen (v2026.09.07.4)

**5. Weekreview met afvinkbare focus.** De weekreview vatte je week al samen;
daar komt bij: de **beste A-setup van de week** (beste uitvoering die ook geld
opleverde, met jouw eigen les erbij) en het zwaarste terugkerende patroon. En
je focus blijft nu bovenaan je dagoverzicht staan **tot je 'm afvinkt** — met
"Gelukt ✓" op het dagoverzicht of "Afvinken" op de weekreview. Kolom
`reviews.focus_af`.

**6. Terugkerende-patroondetector.** Naast de foutcode-detector (3× binnen 10
trades) kijkt de journal nu naar **je eigen tags**. Komt een tag drie keer of
vaker terug, dan krijg je 'm te zien met wat hij je oplevert of kost:

> "soft break" kwam 3× terug en staat op −7,88 euro (−1,02R per trade).
> Dit is geen incident meer, dit is een patroon.

Wat geld kost staat bovenaan en is rood; wat werkt is groen ("zoek er meer
van"). Te vinden op **Foutenanalyse**.

**7. Gemiste setups.** Bestond al als status "overgeslagen" met een reden en een
eigen teller op Dashboard → Discipline. Toegevoegd: de reden **"niet aan het
scherm"** — een routine-probleem, geen setup-probleem, en dat verdient een eigen
hokje naast twijfel en te laat gezien.

**8. Mijlpalen en streaks.** Naast de saldo-mijlpalen (€75, €100, …) en je
reeks valide setups is er nu de **schone week**: een week waarin je geen enkele
C hebt genomen. Bewust niet "een winstweek" — winst kun je niet sturen, je
setupkeuze wel. Staat op Dashboard → Vandaag.
