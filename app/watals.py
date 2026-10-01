"""
Wat als... -- scenario's op je eigen trades, met de onzekerheid erbij.

Dit is de gevaarlijkste module van het hele platform. Een scenario-dashboard
maakt van een aanname een grafiek, en een grafiek ziet er altijd waar uit. Daarom
staat hier één regel boven alles:

    ELK CIJFER DRAAGT ZIJN HERKOMST MEE.

Er zijn drie soorten "wat als", en ze zijn NIET even hard:

  1. HERREKEND  -- je filtert je echte trades. De uitkomst is bekend, want die
                   trades zijn gewoon gebeurd. "Alleen A-setups" is geen aanname:
                   je telt een deelverzameling opnieuw op. Dit is meting.

  2. GEMETEN    -- een contrafeitelijk scenario dat volgt uit wat JIJ gelogd hebt.
                   Een ruimere SL: je weet hoe ver de sweep kwam (overshoot) en
                   je hebt gelogd of prijs daarna alsnog TP haalde (sl_dan_tp).
                   Dan is "deze verliezer was een winnaar geweest" geen gok maar
                   een afleiding uit twee metingen. Alleen geldig zolang die
                   velden ingevuld zijn -- vandaar dat dekking overal meeloopt.

  3. GEPROJECTEERD -- de uitkomst is ONBEKEND en wordt aangenomen. Elke gemiste
                   trade valt hier. Je weet niet wat hij gedaan zou hebben. Punt.
                   Deze scenario's leveren daarom nooit één lijn op maar een
                   band: beste geval, verwachting, slechtste geval. Wie hier een
                   enkel getal van maakt, liegt tegen zichzelf.

De tweede regel: dit werkt beide kanten op. Een journal dat alleen laat zien wat
je gemist hebt kweekt spijt en overtrading. Daarom rekent deze module net zo hard
door wat je discipline je BESPAARD heeft -- de setups die je terecht liet lopen,
en wat een krappere SL je gekost zou hebben.

Geld-model bij SL-scenario's: VAST RISICO IN EURO'S. Zet je je stop twee keer zo
ver weg, dan halveer je je positie, zodat je per trade hetzelfde riskeert. Anders
vergelijk je twee verschillende inzetten en zegt de uitkomst niets. Gevolg: een
ruimere SL verkleint je winst per trade (de RR daalt), en dat hoort zichtbaar te
zijn -- ruimer is niet gratis.
"""

from . import cbr, edge, adherentie, simulatie

MIN_N = 5              # onder dit aantal is een scenario een anekdote
MIN_N_OORDEEL = 20     # onder dit aantal mag je er geen regel op bouwen

# SL-schuifregelaar, in points (1 point = 0,10 in prijs).
SL_STANDEN = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0]
# De vier standen die Marijn expliciet noemde, als snelknoppen.
SL_SNELKNOPPEN = [5.0, 10.0, 20.0, 50.0]

# TP-schuifregelaar: welk deel van je huidige TP-afstand.
TP_FACTOREN = [0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0]


# ---------- kleine helpers ----------

def _f(waarde):
    if waarde is None or waarde == "":
        return None
    try:
        return float(waarde)
    except (TypeError, ValueError):
        return None


def _netto(t):
    return edge._netto(t)


def _gewonnen(t):
    return _netto(t) > 0


def _risk_eur(t, terugval=2.0):
    """
    Wat riskeerde je op deze trade, in euro's?

    Zelfde ladder als edge.r_van_trade: eerst wat je invulde, dan wat volgt uit
    winst en RR, dan de verliesgrootte zelf. Nooit verzinnen zonder het te zeggen
    -- de herkomst gaat mee naar boven in `datakwaliteit`.
    """
    r = _f(t.get("risk_eur"))
    if r and r > 0:
        return r, "gemeten"
    res = _f(t.get("resultaat_eur")) or 0.0
    rr = _f(t.get("rr"))
    if res > 0 and rr and rr > 0:
        return res / rr, "afgeleid"
    if res < 0:
        return abs(res), "afgeleid"
    return terugval, "terugval"


def _mediaan(waarden):
    w = sorted(x for x in waarden if x is not None)
    if not w:
        return None
    m = len(w) // 2
    return w[m] if len(w) % 2 else (w[m - 1] + w[m]) / 2


def _typisch_risico(trades):
    """Het risico dat we aanhouden voor trades die nooit gebeurd zijn."""
    return _mediaan([_risk_eur(t)[0] for t in trades]) or 2.0


def _typische_charge(trades):
    c = _mediaan([_f(t.get("charges")) for t in trades if _f(t.get("charges")) is not None])
    return c if c is not None else -0.06


def _sorteer(trades):
    return sorted(trades, key=lambda t: (t.get("datum") or "",
                                         t.get("tijd_entry") or "", t.get("id") or 0))


# ---------- de kern: een reeks uitkomsten -> een scenario ----------

def _uit_bedragen(bedragen, startkapitaal, label, herkomst, extra=None):
    """
    Van een lijst netto-bedragen naar alles wat een scenario moet tonen:
    winrate, netto, en het saldoverloop waarmee de grafiek getekend wordt.

    `herkomst` is verplicht en is een van: herrekend | gemeten | geprojecteerd.
    Zonder herkomst geen scenario -- dat is precies de fout die deze module
    niet mag maken.
    """
    n = len(bedragen)
    winnaars = [b for b in bedragen if b > 0]
    netto = round(sum(bedragen), 2)
    start = float(startkapitaal or 0)

    saldo = start
    curve = [{"i": 0, "saldo": round(saldo, 2), "pct": 0.0}]
    for i, b in enumerate(bedragen, 1):
        saldo = round(saldo + b, 2)
        curve.append({
            "i": i,
            "saldo": saldo,
            "pct": round(100 * (saldo - start) / start, 2) if start else None,
        })

    scen = {
        "label": label,
        "herkomst": herkomst,
        "n": n,
        "winnaars": len(winnaars),
        "verliezers": len([b for b in bedragen if b < 0]),
        "winrate": round(100 * len(winnaars) / n) if n else 0,
        "netto_eur": netto,
        "saldo_eind": round(start + netto, 2),
        "groei_pct": round(100 * netto / start, 2) if start else None,
        "gem_per_trade": round(netto / n, 2) if n else 0.0,
        "curve": curve,
        "genoeg": n >= MIN_N,
    }
    if extra:
        scen.update(extra)
    return scen


def _scenario_van_trades(trades, startkapitaal, label, herkomst="herrekend", extra=None):
    bedragen = [_netto(t) for t in _sorteer(trades)]
    return _uit_bedragen(bedragen, startkapitaal, label, herkomst, extra)


# =====================================================================
# 1. HERREKEND -- filters over je echte trades
# =====================================================================

def _in_venster(t, van, tot):
    return cbr.binnen_venster(t.get("tijd_entry"), van, tot) is True


def _minuut(t):
    tijd = (t.get("tijd_entry") or "").strip()
    if ":" not in tijd:
        return None
    try:
        return int(tijd.split(":")[1])
    except (ValueError, IndexError):
        return None


def filters(van="11:00", tot="12:00"):
    """
    Elke as waarop we al analyseren, als los scenario. Allemaal herrekend:
    de uitkomsten zijn bekend, er wordt niets aangenomen.

    `vraag` is wat het scenario beantwoordt -- die zin hoort in de UI, want een
    filternaam alleen zegt niemand iets.
    """
    return [
        {"key": "alles", "label": "Alles, zoals het ging", "basis": True,
         "vraag": "Je werkelijke resultaat. Alle andere lijnen worden hiermee vergeleken.",
         "fn": lambda t: True},

        {"key": "geen_c", "label": "Zonder C-setups",
         "vraag": "Wat als je je eigen checklist altijd had gehoorzaamd?",
         "fn": lambda t: (t.get("grade") or "") != "C"},

        {"key": "alleen_a", "label": "Alleen A-setups",
         "vraag": "Wat als je uitsluitend perfecte setups had genomen?",
         "fn": lambda t: (t.get("grade") or "") == "A"},

        {"key": "zonder_luck", "label": "Zonder geluk-trades",
         "vraag": "Wat blijft er over als je de winsten weghaalt die je zelf geen edge vond?",
         "fn": lambda t: (t.get("luck_flag") or "").strip() != "ja"},

        {"key": "in_venster", "label": "Alleen binnen je uur",
         "vraag": "Wat als je nooit buiten het 2e uur van Londen had gehandeld?",
         "fn": lambda t: _in_venster(t, van, tot)},

        {"key": "timing_3045", "label": "Alleen entry 30–45 min in de hourly",
         "vraag": "Je eigen timingregel, hard toegepast.",
         "fn": lambda t: (t.get("minuten_in_hourly") not in (None, "")
                          and 30 <= int(t["minuten_in_hourly"]) <= 45)},

        {"key": "shift_duidelijk", "label": "Alleen duidelijke shift",
         "vraag": "Wat als een softe type-3 shift voor jou een ✗ was in plaats van een ✓?",
         "fn": lambda t: (t.get("shift_kwaliteit") or "") == "duidelijk"},

        {"key": "volume_hoog", "label": "Alleen hoog volume",
         "vraag": "Voegt het volume-filter dat je in je hoofd hebt echt iets toe?",
         "fn": lambda t: (t.get("volume_hoog") or "") == "ja"},

        {"key": "over_goed", "label": "Alleen goede overextensie",
         "vraag": "Wat als je alleen instapte na een overextensie die je zelf goed vond?",
         "fn": lambda t: (t.get("overextensie_kwaliteit") or "") == "goed"},

        {"key": "rr_1plus", "label": "Alleen RR ≥ 1",
         "vraag": "Je harde vloer, zonder uitzonderingen.",
         "fn": lambda t: (_f(t.get("rr")) or 0) >= 1},

        {"key": "regelvast", "label": "Alleen regel-conforme trades",
         "vraag": "Geen enkele overtreding: geen C, RR ≥ 1, geen discipline-foutcode.",
         "fn": lambda t: adherentie.beoordeel(t)[0]},

        {"key": "perfect", "label": "Perfecte discipline",
         "vraag": "Alles tegelijk: A of B, binnen je uur, geen enkele regelovertreding.",
         "fn": lambda t: ((t.get("grade") or "") in ("A", "B")
                          and _in_venster(t, van, tot)
                          and adherentie.beoordeel(t)[0])},
    ]


def herrekening(trades, startkapitaal, van="11:00", tot="12:00"):
    """Alle filters doorgerekend, met het verschil ten opzichte van de werkelijkheid."""
    uit = []
    basis_netto = round(sum(_netto(t) for t in trades), 2)
    for f in filters(van, tot):
        rij = [t for t in trades if f["fn"](t)]
        scen = _scenario_van_trades(rij, startkapitaal, f["label"], "herrekend", {
            "key": f["key"],
            "vraag": f["vraag"],
            "basis": f.get("basis", False),
            "weggelaten": len(trades) - len(rij),
            "delta_eur": round(round(sum(_netto(t) for t in rij), 2) - basis_netto, 2),
        })
        uit.append(scen)
    return uit


# =====================================================================
# 2. GEMETEN -- SL verschuiven op basis van de sweep-metingen
# =====================================================================

def _sl_meetbaar(trades):
    """Alleen trades waarvan overshoot én SL-afstand gemeten zijn."""
    return [t for t in trades
            if _f(t.get("sweep_overshoot_points")) is not None
            and _f(t.get("sl_afstand_points")) is not None]


def _sl_uitkomst(t, sl_points, risico):
    """
    Wat had deze trade gedaan met de stop op `sl_points`?

    Twee metingen doen het werk:
      overshoot  -- hoe ver de sweep voorbij het referentieniveau kwam;
      sl_dan_tp  -- of prijs ná je stop alsnog het TP-niveau haalde.

    Belangrijk en hier expres anders dan in sweep.py: een WINNAAR blijft niet
    automatisch winnaar. Zet je de stop krapper dan de overshoot, dan had die
    sweep je er alsnog uitgehaald. Krapper zetten is niet gratis, en een model
    dat dat verzwijgt maakt van elke verkrapping een verbetering.

    Geeft (bedrag_in_euro, soort). Soort 'onbekend' betekent: deze trade kan
    deze stand niet beoordelen, en telt dus nergens in mee.
    """
    ov = _f(t.get("sweep_overshoot_points"))
    tp_pts = _f(t.get("tp_afstand_points"))
    charge = _f(t.get("charges")) or 0.0
    echt_gewonnen = _gewonnen(t)

    geraakt = ov >= sl_points          # de sweep kwam tot aan je stop
    if geraakt:
        return -risico + charge, ("verlies_nieuw" if echt_gewonnen else "verlies")

    # De stop overleefde de sweep.
    if echt_gewonnen:
        soort = "winst"
    elif (t.get("sl_dan_tp") or "") == "ja":
        soort = "winst_nieuw"          # jij hebt gelogd dat TP daarna gehaald werd
    else:
        return None, "onbekend"        # verloren, stop overleefd, maar TP? geen data

    if tp_pts is None or sl_points <= 0:
        return None, "onbekend"
    rr = tp_pts / sl_points            # vast risico -> RR schaalt met de stopbreedte
    return risico * rr + charge, soort


def sl_scenario(trades, sl_points, startkapitaal):
    """Eén SL-stand, volledig doorgerekend tot een saldoverloop."""
    meet = _sl_meetbaar(trades)
    terugval = _typisch_risico(trades)
    bedragen, soorten, onbekend = [], [], 0

    for t in _sorteer(meet):
        risico = _risk_eur(t, terugval)[0]
        bedrag, soort = _sl_uitkomst(t, sl_points, risico)
        if bedrag is None:
            onbekend += 1
            continue
        bedragen.append(bedrag)
        soorten.append(soort)

    rr_waarden = [(_f(t.get("tp_afstand_points")) or 0) / sl_points
                  for t in meet if _f(t.get("tp_afstand_points")) is not None and sl_points > 0]

    return _uit_bedragen(bedragen, startkapitaal,
                         f"SL op {sl_points:g} points", "gemeten", {
        "sl_points": sl_points,
        "sl_prijs": cbr.points_naar_prijs(sl_points),
        "onbekend": onbekend,
        "gered": soorten.count("winst_nieuw"),      # verlies werd winst
        "verspeeld": soorten.count("verlies_nieuw"),  # winst werd verlies
        "rr_gemiddeld": round(sum(rr_waarden) / len(rr_waarden), 2) if rr_waarden else None,
        "rr_onder_1": len([r for r in rr_waarden if r < 1]),
    })


def sl_reeks(trades, startkapitaal, standen=None):
    return [sl_scenario(trades, s, startkapitaal) for s in (standen or SL_STANDEN)]


def sl_analyse(trades, startkapitaal, gekozen=None):
    meet = _sl_meetbaar(trades)
    huidig = _mediaan([_f(t.get("sl_afstand_points")) for t in meet])
    reeks = sl_reeks(trades, startkapitaal) if meet else []

    # Onvolledige sl_dan_tp maakt elke verruiming te pessimistisch: een verliezer
    # zonder dat vinkje kan nooit winnaar worden. Dat moet je weten.
    verliezers = [t for t in meet if not _gewonnen(t)]
    zonder_vlag = [t for t in verliezers if (t.get("sl_dan_tp") or "") not in ("ja", "nee")]

    # De beste stand is niet simpelweg de hoogste netto. Een ruimere stop
    # verlaagt de RR, en onder de 1 breekt hij zijn eigen vloer. Een scenario dat
    # "verruim naar 4 points" adviseert terwijl de RR daar op 0,85 uitkomt, geeft
    # advies dat in strijd is met de regel waar het model op staat. Dus twee
    # antwoorden: het beste dat de vloer respecteert, en apart de verleiding.
    bruikbaar = [r for r in reeks if r["n"] >= MIN_N]
    houdt_vloer = [r for r in bruikbaar if (r["rr_gemiddeld"] or 0) >= 1]
    beste = max(houdt_vloer, key=lambda r: r["netto_eur"], default=None)
    beste_ruw = max(bruikbaar, key=lambda r: r["netto_eur"], default=None)
    vloer_conflict = ""
    if beste and beste_ruw and beste_ruw["sl_points"] != beste["sl_points"]:
        vloer_conflict = (
            f"Puur op netto zou {beste_ruw['sl_points']:g} points beter uitpakken "
            f"({beste_ruw['netto_eur']:+.2f} tegen {beste['netto_eur']:+.2f}), maar daar zakt je "
            f"gemiddelde RR naar {beste_ruw['rr_gemiddeld']} — onder je eigen vloer van 1. "
            "Die stand staat er wel, maar niet als aanbeveling.")

    return {
        "meetbaar": len(meet),
        "totaal": len(trades),
        "dekking_pct": round(100 * len(meet) / len(trades)) if trades else 0,
        "huidige_sl": round(huidig, 2) if huidig else None,
        "gekozen": sl_scenario(trades, gekozen, startkapitaal) if (meet and gekozen) else None,
        "reeks": reeks,
        "snelknoppen": SL_SNELKNOPPEN,
        "beste": beste,
        "beste_ruw": beste_ruw,
        "vloer_conflict": vloer_conflict,
        "zonder_sl_dan_tp": len(zonder_vlag),
        "min_n": MIN_N,
        "kader": (
            "Vast risico in euro's: een ruimere stop betekent een kleinere positie. "
            "Daarom daalt je winst per trade als je de stop verruimt — ruimer is niet gratis. "
            "En andersom: zet je de stop krapper dan de gemeten overshoot, dan had die sweep "
            "je er alsnog uitgehaald. Ook winnaars kunnen hier dus omslaan."
        ),
        "waarschuwing": (
            f"{len(zonder_vlag)} van je {len(verliezers)} verliezers hebben geen 'daarna alsnog TP' "
            "ingevuld. Die kunnen in geen enkel scenario winnaar worden, dus elke verruiming ziet "
            "er hier somberder uit dan hij was."
            if zonder_vlag else ""
        ),
    }


# =====================================================================
# 3. DEELS GEMETEN -- TP dichterbij
# =====================================================================

def tp_scenario(trades, factor, startkapitaal):
    """
    TP op `factor` × je huidige TP-afstand.

    Voor een WINNAAR is dit meting: prijs heeft je volle TP gehaald, dus is hij
    onderweg langs elk dichterbij gelegen niveau gekomen. De winst schaalt mee.

    Voor een VERLIEZER weten we het niet. Zou een dichterbij TP geraakt zijn
    vóórdat de stop viel? Daar hebben we geen meting van. Die blijven hier dus
    verliezer, en daarmee is de uitkomst een ONDERGRENS: in werkelijkheid kan
    een dichterbij TP alleen maar béter uitpakken dan wat hier staat.
    """
    bedragen, aangeraakt = [], 0
    onder_1 = 0

    for t in _sorteer(trades):
        charge = _f(t.get("charges")) or 0.0
        bruto = _f(t.get("resultaat_eur")) or 0.0
        if bruto > 0:
            bedragen.append(bruto * factor + charge)
            aangeraakt += 1
        else:
            bedragen.append(_netto(t))
        rr = _f(t.get("rr"))
        if rr is not None and rr * factor < 1:
            onder_1 += 1

    return _uit_bedragen(bedragen, startkapitaal,
                         f"TP op {round(factor * 100)}%", "gemeten", {
        "factor": factor,
        "winnaars_geschaald": aangeraakt,
        "rr_onder_1": onder_1,
        "ondergrens": True,
    })


def tp_analyse(trades, startkapitaal, factor=None):
    reeks = [tp_scenario(trades, f, startkapitaal) for f in TP_FACTOREN]

    # Wat we WEL weten over de andere kant op: tp_verloop is jouw eigen log van
    # of prijs na je TP nog doorliep. Verder weg zetten kunnen we niet rekenen
    # (we weten niet hóe ver), maar dit telt wel of het signaal er is.
    verloop = {"precies": 0, "liep_door": 0, "te_vroeg": 0}
    for t in trades:
        v = (t.get("tp_verloop") or "").strip()
        if v in verloop:
            verloop[v] += 1
    n_verloop = sum(verloop.values())

    return {
        "reeks": reeks,
        "factoren": TP_FACTOREN,
        "gekozen": tp_scenario(trades, factor, startkapitaal) if factor else None,
        "verloop": verloop,
        "n_verloop": n_verloop,
        "min_n": MIN_N,
        "kader": (
            "Een winnaar is langs elk dichterbij TP-niveau gekomen, dus die schaalt mee — "
            "dat is meting. Van een verliezer weten we niet of een korter doel wél geraakt was; "
            "die blijft hier verliezer. Wat je hier ziet is dus een ONDERGRENS."
        ),
        "verder_weg": (
            f"Bij {verloop['liep_door']} van de {n_verloop} trades met ingevuld TP-verloop liep prijs "
            "door na je TP. Dat je daar rendement laat liggen is een signaal — maar hoevéél is niet "
            "te berekenen zonder te loggen hoe ver hij doorliep."
            if n_verloop else
            "Vul 'TP-verloop' in bij je trades. Zonder dat veld is er niets te zeggen over verder weg leggen."
        ),
    }


# =====================================================================
# 4. GEPROJECTEERD -- gemiste trades, met een band in plaats van een lijn
# =====================================================================

# Hoeveel "denkbeeldige" trades tegen je algemene winrate we bij een grade
# optellen voordat we die grade op zijn eigen cijfer geloven. Met drie A-trades
# die alle drie wonnen is de ruwe winrate 100%, en die 100% zou hier de aanname
# worden voor elke gemiste A-setup. Dat is geen schatting maar een spiegel voor
# je spijt. Deze verzachting trekt kleine steekproeven terug naar je eigen
# gemiddelde en verdwijnt vanzelf naarmate je meer per grade logt.
KRIMP = 5


def _winrate_per_grade(trades, algemeen_pct):
    per = {}
    for t in trades:
        per.setdefault(t.get("grade") or "?", []).append(t)
    uit = {}
    for g, rij in per.items():
        n = len(rij)
        w = len([t for t in rij if _gewonnen(t)])
        ruw = round(100 * w / n) if n else 0
        # Beta-verzachting richting je algemene winrate.
        verzacht = (w + KRIMP * algemeen_pct / 100) / (n + KRIMP) * 100
        uit[g] = {
            "n": n, "winnaars": w,
            "winrate": ruw,
            "winrate_verzacht": round(verzacht, 1),
            "verzacht": n < KRIMP * 2,       # bij genoeg data is ruw = verzacht bijna gelijk
            "wilson": simulatie.wilson(w, n),
        }
    return uit


def _aanname_voor(t, per_grade, algemeen, modus, eigen):
    """
    Welke winrate nemen we aan voor een trade die nooit gebeurd is?

    'grade'         -- de winrate van je eigen trades met dezelfde grade, maar
                       verzacht richting je algemene winrate zolang die grade
                       weinig trades heeft. Drie A-setups die alle drie wonnen
                       zijn geen bewijs dat A-setups altijd winnen.
    'conservatief'  -- de ondergrens van het 95%-interval. Bij tien trades is die
                       ondergrens laag, en dat hóórt zo.
    'eigen'         -- jij schuift zelf. Handig om te zien hoe hoog de winrate zou
                       moeten zijn voordat een scenario kantelt.
    """
    g = t.get("grade") or "?"
    if modus == "eigen":
        return float(eigen), f"jouw aanname ({eigen:.0f}%)"
    info = per_grade.get(g)
    if not info or not info["n"]:
        return float(algemeen), f"je algemene winrate ({algemeen:.0f}%) — geen {g}-trades om op te leunen"
    if modus == "conservatief":
        return info["wilson"]["laag"], (
            f"ondergrens van het 95%-interval van je {g}-setups ({info['n']} stuks)")
    if info["verzacht"]:
        return info["winrate_verzacht"], (
            f"je {g}-setups staan op {info['winrate']}%, maar dat zijn er pas {info['n']}. "
            f"Verzacht naar {info['winrate_verzacht']:.0f}% richting je algemene winrate.")
    return float(info["winrate"]), f"winrate van je {g}-setups ({info['n']} stuks)"


def _projectie(genomen, kandidaten, startkapitaal, per_grade, algemeen,
               modus, eigen, label, sleutel):
    """
    Neem de echte trades en voeg de kandidaten toe op hun eigen datum.

    Drie lijnen, want één lijn zou hier een leugen zijn:
      verwacht  -- elke kandidaat draagt zijn verwachtingswaarde bij;
      best      -- ze winnen allemaal;
      slecht    -- ze verliezen allemaal.
    De echte uitkomst ligt ergens in die band, en de band is breed. Dat is het punt.
    """
    risico_terugval = _typisch_risico(genomen)
    charge = _typische_charge(genomen)

    samen = _sorteer(list(genomen) + list(kandidaten))
    verwacht, best, slecht = [], [], []
    detail = []

    for t in samen:
        if t.get("_kandidaat"):
            risico = _f(t.get("risk_eur")) or risico_terugval
            rr = _f(t.get("rr")) or 1.0
            w, uitleg = _aanname_voor(t, per_grade, algemeen, modus, eigen)
            p = max(0.0, min(1.0, w / 100))
            winst = risico * rr + charge
            verlies = -risico + charge
            verwacht.append(p * winst + (1 - p) * verlies)
            best.append(winst)
            slecht.append(verlies)
            detail.append({
                "id": t.get("id"), "datum": t.get("datum"),
                "grade": t.get("grade"), "rr": rr,
                "reden": t.get("skip_reden") or "",
                "reden_label": adherentie.SKIP_REDENEN.get(
                    (t.get("skip_reden") or "").strip(), {}).get("label", "geen reden ingevuld"),
                "aanname_pct": round(w, 1),
                "aanname_uitleg": uitleg,
                "winst_eur": round(winst, 2),
                "verlies_eur": round(verlies, 2),
                "verwacht_eur": round(p * winst + (1 - p) * verlies, 2),
            })
        else:
            b = _netto(t)
            verwacht.append(b); best.append(b); slecht.append(b)

    scen = _uit_bedragen(verwacht, startkapitaal, label, "geprojecteerd", {
        "key": sleutel,
        "n_kandidaten": len(kandidaten),
        "n_echt": len(genomen),
        "detail": detail,
    })
    scen["curve_best"] = _uit_bedragen(best, startkapitaal, label + " (alles raak)",
                                       "geprojecteerd")["curve"]
    scen["curve_slecht"] = _uit_bedragen(slecht, startkapitaal, label + " (alles mis)",
                                         "geprojecteerd")["curve"]
    scen["netto_best"] = round(sum(best), 2)
    scen["netto_slecht"] = round(sum(slecht), 2)

    # Wat deze setups zélf bijdragen, los van je echte resultaat. Zonder dit
    # onderscheid leest "2 setups" naast "netto 11,19" als "die twee leverden
    # 11,19 op", terwijl dat het totaal inclusief je bestaande trades is.
    basis_netto = round(sum(_netto(t) for t in genomen), 2)
    scen["basis_netto"] = basis_netto
    scen["bijdrage_verwacht"] = round(scen["netto_eur"] - basis_netto, 2)
    scen["bijdrage_best"] = round(scen["netto_best"] - basis_netto, 2)
    scen["bijdrage_slecht"] = round(scen["netto_slecht"] - basis_netto, 2)
    # De winrate van een projectie slaat nergens op als je hem als feit leest.
    scen["winrate_toelichting"] = (
        "Dit percentage bevat aangenomen uitkomsten en is dus geen gemeten winrate."
    )
    return scen


# De vier soorten, in de volgorde waarin ze op het scherm horen te staan.
# Bewust vooraan: dat is de enige groep die je goed deed, en die hoort niet
# onderaan weggestopt te worden onder de spijt.
GEMIST_BLOKKEN = [
    ("bewust", "Bewust overgeslagen",
     "Je woog hem en bleef weg. Wat heeft dat je bespaard?"),
    ("aarzeling", "Niet genomen uit twijfel",
     "Valide setup, en je durfde niet. Dit gaat over je hoofd."),
    ("uitvoering", "Gemist in de uitvoering",
     "Geen order neergelegd, te laat gezien, of niet achter je scherm."),
    ("markt", "Net misgelopen — geen fout",
     "Je order lag klaar op de juiste plek en de prijs kwam er net niet aan."),
    ("onbekend", "Reden niet ingevuld",
     "Zonder reden valt hier niets van te leren."),
]


def gemist(genomen, overgeslagen, startkapitaal, modus="grade", eigen=50.0):
    """
    Vier soorten "niet genomen", elk met een eigen projectie.

    Dit stond eerst als twee groepen: spijt tegenover discipline. Dat klopte
    niet. "Ik durfde niet", "ik legde geen order neer" en "mijn order werd net
    niet gevuld" zijn drie verschillende dingen, en alleen de eerste twee zijn
    iets wat jij anders had kunnen doen.

    Die laatste categorie is de belangrijkste toevoeging. Een order die klaarlag
    en 3 pips misliep is geen gemiste kans die je jezelf mag aanrekenen -- je
    plan klopte en je uitvoering klopte. Zet je die op één hoop met de rest, dan
    telt het journal jouw goede uitvoering als een fout, en ga je je entry
    verschuiven om iets te repareren wat niet stuk was.
    """
    algemeen = (round(100 * len([t for t in genomen if _gewonnen(t)]) / len(genomen))
                if genomen else 50)
    per_grade = _winrate_per_grade(genomen, algemeen)
    basis = round(sum(_netto(t) for t in genomen), 2)

    def markeer(rij):
        return [{**t, "_kandidaat": True} for t in rij]

    groepen = {k: [] for k, _, _ in GEMIST_BLOKKEN}
    for t in overgeslagen:
        groepen[adherentie.soort_van(t.get("skip_reden"))].append(t)

    uit = {
        "per_grade": per_grade,
        "algemene_winrate": algemeen,
        "modus": modus,
        "eigen": eigen,
        "basis_netto": basis,
        "n_overgeslagen": len(overgeslagen),
        "min_n": MIN_N,
        "blokken": [],
        "soorten": adherentie.SKIP_SOORTEN,
        "kader": (
            "Dit is de enige plek in het platform waar met onbekende uitkomsten gerekend wordt. "
            "Een setup die je niet nam heeft geen resultaat — hij is niet gebeurd. Daarom staat er "
            "een band en geen lijn: bovenin winnen ze allemaal, onderin verliezen ze allemaal. "
            "Hoe breder die band, hoe minder dit scenario je te vertellen heeft."
        ),
    }

    for sleutel, titel, uitleg in GEMIST_BLOKKEN:
        rij = groepen[sleutel]
        if not rij:
            continue
        scen = _projectie(genomen, markeer(rij), startkapitaal, per_grade,
                          algemeen, modus, eigen, "Mét: " + titel.lower(), sleutel)
        info = adherentie.SKIP_SOORTEN[sleutel]
        uit["blokken"].append({
            **scen,
            "titel": titel,
            "uitleg": uitleg,
            "soort_uitleg": info["uitleg"],
            "fout": info["fout"],
            "n_valide": len([t for t in rij if t.get("grade") in ("A", "B")]),
        })
        uit[sleutel] = scen        # ook los bereikbaar

    if overgeslagen:
        uit["alles"] = _projectie(genomen, markeer(list(overgeslagen)), startkapitaal,
                                  per_grade, algemeen, modus, eigen,
                                  "Mét álles wat je zag", "alles")

    uit["oordeel"] = _gemist_oordeel(uit, groepen, basis)
    return uit


def _gemist_oordeel(uit, groepen, basis):
    """
    Eén alinea in gewone taal. De volgorde is bewust: eerst wat je goed deed,
    dan wat je jezelf mag aanrekenen, dan wat niet jouw schuld was. Andersom
    lezen mensen alleen de spijt.
    """
    delen = []

    d = uit.get("bewust")
    if d:
        effect = d["bijdrage_verwacht"]
        n = len(groepen["bewust"])
        if effect < 0:
            delen.append(f"Je bleef bewust weg bij {n} setups; die hadden je naar verwachting "
                         f"{abs(effect):.2f} euro gekost. Dat is wat je regel je opleverde.")
        else:
            delen.append(f"Je bleef bewust weg bij {n} setups die naar verwachting "
                         f"{effect:+.2f} euro hadden opgeleverd. Op deze steekproef kostte je regel "
                         f"je dus geld — te weinig data om 'm te wijzigen, wel om te volgen.")

    eigen_schuld = []
    for k, naam in (("aarzeling", "uit twijfel"), ("uitvoering", "in de uitvoering")):
        s = uit.get(k)
        if s:
            eigen_schuld.append(f"{len(groepen[k])} {naam} ({s['bijdrage_verwacht']:+.2f})")
    if eigen_schuld:
        totaal = sum(uit[k]["bijdrage_verwacht"] for k in ("aarzeling", "uitvoering") if k in uit)
        delen.append(f"Zelf laten liggen: {', en '.join(eigen_schuld)} — samen naar verwachting "
                     f"{totaal:+.2f} euro. Dit is het deel waar je iets aan kunt doen.")

    m = uit.get("markt")
    if m:
        n = len(groepen["markt"])
        delen.append(f"Daarnaast liep je order {n} keer net mis ({m['bijdrage_verwacht']:+.2f}). "
                     f"Daar deed je niets verkeerd" +
                     (" — maar twee keer is genoeg om je entry-niveau eens tegen het licht te houden."
                      if n >= 2 else "."))

    return " ".join(delen)


# =====================================================================
# Alles bij elkaar
# =====================================================================

def betrouwbaarheid(trades):
    """
    De rem op dit hele scherm. Bij tien trades is elk scenario hier een
    anekdote met een grafiek eromheen, en dat moet bovenaan staan -- niet
    weggestopt in een voetnoot.
    """
    n = len(trades)
    w = len([t for t in trades if _gewonnen(t)])
    interval = simulatie.wilson(w, n)
    if n < MIN_N:
        niveau, tekst = "ruis", (
            f"{n} trades. Hier valt niets te vergelijken — elk scenario hieronder verandert "
            "compleet zodra je er één trade bij logt.")
    elif n < MIN_N_OORDEEL:
        niveau, tekst = "indicatie", (
            f"{n} trades, en je winrate ligt ergens tussen {interval['laag']:.0f}% en "
            f"{interval['hoog']:.0f}%. Dat interval is breder dan het verschil tussen bijna alle "
            f"scenario's hieronder. Gebruik dit om te zien wat je moet mèten, niet om je regels "
            f"te veranderen — dat mag vanaf ongeveer {MIN_N_OORDEEL} trades.")
    else:
        niveau, tekst = "bruikbaar", (
            f"{n} trades, winrate tussen {interval['laag']:.0f}% en {interval['hoog']:.0f}%. "
            "Scenario's die verder uit elkaar liggen dan dat interval zeggen iets.")
    return {"n": n, "niveau": niveau, "tekst": tekst, "winrate": interval,
            "min_n": MIN_N, "min_n_oordeel": MIN_N_OORDEEL}


def datakwaliteit(trades):
    """Waarop rust dit? Zonder dit blok is de rest van het scherm niet te wegen."""
    def telveld(veld):
        return len([t for t in trades if (t.get(veld) not in (None, ""))])

    n = len(trades)
    herkomsten = [_risk_eur(t)[1] for t in trades]
    return {
        "n": n,
        "risico_gemeten": herkomsten.count("gemeten"),
        "risico_afgeleid": herkomsten.count("afgeleid"),
        "risico_terugval": herkomsten.count("terugval"),
        "sweep_gemeten": telveld("sweep_overshoot_points"),
        "sl_gemeten": telveld("sl_afstand_points"),
        "tp_gemeten": telveld("tp_afstand_points"),
        "sl_dan_tp": telveld("sl_dan_tp"),
        "minuten_in_hourly": telveld("minuten_in_hourly"),
        "shift_kwaliteit": telveld("shift_kwaliteit"),
        "tp_verloop": telveld("tp_verloop"),
        "grootste_gat": _grootste_gat(trades),
    }


def _grootste_gat(trades):
    """Welk ontbrekend veld blokkeert hier het meeste? Eén concrete aanwijzing."""
    n = len(trades)
    if not n:
        return ""
    gaten = [
        ("sweep_overshoot_points", "de sweep-overshoot", "dan werkt de SL-schuif over al je trades"),
        ("tp_afstand_points", "de TP-afstand in points", "dan kan de RR per scenario echt uitgerekend worden"),
        ("sl_dan_tp", "'daarna alsnog TP'", "dan kan een verliezer in een ruimer scenario winnaar worden"),
        ("minuten_in_hourly", "de minuut in de hourly", "dan werkt het timingfilter"),
    ]
    for veld, naam, gevolg in gaten:
        ingevuld = len([t for t in trades if (t.get(veld) not in (None, ""))])
        if ingevuld < n:
            return (f"{n - ingevuld} van je {n} trades missen {naam}. Vul dat aan, {gevolg}.")
    return ""


def analyse(trades, overgeslagen, startkapitaal, van="11:00", tot="12:00",
            sl_points=None, tp_factor=None, aanname="grade", eigen_winrate=50.0):
    return {
        "betrouwbaarheid": betrouwbaarheid(trades),
        "datakwaliteit": datakwaliteit(trades),
        "herrekening": herrekening(trades, startkapitaal, van, tot),
        "sl": sl_analyse(trades, startkapitaal, sl_points),
        "tp": tp_analyse(trades, startkapitaal, tp_factor),
        "gemist": gemist(trades, overgeslagen, startkapitaal, aanname, eigen_winrate),
        "startkapitaal": round(float(startkapitaal or 0), 2),
        "venster": {"van": van, "tot": tot},
        "herkomst_uitleg": {
            "herrekend": "Je eigen trades, opnieuw opgeteld. De uitkomsten zijn bekend.",
            "gemeten": "Contrafeitelijk, maar afgeleid uit wat je zelf gemeten hebt.",
            "geprojecteerd": "De uitkomst is onbekend en aangenomen. Lees dit als een band, niet als een cijfer.",
        },
    }
