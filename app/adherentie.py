"""
Regel-adherentie en gemiste setups (fase 11.1 en 11.2).

11.1 — Het percentage trades waarbij je je eigen regels volgde, met bandindeling,
       plus de vergelijking die er echt toe doet: presteren de trades waarbij je je
       regels volgde beter dan de trades waarbij je ze brak?

11.2 — Niet elke overgeslagen setup is hetzelfde. Een C laten lopen is discipline.
       Een A of B laten lopen uit twijfel is een fout, en meestal een dure.

Beide gebruiken edge.r_van_trade, zodat er nooit twee waarheden ontstaan.
"""

from . import cbr, edge

# Codes die zeggen: hier heb je je eigen regels gebroken.
# (D1/D2/D3 gaan over journallen, niet over de trade zelf -- die tellen niet mee.)
REGELBREKERS = {
    "E4": "buiten het tijdvenster",
    "E5": "C-setup geforceerd",
    "E7": "late entry, buiten de 50%-zone",
    "R1": "SL in de sweep-zone",
    "R3": "RR onder de vloer van 1",
    "R4": "verkeerde positiegrootte",
    "M2": "SL verschoven tegen de regels",
    "P1": "revenge",
    "P2": "overtrading",
    "P3": "verveling-entry",
    "P4": "size-up na winst",
    "D4": "geen pre-trade plan",
}

BANDEN = [
    (85, "elite-discipline", "goed",
     "Houd dit vast. Wekelijks meten is genoeg."),
    (75, "sterke discipline", "goed",
     "Bijna. Pak de één overtreding die het vaakst terugkomt."),
    (60, "op weg", "let-op",
     "Solide vooruitgang. Richt je op je vaakste overtreding, niet op alles tegelijk."),
    (0, "het systeem klopt niet", "slecht",
     "Onder de 60% is het advies niet 'meer discipline'. Snoei je regels terug tot er "
     "drie overblijven die je wél volgt."),
]


def _band(pct):
    for drempel, label, kleur, advies in BANDEN:
        if pct >= drempel:
            return {"label": label, "kleur": kleur, "advies": advies, "drempel": drempel}
    return BANDEN[-1]


def _codes(t):
    return {c.strip() for c in (t.get("foutcodes") or "").split(",") if c.strip()}


def beoordeel(t):
    """
    Volgde deze trade de regels? Geeft (bool, lijst met redenen waarom niet).
    Drie toetsen: de checklist zelf, de harde RR-vloer, en de foutcodes die
    over discipline gaan.
    """
    redenen = []
    if t.get("grade") == "C":
        redenen.append("grade C — de checklist zei: geen trade")
    rr = t.get("rr")
    if rr is not None and rr < 1:
        redenen.append(f"RR {rr} onder de vloer van 1")
    for code in sorted(_codes(t) & set(REGELBREKERS)):
        redenen.append(f"{code} — {REGELBREKERS[code]}")
    return (not redenen), redenen


def analyse(trades):
    trades = [t for t in trades if (t.get("status") or "genomen") == "genomen"]
    n = len(trades)

    gevolgd, gebroken = [], []
    reden_telling = {}
    for t in trades:
        ok, redenen = beoordeel(t)
        (gevolgd if ok else gebroken).append(t)
        for r in redenen:
            reden_telling[r] = reden_telling.get(r, 0) + 1

    pct = round(100 * len(gevolgd) / n) if n else 0
    band = _band(pct)

    g = edge._groep(gevolgd)
    b = edge._groep(gebroken)

    def _pf(rij):
        winst = sum(edge._netto(t) for t in rij if edge._netto(t) > 0)
        verlies = abs(sum(edge._netto(t) for t in rij if edge._netto(t) < 0))
        return round(winst / verlies, 2) if verlies > 0 else None

    top = sorted(reden_telling.items(), key=lambda x: -x[1])

    return {
        "n": n,
        "n_gevolgd": len(gevolgd),
        "n_gebroken": len(gebroken),
        "pct": pct,
        "band": band,
        "gevolgd": {**g, "profit_factor": _pf(gevolgd)},
        "gebroken": {**b, "profit_factor": _pf(gebroken)},
        "verschil_expectancy": round(g["expectancy_r"] - b["expectancy_r"], 3),
        "redenen": [{"reden": r, "aantal": a} for r, a in top[:8]],
        "regelbrekers": REGELBREKERS,
        "genoeg_data": n >= 10,
    }


# ---------- 11.2 Gemiste setups ----------

# ---------- waarom een setup niet genomen is ----------
#
# "Overgeslagen" is geen enkele categorie, en ze op één hoop gooien laat het
# journal twee kanten op liegen. Een setup waar je bewust van wegbleef is een
# overwinning. Een setup waar je uit angst van wegbleef is een lek. Een setup
# die je miste omdat je er niet was, is een routineprobleem. En een setup waar
# je order gewoon net niet gevuld werd is HELEMAAL GEEN FOUT -- je plan klopte,
# je order lag klaar, de markt kwam alleen niet naar je toe.
#
# Dat laatste onderscheid is het belangrijkste, want zonder die categorie wordt
# elke niet-gevulde order geboekt als iets wat je verkeerd deed. Dan ga je je
# entry verschuiven om een "fout" op te lossen die je niet gemaakt hebt.

SKIP_SOORTEN = {
    "bewust": {
        "label": "Bewust overgeslagen",
        "kort": "bewust",
        "fout": False,
        "uitleg": "Je zag hem, je woog hem, je bleef weg. Dit is je discipline aan het werk.",
    },
    "aarzeling": {
        "label": "Niet genomen uit twijfel",
        "kort": "aarzeling",
        "fout": True,
        "uitleg": "Je zag een valide setup en durfde niet. Dit is de enige categorie die over "
                  "je hoofd gaat, en meestal de duurste.",
    },
    "uitvoering": {
        "label": "Gemist in de uitvoering",
        "kort": "uitvoering",
        "fout": True,
        "uitleg": "De setup was er, jouw uitvoering niet: geen order neergelegd, te laat gezien, "
                  "of niet achter je scherm. Dit los je op met routine, niet met je model.",
    },
    "markt": {
        "label": "Net misgelopen",
        "kort": "markt",
        "fout": False,      # nadrukkelijk GEEN fout
        "uitleg": "Je order lag klaar op de juiste plek en de prijs kwam er net niet. Hier heb "
                  "je niets verkeerd gedaan. Gebeurt dit vaak, dan is je entry-niveau het "
                  "gesprek waard — niet je discipline.",
    },
    "onbekend": {
        "label": "Reden niet ingevuld",
        "kort": "onbekend",
        "fout": None,
        "uitleg": "Zonder reden valt er niets van te leren. Vul 'm alsnog in.",
    },
}

SKIP_REDENEN = {
    "regels": {"label": "de checklist zei nee", "soort": "bewust", "fout": False,
               "uitleg": "Precies waar de checklist voor is. Dit is discipline-winst."},
    "buiten_venster": {"label": "buiten het tijdvenster", "soort": "bewust", "fout": False,
                       "uitleg": "Buiten het 2e uur Londen is wegblijven de regel."},

    "twijfel": {"label": "twijfel — durfde niet", "soort": "aarzeling", "fout": True,
                "uitleg": "De setup was valide, maar je durfde niet. Dit kost geld."},

    "geen_order": {"label": "geen order neergelegd", "soort": "uitvoering", "fout": True,
                   "uitleg": "Je zag de setup maar legde niets neer, en toen liep hij weg. "
                             "Een limit order op je niveau haalt dit weg."},
    "te_laat": {"label": "te laat gezien", "soort": "uitvoering", "fout": True,
                "uitleg": "Je was er niet op tijd bij. Vaak een routine-probleem, geen setup-probleem."},
    "niet_aan_scherm": {"label": "niet aan het scherm", "soort": "uitvoering", "fout": True,
                        "uitleg": "De setup was er, jij niet. Dit los je op met je agenda, niet met je model."},

    "order_niet_gevuld": {"label": "order net niet gevuld", "soort": "markt", "fout": False,
                          "uitleg": "Je order stond klaar en de prijs kwam er net niet aan. Geen fout — "
                                    "wel iets om te tellen: als dit blijft gebeuren zegt dat iets over "
                                    "je entry-niveau."},

    "anders": {"label": "andere reden", "soort": "onbekend", "fout": None, "uitleg": ""},
}


def soort_van(skip_reden):
    """Welke van de vier soorten hoort bij deze reden?"""
    return SKIP_REDENEN.get((skip_reden or "").strip(), {}).get("soort", "onbekend")


def gemist(overgeslagen, gevolgd_expectancy_r):
    """
    Splitst de overgeslagen setups naar de vier soorten.

    De vraag "wat heb ik gemist?" heeft geen enkel antwoord. Wegblijven omdat je
    regel het zei is winst. Wegblijven uit angst is een lek. Er niet zijn is een
    routineprobleem. En een order die net niet vult is geen van drieën -- daar
    ging niets mis, de markt kwam alleen niet.

    Alleen de aarzeling- en uitvoeringsgroep tellen mee als gemiste kans, en
    zelfs die schatting is nadrukkelijk een schatting: we weten niet wat die
    trade gedaan zou hebben, alleen wat een gemiddelde valide setup oplevert.
    """
    groepen = {k: [] for k in SKIP_SOORTEN}
    for t in overgeslagen:
        groepen[soort_van(t.get("skip_reden"))].append(t)

    valide = lambda rij: [t for t in rij if t.get("grade") in ("A", "B")]

    # Wat je écht liet liggen: valide setups waar jij de oorzaak was.
    gemiste = valide(groepen["aarzeling"]) + valide(groepen["uitvoering"])
    # Onbekend telt alleen mee als de setup valide was -- anders weten we niets.
    gemiste += valide(groepen["onbekend"])
    discipline = groepen["bewust"]
    niet_jouw_schuld = groepen["markt"]

    per_reden = {}
    for t in overgeslagen:
        r = (t.get("skip_reden") or "").strip() or "anders"
        per_reden[r] = per_reden.get(r, 0) + 1

    geschat_r = round(len(gemiste) * max(gevolgd_expectancy_r, 0), 2)

    def kaart(t):
        reden = (t.get("skip_reden") or "").strip()
        return {"id": t.get("id"), "datum": t.get("datum"), "grade": t.get("grade"),
                "reden": reden, "soort": soort_van(reden), "rr": t.get("rr")}

    return {
        "n_overgeslagen": len(overgeslagen),
        "n_discipline": len(discipline),
        "n_gemist": len(gemiste),
        "n_markt": len(niet_jouw_schuld),
        "per_soort": [{
            "soort": k, **SKIP_SOORTEN[k],
            "n": len(rij),
            "n_valide": len(valide(rij)),
        } for k, rij in groepen.items() if rij],
        "geschat_r": geschat_r,
        "per_reden": [{"reden": r, "label": SKIP_REDENEN.get(r, {}).get("label", "geen reden ingevuld"),
                       "soort": soort_van(r), "aantal": a}
                      for r, a in sorted(per_reden.items(), key=lambda x: -x[1])],
        "gemiste": [kaart(t) for t in sorted(gemiste, key=lambda x: (x.get("datum") or ""),
                                             reverse=True)[:8]],
        "markt": [kaart(t) for t in sorted(niet_jouw_schuld, key=lambda x: (x.get("datum") or ""),
                                           reverse=True)[:8]],
        "markt_signaal": (
            f"{len(niet_jouw_schuld)} keer lag je order klaar en kwam de prijs er net niet aan. "
            "Daar heb je niets fout gedaan. Maar als dit vaker gebeurt, is dat data over je "
            "entry-niveau — niet over je discipline."
            if len(niet_jouw_schuld) >= 2 else ""
        ),
        "redenen_lijst": SKIP_REDENEN,
        "soorten_lijst": SKIP_SOORTEN,
    }
