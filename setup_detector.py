# -*- coding: utf-8 -*-
"""
setup_detector.py -- jouw entry-model als rekenwerk (23 sep 2026).

    1. Impuls      een schone, krachtige beweging in één richting
    2. Top         het uiterste van de impuls, gevolgd door een mini-pullback
    3. Sweep       prijs tikt voorbij die top (wick volstaat), binnen 10 candles
                   en hoogstens 30 points erdoorheen
    4. BOS         een candle SLUIT voorbij de low (high) van de mini-pullback
    5. Entry       50% tussen het sweep-extreme en de low (high) van de pullback
    6. SL / TP     SL 5 points voorbij het sweep-extreme, TP op 1:1
    Ongeldig       raakt prijs vóór de entry de 50% van de impuls, dan is de
                   impuls weg

Na een impuls OMHOOG zoek je een SHORT, na een impuls OMLAAG een LONG.
Geen 1H-bias, geen DXY: de richting volgt uit de impuls zelf.

Pure functies over candles -- geen MT5, geen netwerk, geen database -- zodat
exact dezelfde code live draait, in de replay en in de tests.

Een candle is (tijd, open, high, low, close); tijd mag alles zijn dat oploopt
(epoch-seconden, index, ...).
"""

from dataclasses import dataclass, asdict, field
from typing import List, Optional

STANDAARD = {
    "punt": 0.10,                 # 1 point = 0,10 in prijs (goud)
    "atr_periode": 14,
    "impuls_min_candles": 4,
    "impuls_max_candles": 30,
    "impuls_min_atr": 4.0,        # netto beweging >= 4x de gemiddelde candle
    "impuls_max_overlap": 0.45,   # gemiddelde overlap tussen opeenvolgende candles
    "impuls_min_efficientie": 0.6,  # netto body-beweging / som van alle bodies
    "top_geldig_candles": 10,     # de sweep moet binnen 10 candles na de top komen
    "sweep_max_points": 30,       # verder dan 30 points door de top = nieuwe impuls
    "bos_max_candles": 15,        # na de sweep: zo lang mag de BOS op zich laten wachten
    "entry_max_candles": 30,      # na de BOS: zo lang blijft de entry geldig
    "sl_marge_points": 5,         # jouw 0,5+ regel
    "rr": 1.0,                    # TP altijd op 1:1
    "eis_1h_break": True,         # de impuls moet de high/low van de vorige 1H-candle breken
    "eis_50_impuls": True,
    "eis_bos": True,              # False = geen break of structure nodig: entry direct na de sweep
    "bos_op_wick": False,         # True = een wick voorbij de pullback is genoeg (type 3 shift, Marijn 6 okt 2026); False = close
    "sweep_direct": False,        # True = de candle direct na de top mag de sweep zijn (pullback = de topcandle zelf)
    "entry_pct": 0.5,             # entry = pullback-niveau + pct x (sweep - pullback); 0.5 = midden, 0.3 = dichter bij de BOS        # 1 okt 2026: False = 50% van de impuls raken maakt de setup NIET meer ongeldig
}


def _t(c): return c[0]
def _o(c): return c[1]
def _h(c): return c[2]
def _l(c): return c[3]
def _c(c): return c[4]


def overlap_ratio(a, b) -> float:
    """Hoeveel twee opeenvolgende candles elkaar overlappen, 0..1 (t.o.v. de kleinste)."""
    over = max(0.0, min(_h(a), _h(b)) - max(_l(a), _l(b)))
    kleinste = min(_h(a) - _l(a), _h(b) - _l(b))
    if kleinste <= 0:
        return 1.0
    return min(1.0, over / kleinste)


def atr(bars: List, eind: int, periode: int) -> float:
    """Gemiddelde true range over de 'periode' candles VOOR index eind."""
    begin = eind - periode
    if begin < 1:
        return 0.0
    trs = []
    for k in range(begin, eind):
        h, l, pc = _h(bars[k]), _l(bars[k]), _c(bars[k - 1])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


# ---------------------------------------------------------------- 1. impuls

@dataclass
class Impuls:
    richting: str            # "up" of "down"
    i: int                   # eerste candle
    j: int                   # top-candle (uiterste)
    van: float               # low (up) of high (down) aan het begin
    tot: float               # high (up) of low (down) = de top
    netto: float
    candles: int
    overlap: float
    efficientie: float
    atr: float
    kracht: float            # netto / atr

    @property
    def eq(self):
        return (self.van + self.tot) / 2


def meet_leg(bars, i, j, richting, cfg):
    """Maatstaven van candles i..j als impuls in 'richting'. None als de vorm niet klopt."""
    leg = bars[i:j + 1]
    if richting == "up":
        if _l(bars[i]) > min(_l(c) for c in leg) or _h(bars[j]) < max(_h(c) for c in leg):
            return None
        van, tot = _l(bars[i]), _h(bars[j])
        netto = tot - van
        body_netto = _c(bars[j]) - _o(bars[i])
    else:
        if _h(bars[i]) < max(_h(c) for c in leg) or _l(bars[j]) > min(_l(c) for c in leg):
            return None
        van, tot = _h(bars[i]), _l(bars[j])
        netto = van - tot
        body_netto = _o(bars[i]) - _c(bars[j])
    if netto <= 0:
        return None
    som = sum(abs(_c(c) - _o(c)) for c in leg)
    eff = body_netto / som if som > 0 else 0.0
    ovs = [overlap_ratio(leg[k - 1], leg[k]) for k in range(1, len(leg))]
    ov = sum(ovs) / len(ovs) if ovs else 1.0
    a = atr(bars, i, cfg["atr_periode"])
    return Impuls(richting, i, j, van, tot, netto, len(leg), ov, eff, a,
                  (netto / a) if a > 0 else 0.0)


def is_goed(imp: Impuls, cfg) -> bool:
    return (imp.candles >= cfg["impuls_min_candles"]
            and imp.atr > 0
            and imp.kracht >= cfg["impuls_min_atr"]
            and imp.overlap <= cfg["impuls_max_overlap"]
            and imp.efficientie >= cfg["impuls_min_efficientie"])


def impuls_naar(bars, j, richting, cfg) -> Optional[Impuls]:
    """De beste impuls die op candle j zijn top heeft. Je 'alleen de impuls'-regel:
    we proberen elk beginpunt en houden de GROOTSTE die nog schoon is -- de basis
    ervoor telt dus niet mee."""
    beste = None
    lo = max(cfg["atr_periode"] + 1, j - cfg["impuls_max_candles"] + 1)
    for i in range(j - cfg["impuls_min_candles"] + 1, lo - 1, -1):
        imp = meet_leg(bars, i, j, richting, cfg)
        if imp is None or not is_goed(imp, cfg):
            continue
        if beste is None or imp.netto > beste.netto:
            beste = imp
    return beste


def vorige_1h_extreme(bars, imp):
    """(high, low) van de vorige VOLLE 1H-candle t.o.v. het uur waarin de impuls
    zijn top heeft. None als de tijd geen epoch-seconden is (bv. in de tests) of
    als er nog geen vorig uur in de data zit."""
    tt = _t(bars[imp.j])
    if not isinstance(tt, (int, float)) or isinstance(tt, bool):
        return None
    uur_start = (int(tt) // 3600) * 3600
    vorig0, vorig1 = uur_start - 3600, uur_start
    hs = [_h(c) for c in bars if isinstance(_t(c), (int, float)) and vorig0 <= int(_t(c)) < vorig1]
    ls = [_l(c) for c in bars if isinstance(_t(c), (int, float)) and vorig0 <= int(_t(c)) < vorig1]
    if not hs:
        return None
    return max(hs), min(ls)


def breekt_vorige_1h(bars, imp, cfg) -> bool:
    """Jouw regel: een impuls omhoog moet de HIGH van de vorige 1H-candle breken,
    een impuls omlaag de LOW. Kan de vorige 1H niet bepaald worden (geen epoch-tijd
    of te weinig historie), dan laten we hem door -- we blokkeren nooit op ontbrekende data."""
    if not cfg.get("eis_1h_break", True):
        return True
    ext = vorige_1h_extreme(bars, imp)
    if ext is None:
        return True
    hoog, laag = ext
    return imp.tot > hoog if imp.richting == "up" else imp.tot < laag


def _kleine_sweep(bars, j, richting, cfg) -> bool:
    """sweep_direct: de volgende candle gaat hooguit sweep_max_points door de high/low van j en sluit er weer onder/boven
    (een sweep, geen doorlopende impuls)."""
    if j + 1 >= len(bars):
        return False
    n = bars[j + 1]
    if richting == "up":
        door = (_h(n) - _h(bars[j])) / cfg["punt"]
        return 0 < door <= cfg["sweep_max_points"] and _c(n) < _h(bars[j])
    door = (_l(bars[j]) - _l(n)) / cfg["punt"]
    return 0 < door <= cfg["sweep_max_points"] and _c(n) > _l(bars[j])


def is_top(bars, j, richting) -> bool:
    """j is een top als de volgende (gesloten) candle niet verder komt."""
    if j + 1 >= len(bars):
        return False
    if richting == "up":
        return _h(bars[j + 1]) <= _h(bars[j])
    return _l(bars[j + 1]) >= _l(bars[j])


# ---------------------------------------------------------------- 2-6. levensloop

@dataclass
class Setup:
    sleutel: str
    impuls_richting: str      # "up" / "down"
    trade: str                # "short" / "long"
    impuls: dict
    top: float
    top_tijd: object
    eq: float
    status: str = "opgelet"   # opgelet -> rijp -> entry -> tp/sl/onbeslist ; of vervallen
    reden: str = ""
    pullback: Optional[float] = None
    sweep: Optional[float] = None
    sweep_tijd: object = None
    bos_tijd: object = None
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    risico_points: Optional[float] = None
    entry_tijd: object = None
    uitkomst_tijd: object = None
    events: List = field(default_factory=list)   # [(soort, tijd)]

    def naar_dict(self):
        return asdict(self)


def _event(s, soort, tijd):
    s.events.append((soort, tijd))


def volg_setup(bars, imp: Impuls, cfg, live=None) -> Setup:
    """Loopt de candles na de top af en bepaalt waar de setup nu staat.

    bars = GESLOTEN candles. live = de candle die nu nog loopt (of None); die
    telt alleen mee voor 'aanraken' (entry, SL, TP, de 50%), nooit voor een close.
    """
    up = imp.richting == "up"
    punt = cfg["punt"]
    j = imp.j
    s = Setup(
        sleutel=f"{imp.richting}-{_t(bars[imp.i])}-{_t(bars[j])}",
        impuls_richting=imp.richting, trade="short" if up else "long",
        impuls={k: (round(v, 3) if isinstance(v, float) else v) for k, v in asdict(imp).items()},
        top=imp.tot, top_tijd=_t(bars[j]), eq=round(imp.eq, 3),
    )
    s.impuls["van_tijd"] = _t(bars[imp.i])
    s.impuls["tot_tijd"] = _t(bars[j])
    _event(s, "opgelet", _t(bars[j + 1]))

    reeks = list(bars[j + 1:])
    live_idx = None
    if live is not None:
        reeks.append(live)
        live_idx = len(reeks) - 1

    voorbij = (lambda a, b: a > b) if up else (lambda a, b: a < b)       # verder dan de top
    terug = (lambda c, niveau: _l(c) <= niveau) if up else (lambda c, niveau: _h(c) >= niveau)
    uiterste = _h if up else _l
    tegen = _l if up else _h

    fase = "sweep"
    pullback = None
    sweep = None
    sweep_k = bos_k = None
    for k, c in enumerate(reeks):
        is_live = (k == live_idx)
        tijd = _t(c)
        n_na_top = k + 1           # candles sinds de top

        if fase in ("sweep", "bos", "entry"):
            # impuls weg: de 50% van de impuls geraakt vóór de entry
            if cfg.get("eis_50_impuls", True) and terug(c, s.eq):
                s.status, s.reden = "vervallen", "prijs raakte de 50% van de impuls vóór de entry: impuls weg"
                _event(s, "vervallen", tijd)
                return s

        if fase == "sweep":
            if is_live:
                break
            if voorbij(uiterste(c), s.top):
                if k == 0 and not cfg.get("sweep_direct", False):
                    # direct doorgelopen: geen mini-pullback, dan was dit niet de top
                    s.status, s.reden = "vervallen", "geen mini-pullback: de impuls liep gewoon door"
                    _event(s, "vervallen", tijd)
                    return s
                if pullback is None:                  # sweep_direct: de structuur is de topcandle zelf
                    pullback = tegen(bars[j])
                    s.pullback = pullback
                door = abs(uiterste(c) - s.top) / punt
                if door > cfg["sweep_max_points"]:
                    s.status, s.reden = "vervallen", f"{door:.0f} points door de top: geen sweep maar een nieuwe impuls"
                    _event(s, "vervallen", tijd)
                    return s
                sweep, sweep_k = uiterste(c), k
                s.sweep, s.sweep_tijd = sweep, tijd
                fase = "bos"
                # dezelfde candle kan meteen ook de BOS zijn (valt hieronder)
            else:
                pb = tegen(c)
                pullback = pb if pullback is None else (min(pullback, pb) if up else max(pullback, pb))
                s.pullback = pullback
                if n_na_top >= cfg["top_geldig_candles"]:
                    s.status, s.reden = "vervallen", f"geen sweep binnen {cfg['top_geldig_candles']} min na de top"
                    _event(s, "vervallen", tijd)
                    return s
                continue

        if fase == "bos":
            if is_live:
                break
            # het sweep-extreme kan nog verder lopen tot aan de BOS
            if voorbij(uiterste(c), sweep):
                sweep = uiterste(c)
                s.sweep = sweep
                door = abs(sweep - s.top) / punt
                if door > cfg["sweep_max_points"]:
                    s.status, s.reden = "vervallen", f"{door:.0f} points door de top: geen sweep maar een nieuwe impuls"
                    _event(s, "vervallen", tijd)
                    return s
            niveau = tegen(c) if cfg.get("bos_op_wick", False) else _c(c)          # wick (type 3 shift) of close
            gesloten_voorbij = (not cfg.get("eis_bos", True)) or ((niveau < pullback) if up else (niveau > pullback))
            if gesloten_voorbij:
                bos_k = k
                s.bos_tijd = tijd
                marge = cfg["sl_marge_points"] * punt
                pct = float(cfg.get("entry_pct", 0.5))
                s.entry = round(pullback + pct * (sweep - pullback), 2)
                s.sl = round(sweep + marge if up else sweep - marge, 2)
                risico = abs(s.sl - s.entry)
                s.tp = round(s.entry - cfg["rr"] * risico if up else s.entry + cfg["rr"] * risico, 2)
                s.risico_points = round(risico / punt, 1)
                s.status = "rijp"
                _event(s, "rijp", tijd)
                fase = "entry"
                continue
            if k - sweep_k >= cfg["bos_max_candles"]:
                s.status, s.reden = "vervallen", f"geen break of structure binnen {cfg['bos_max_candles']} min na de sweep"
                _event(s, "vervallen", tijd)
                return s
            continue

        if fase == "entry":
            geraakt = (_h(c) >= s.entry) if up else (_l(c) <= s.entry)
            tp_eerst = (_l(c) <= s.tp) if up else (_h(c) >= s.tp)
            if geraakt:
                s.status, s.entry_tijd = "entry", tijd
                _event(s, "entry", tijd)
                fase = "loopt"
                # zelfde candle: SL telt meteen, TP is niet te ordenen
                sl_hier = (_h(c) >= s.sl) if up else (_l(c) <= s.sl)
                if sl_hier:
                    s.status, s.uitkomst_tijd = "sl", tijd
                    _event(s, "sl", tijd)
                    return s
                if tp_eerst and not is_live:
                    s.status, s.uitkomst_tijd = "onbeslist", tijd
                    s.reden = "entry en TP in dezelfde minuut"
                    _event(s, "onbeslist", tijd)
                    return s
                continue
            if tp_eerst:
                s.status, s.reden = "vervallen", "TP-niveau al geraakt zonder pullback naar de entry"
                _event(s, "vervallen", tijd)
                return s
            if not is_live and k - bos_k >= cfg["entry_max_candles"]:
                s.status, s.reden = "vervallen", f"geen pullback naar de entry binnen {cfg['entry_max_candles']} min"
                _event(s, "vervallen", tijd)
                return s
            continue

        if fase == "loopt":
            sl_hier = (_h(c) >= s.sl) if up else (_l(c) <= s.sl)
            tp_hier = (_l(c) <= s.tp) if up else (_h(c) >= s.tp)
            if sl_hier and tp_hier:
                if is_live:
                    break
                s.status, s.uitkomst_tijd, s.reden = "onbeslist", tijd, "TP en SL in dezelfde minuut"
                _event(s, "onbeslist", tijd)
                return s
            if sl_hier:
                s.status, s.uitkomst_tijd = "sl", tijd
                _event(s, "sl", tijd)
                return s
            if tp_hier:
                s.status, s.uitkomst_tijd = "tp", tijd
                _event(s, "tp", tijd)
                return s
    return s


LEVEND = ("opgelet", "rijp", "entry")


def scan(bars, cfg=None, live=None, vanaf_index=0):
    """Alle setups in de candles, in volgorde van hun top.

    Zolang een setup in een richting nog leeft (wacht op sweep, BOS of entry),
    telt een nieuwe top in dezelfde richting niet als nieuwe setup -- anders
    krijg je voor één beweging drie meldingen.
    """
    cfg = {**STANDAARD, **(cfg or {})}
    uit = []
    bezet_tot = {"up": -1, "down": -1}     # index tot waar een setup nog 'leeft'
    start = max(cfg["atr_periode"] + cfg["impuls_min_candles"], vanaf_index)
    for j in range(start, len(bars) - 1):
        for richting in ("up", "down"):
            if j <= bezet_tot[richting]:
                continue
            if not is_top(bars, j, richting) and not (cfg.get("sweep_direct", False) and _kleine_sweep(bars, j, richting, cfg)):
                continue
            imp = impuls_naar(bars, j, richting, cfg)
            if imp is None:
                continue
            if not breekt_vorige_1h(bars, imp, cfg):
                continue                      # brak de vorige 1H high/low niet -> geen valide setup
            s = volg_setup(bars, imp, cfg, live=live)
            uit.append(s)
            # tot welke candle blokkeert deze setup nieuwe toppen?
            if s.status in LEVEND:
                bezet_tot[richting] = len(bars)
            else:
                laatste = s.events[-1][1]
                idx = next((k for k, c in enumerate(bars) if _t(c) == laatste), len(bars))
                # een doorgeschoten top mag meteen een nieuwe impuls starten
                bezet_tot[richting] = j if "nieuwe impuls" in s.reden or "liep gewoon door" in s.reden else idx
    return uit


def beste_kandidaat(bars, cfg=None):
    """Voor het log: de sterkste beweging aan het eind van de candles, ook als hij
    niet door de keuring komt -- zodat je ziet WAAROM er niets gebeurt.
    Loopt er nu een impuls die wél voldoet (nog zonder top), dan krijg je die."""
    cfg = {**STANDAARD, **(cfg or {})}
    if len(bars) < cfg["atr_periode"] + cfg["impuls_min_candles"] + 1:
        return None
    j = len(bars) - 1
    for richting in ("up", "down"):
        goed = impuls_naar(bars, j, richting, cfg)
        if goed is not None:
            return goed
    beste = None
    for richting in ("up", "down"):
        lo = max(cfg["atr_periode"] + 1, j - cfg["impuls_max_candles"] + 1)
        for jj in range(j, max(lo, j - 5) - 1, -1):
            for i in range(jj - cfg["impuls_min_candles"] + 1, lo - 1, -1):
                imp = meet_leg(bars, i, jj, richting, cfg)
                if imp is None:
                    continue
                if beste is None or imp.kracht > beste.kracht:
                    beste = imp
    return beste


def waarom_niet(imp: Impuls, cfg=None) -> str:
    cfg = {**STANDAARD, **(cfg or {})}
    r = []
    if imp.candles < cfg["impuls_min_candles"]:
        r.append(f"maar {imp.candles} candles")
    if imp.kracht < cfg["impuls_min_atr"]:
        r.append(f"te zwak ({imp.kracht:.1f}× ATR, min {cfg['impuls_min_atr']:g})".replace(".", ","))
    if imp.overlap > cfg["impuls_max_overlap"]:
        r.append(f"overlap {imp.overlap:.0%} (max {cfg['impuls_max_overlap']:.0%})")
    if imp.efficientie < cfg["impuls_min_efficientie"]:
        r.append(f"efficiëntie {imp.efficientie:.2f} (min {cfg['impuls_min_efficientie']:g})".replace(".", ","))
    return ", ".join(r) or "voldoet"
