"""
CBR-model: constanten, criteria en de auto-grade-logica.

De grade volgt ALTIJD uit de checklist -- nooit uit onderbuik.
Dit is de discipline-check die de rest van het platform afdwingt.
"""

# Interne waarden voor de criteria. Frontend toont ze als V / ? / X.
VAL_YES = "yes"      # V
VAL_MAYBE = "maybe"  # ?
VAL_NO = "no"        # X
VALID_VALUES = {VAL_YES, VAL_MAYBE, VAL_NO}

SYMBOL = {VAL_YES: "✓", VAL_MAYBE: "?", VAL_NO: "✗"}  # ✓ ? ✗

# =====================================================================
# FASE 1 (t/m 10 sep 2026) -- het oude model: sweep een high of low, draai
# erop. Bewaard zodat de 20 gearchiveerde trades hun grade houden.
# =====================================================================
CRITERIA_F1 = [
    {"key": "crit1_conditie", "num": 1, "critical": True,
     "title": "Trending range met 2+ legs",
     "help": "GEEN schone trend. Nooit reversals in een lopende trend."},
    {"key": "crit2_sweep", "num": 2, "critical": True,
     "title": "Overextensie sweept vorige 1H high/low",
     "help": "Externe liquiditeit: de vorige 1H high of low moet gesweept zijn."},
    {"key": "crit3_shift", "num": 3, "critical": True,
     "title": "Type-3 shift (beide kanten geraakt)",
     "help": "High dan low of andersom. Geen enkele BOS."},
    {"key": "crit4_entry", "num": 4, "critical": False,
     "title": "Entry op 50% van de shift",
     "help": "Kwaliteitscriterium, niet-kritisch."},
    {"key": "crit5_tp", "num": 5, "critical": False,
     "title": "TP op 50% van de extensie, RR >= 1",
     "help": "RR >= 1 is de harde vloer. Winrate-first: 1:1 is prima."},
]

# =====================================================================
# FASE 2 (vanaf 11 sep 2026) -- bias eerst.
#
# Wat er veranderde: in fase 1 werd elke gesweepte high of low als setup
# gelezen en werd er tegenin gehandeld, zonder richting van boven. Dat is
# precies waar de reeks van 9-10 sep op stukliep. Nu bepaalt de 1H-trend
# eerst de RICHTING, en pas daarna zoek je de tegenbeweging die die richting
# weer oppakt: bullish bias -> wacht op een sweep omlaag -> shift omhoog.
#
# Acht criteria, waarvan vijf kritisch.
# =====================================================================
CRITERIA_F2 = [
    {"key": "f2_bias", "num": 1, "critical": True,
     "title": "1H-bias bepaald en trade volgt die richting",
     "help": "Bullish 1H -> alleen longs. Bearish 1H -> alleen shorts. "
             "Uitzoomen: de hogere timeframe geeft de richting, niet de sweep."},
    {"key": "f2_dxy", "num": 2, "critical": True,
     "title": "DXY correleert invers",
     "help": "Goud bullish hoort samen te gaan met een bearish dollar. "
             "Bewegen ze in eenheid, dan sla je over -- tenzij het echt A+ is."},
    {"key": "f2_expansie", "num": 3, "critical": True,
     "title": "20+ min expansie zonder pullbacks",
     "help": "Prijs moet minstens twintig minuten eenzijdig uitbreiden. "
             "Zonder die expansie is er geen onbalans om op te handelen."},
    {"key": "f2_sweep", "num": 4, "critical": True,
     "title": "Sweep van het 1e sessie-uur of rebalance",
     "help": "Bullish bias -> de low van het 1e uur gesweept. Bearish -> de high. "
             "Alternatief: prijs rebalanceert een recente trending move."},
    {"key": "f2_shift", "num": 5, "critical": True,
     "title": "Type-3 shift terug in de biasrichting",
     "help": "Market structure shift met een body-close, en wel de kant op "
             "die je 1H-bias aangeeft. Tegen de bias in is continuatie, geen setup."},
    {"key": "f2_entry", "num": 6, "critical": False,
     "title": "Entry op 50% van de shift-beweging",
     "help": "Kwaliteitscriterium. Geen retrace = geen entry; dat kost je "
             "ongeveer 30% van de setups en dat hoort zo."},
    {"key": "f2_sl", "num": 7, "critical": False,
     "title": "SL op het extreme van de type-3 shift",
     "help": "Het verste punt van de shift-beweging, achter de sweep. "
             "Niet krapper -- dan zit je binnen de liquidity grab."},
    {"key": "f2_tp", "num": 8, "critical": False,
     "title": "TP op rebalance / minimaal 1,5R",
     "help": "50% equilibrium van de expansiebeweging, het dichtstbijzijnde "
             "structuurniveau boven 1,5R, of ruimer als je bias sterk is."},
]

# Het actieve model. Alles wat 'de criteria' opvraagt krijgt fase 2.
CRITERIA = CRITERIA_F2

CRITICAL_KEYS = [c["key"] for c in CRITERIA if c["critical"]]
QUALITY_KEYS = [c["key"] for c in CRITERIA if not c["critical"]]
ALL_CRIT_KEYS = [c["key"] for c in CRITERIA]

F1_CRITICAL = [c["key"] for c in CRITERIA_F1 if c["critical"]]
F1_ALL = [c["key"] for c in CRITERIA_F1]

FASE_ACTIEF = 2
FASE_NAAM = {1: "Fase 1 -- sweep-en-draai (archief)",
             2: "Fase 2 -- bias eerst"}


def criteria_voor(fase) -> list:
    return CRITERIA_F1 if int(fase or 2) == 1 else CRITERIA_F2


def compute_grade(values: dict) -> str:
    """Fase 1. Ongewijzigd -- de archieftrades houden hun grade."""
    critical = [values.get(k) for k in F1_CRITICAL]
    if any(v in (VAL_NO, VAL_MAYBE) for v in critical):
        return "C"
    if all(values.get(k) == VAL_YES for k in F1_ALL):
        return "A"
    return "B"


def compute_grade_f2(values: dict) -> str:
    """
    Fase 2: vijf kritische criteria, drie kwaliteitscriteria.

    kritisch op X of ?   -> C ("dit was geen trade")
    alle acht V          -> A
    vijf kritische V     -> B
    """
    critical = [values.get(k) for k in CRITICAL_KEYS]
    if any(v in (VAL_NO, VAL_MAYBE) for v in critical):
        return "C"
    if all(values.get(k) == VAL_YES for k in ALL_CRIT_KEYS):
        return "A"
    return "B"


def grade_voor(values: dict, fase=None) -> str:
    """Kiest de juiste gradeberekening op basis van de fase van de trade."""
    f = int(fase if fase is not None else values.get("fase") or FASE_ACTIEF)
    return compute_grade(values) if f == 1 else compute_grade_f2(values)


def is_no_trade(grade: str) -> bool:
    """Grade C betekent: dit was geen trade."""
    return grade == "C"


# =====================================================================
# Ronde 2 -- de sweep meten in plaats van erover praten.
#
# Twee van de eerste acht trades verloren op dezelfde manier: SL geraakt met
# een minimale marge, waarna prijs alsnog het TP-niveau haalde. De SL zat dus
# BINNEN de sweep. Dat is geen pech en ook geen te krappe SL in het algemeen --
# het is een meetbaar plaatsingsprobleem, en dus loggen we het.
# =====================================================================

POINT = 0.10          # 1 point = 0,10 in prijs. 0,30 boven de high = 3 points.


def prijs_naar_points(verschil: float) -> float:
    """0,30 in prijs -> 3,0 points."""
    return round(float(verschil) / POINT, 2)


def points_naar_prijs(points: float) -> float:
    """3,0 points -> 0,30 in prijs."""
    return round(float(points) * POINT, 4)


def sl_marge(trade: dict):
    """
    sl_afstand_points - sweep_overshoot_points.

    Negatief = je SL lag binnen de sweep en werd dus meegenomen door precies
    de beweging waar je setup op gebouwd is. Geeft None zolang een van beide
    velden leeg is -- liever niets tonen dan een cijfer verzinnen.
    """
    sl = trade.get("sl_afstand_points")
    ov = trade.get("sweep_overshoot_points")
    if sl is None or ov is None:
        return None
    try:
        return round(float(sl) - float(ov), 2)
    except (TypeError, ValueError):
        return None


# Een type-3 shift is niet binair (ontdekt bij trade 8). Deze schaal staat
# NAAST crit3_shift -- die blijft gewoon V / ? / X.
SHIFT_KWALITEIT = [
    {"key": "duidelijk",   "label": "duidelijk",   "goed": True},
    {"key": "soft",        "label": "soft",        "goed": False},
    {"key": "onduidelijk", "label": "onduidelijk", "goed": False},
]
SHIFT_KWALITEIT_KEYS = {o["key"] for o in SHIFT_KWALITEIT}

# Waarnemening die bij de shift-kwaliteit hoort, als tooltip in het formulier.
SHIFT_TOOLTIP = ("Stijgt prijs te lang en te snel vóór de return, dan wordt de "
                 "shift zachter en minder duidelijk.")

# Pre-condities uit je eigen notitieboek: je past ze toe, maar ze stonden
# nergens gelogd -- dus kon niemand zien of ze verlies voorspellen.
VOLUME_OPTIES = [
    {"key": "ja",  "label": "hoog",   "goed": True},
    {"key": "nee", "label": "laag",   "goed": False},
]
OVEREXTENSIE_OPTIES = [
    {"key": "goed",   "label": "goed",   "goed": True},
    {"key": "slecht", "label": "slecht", "goed": False},
]
VOLUME_KEYS = {o["key"] for o in VOLUME_OPTIES}
OVEREXTENSIE_KEYS = {o["key"] for o in OVEREXTENSIE_OPTIES}


# Grade-integriteit. Bij trade 8 werd een softe shift bijna als V gelogd,
# terwijl het feitelijk een ? was. De grade moet uit de checklist volgen en
# niet uit de uitkomst -- anders wordt dezelfde softe shift bij winst een B
# en bij verlies een C.
TWIJFELWOORDEN = [
    "soft", "niet heel duidelijk", "niet echt", "twijfel", "twijfelde",
    "onduidelijk", "niet duidelijk", "vaag", "matig", "zwak", "net aan",
    "niet overtuigend", "niet super",
]


def twijfel_in_tekst(*teksten) -> list:
    """Welke twijfelwoorden staan er in de notities? Leeg = geen signaal."""
    hooi = " ".join((t or "") for t in teksten).lower()
    return [w for w in TWIJFELWOORDEN if w in hooi]


# Emotie-chips (fase 9.3). Klikken in plaats van typen: een halve seconde werk,
# en het levert data op waar je later op kunt filteren. Vrije tekst doet dat niet.
EMOTIES = [
    {"key": "rustig",      "label": "rustig",      "goed": True},
    {"key": "scherp",      "label": "scherp",      "goed": True},
    {"key": "geduldig",    "label": "geduldig",    "goed": True},
    {"key": "gehaast",     "label": "gehaast",     "goed": False},
    {"key": "twijfelend",  "label": "twijfelend",  "goed": False},
    {"key": "overmoedig",  "label": "overmoedig",  "goed": False},
    {"key": "revenge",     "label": "revenge",     "goed": False},
    {"key": "verveeld",    "label": "verveeld",    "goed": False},
    {"key": "moe",         "label": "moe",         "goed": False},
    {"key": "afgeleid",    "label": "afgeleid",    "goed": False},
]

EMOTIE_KEYS = {e["key"] for e in EMOTIES}


# Voorbereiding vóór de sessie (fase 14.2). Vijf handelingen die je regels al
# voorschrijven, maar die tot nu toe nergens als handeling stonden.
VOORBEREIDING = [
    {"key": "levels", "label": "1H high en low getekend",
     "help": "Vóór de opening, zoals je notitieboek zegt.", "code": "D3"},
    {"key": "nieuws", "label": "Economische agenda gecheckt",
     "help": "Goud reageert hard op nieuws in het Londense uur.", "code": ""},
    {"key": "risk", "label": "Risk per trade bepaald",
     "help": "Vast bedrag, vóór je iets ziet.", "code": "R4"},
    {"key": "dagregels", "label": "Dagregels bevestigd",
     "help": "Hoeveel trades maximaal, en na hoeveel verliezers stop je.", "code": "P2"},
    {"key": "plan", "label": "Pre-trade plan: wat neem ik wél en wat niet",
     "help": "Eén zin is genoeg. Geen plan is geen trade.", "code": "D4"},
]

VOORBEREIDING_KEYS = [v["key"] for v in VOORBEREIDING]


# Foutentaxonomie -- vaste codes.
FOUTCODES = {
    "E": {
        "label": "Entry / setup",
        "codes": {
            "E1": "Entry zonder shift",
            "E2": "Conditie fout (trend als range)",
            "E3": "FOMO na overextensie",
            "E4": "Buiten tijdvenster",
            "E5": "C-setup geforceerd",
            "E6": "DXY genegeerd",
            "E7": "Late entry / buiten 50%-zone",
            "E8": "Shift zonder voorafgaande sweep van 1H H/L",
            "E9": "Tegen de 1H-bias in getraded",
            "E10": "Entry op de tweede pullback i.p.v. de eerste",
        },
    },
    "R": {
        "label": "Risk",
        "codes": {
            "R1": "SL op voor de hand liggend niveau / in sweep-zone",
            "R2": "SL te krap",
            "R3": "RR onder minimum",
            "R4": "Verkeerde positiegrootte",
        },
    },
    "M": {
        "label": "Management",
        "codes": {
            "M1": "Te vroeg gesloten",
            "M2": "SL verschoven tegen regels",
            "M3": "Handmatig gesloten uit angst",
            "M4": "Niet ingegrepen bij invalidatie",
        },
    },
    "P": {
        "label": "Psychologie",
        "codes": {
            "P1": "Revenge",
            "P2": "Overtrading",
            "P3": "Verveling-entry",
            "P4": "Size-up na winst",
        },
    },
    "D": {
        "label": "Discipline / data",
        "codes": {
            "D1": "Geen screenshot",
            "D2": "Journal niet ingevuld",
            "D3": "Levels niet vooraf getekend",
            "D4": "Geen pre-trade plan",
        },
    },
}

# Corrigerende regels per foutcode -- gebruikt in de foutenanalyse (fase 4).
CORRECTIES = {
    "E1": "Geen entry zonder bevestigde type-3 shift. Wacht op de shift.",
    "E2": "Onderscheid range van trend: tel de legs, check op 2+ legs.",
    "E3": "Overextensie = wachten, niet chasen. Laat de eerste beweging gaan.",
    "E4": "Handel alleen in het 2e uur van de Londense sessie.",
    "E5": "Als het een C is: niet nemen. De checklist beslist, niet je onderbuik.",
    "E6": "XAU-only, maar negeer een tegengestelde DXY niet als context.",
    "E7": "Entry alleen binnen de 50%-zone van de shift. Anders skip.",
    "E8": "Shift telt alleen na een sweep van de vorige 1H high/low.",
    "R1": "Plaats de SL niet in de sweep-zone / net boven de recente high.",
    "R2": "Geef de SL ademruimte, niet te krap onder ruis.",
    "R3": "RR onder 1 = geen trade. Harde vloer.",
    "R4": "Bereken positiegrootte op vast risico in EUR.",
    "M1": "Laat de trade lopen tot TP of SL. Niet vervroegd sluiten.",
    "M2": "Verschuif de SL niet tegen je eigen regels in.",
    "M3": "Angst is geen exit-signaal. Volg het plan.",
    "M4": "Grijp in zodra de setup invalideert, wacht niet af.",
    "P1": "Na verlies: stop of pauzeer. Geen revenge-trade.",
    "P2": "Max aantal setups per dag respecteren.",
    "P3": "Geen entry uit verveling. Geen setup = geen trade.",
    "P4": "Size niet op na een winst. Vast risico blijft vast.",
    "D1": "Maak altijd een pre-entry, entry en post-exit screenshot.",
    "D2": "Vul de journal dezelfde dag volledig in.",
    "D3": "Teken je levels voordat de sessie begint.",
    "D4": "Geen pre-trade plan = geen trade.",
}


def all_foutcodes_flat() -> dict:
    """Platte map code -> beschrijving voor validatie/weergave."""
    flat = {}
    for group in FOUTCODES.values():
        flat.update(group["codes"])
    return flat


# =====================================================================
# De mens-laag en de vangrails (ronde 3).
#
# De journal was sterk in data en zwak in discipline, staat en reflectie.
# Alles hieronder blijft bewust licht: op DAGniveau, drie klikken en één zin.
# Per trade een stemming bijhouden is een klus die je na een week laat vallen.
# =====================================================================

SESSIE_TOGGLES = [
    {"key": "in_venster", "label": "Alleen in mijn venster getraded",
     "help": "Het 2e uur van Londen. Buiten je uur is je edge niet gemeten.",
     "code": "E4"},
    {"key": "plan_gevolgd", "label": "Plan gevolgd, niets geforceerd",
     "help": "Geen setups gezocht die er niet waren, niet doorgetikt na een verlies.",
     "code": "P2"},
]

STATEN = [
    {"key": "rustig",  "label": "rustig",  "goed": True},
    {"key": "gehaast", "label": "gehaast", "goed": False},
    {"key": "moe",     "label": "moe",     "goed": False},
]
STAAT_KEYS = {s["key"] for s in STATEN}


def _naar_minuten(hhmm):
    """'10:30' -> 630. Geeft None bij rommel, want dan doen we geen uitspraak."""
    if not hhmm or ":" not in hhmm:
        return None
    try:
        u, m = hhmm.strip().split(":")[:2]
        return int(u) * 60 + int(m)
    except (ValueError, TypeError):
        return None


def binnen_venster(tijd_entry, van="10:00", tot="11:00"):
    """
    Valt deze entry in je tijdvenster? Alles in Amsterdamse tijd, want zo log jij.
    Londen = Amsterdam - 1 uur, dus het 2e Londense uur (09:00-10:00 Londen)
    is 10:00-11:00 bij jou op de klok.

    Geeft None als er geen tijd is -- geen tijd is geen overtreding, alleen
    ontbrekende data.
    """
    t = _naar_minuten(tijd_entry)
    if t is None:
        return None
    a, b = _naar_minuten(van), _naar_minuten(tot)
    if a is None or b is None:
        return None
    # 1 okt 2026: het venster bestaat uit meerdere blokken (Asia + 10-15). Krijgen we de
    # omhullende uit de config (01:00-15:00) binnen, dan gelden de echte blokken (09-10 dicht).
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import venster as _v
        bl = _v.blokken()
        if len(bl) > 1 and a == min(x for x, _ in bl) and b == max(z for _, z in bl):
            return _v.binnen(t)
    except Exception:
        pass
    return a <= t < b


def londense_tijd(tijd_entry):
    """De entrytijd omgerekend naar Londen, puur om te tonen."""
    t = _naar_minuten(tijd_entry)
    if t is None:
        return ""
    t = (t - 60) % (24 * 60)
    return f"{t // 60:02d}:{t % 60:02d}"
