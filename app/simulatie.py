"""
Hoe zeker is zeker? (fase 11.3)

Twee dingen die een journal zelden doet en die je hier hard nodig hebt:

1. Een betrouwbaarheidsinterval op je winrate (Wilson). Bij vijf trades is dat
   interval belachelijk breed -- en dat is precies het punt.
2. Een Monte-Carlo: duizenden keren je eigen trades opnieuw trekken en kijken
   waar je dan uitkomt. Zo zie je hoeveel van je curve toeval kan zijn.

Alles gebeurt op R-uitkomsten uit edge.py, dus dezelfde bron als de rest.
"""

import math
import random

from . import edge

HERHALINGEN = 10000
VOORUIT = 20          # aantal trades voor de vooruitblik
SEED = 20260905       # vaste seed: dezelfde data geeft altijd hetzelfde antwoord


def wilson(successen, n, z=1.96):
    """
    Wilson score interval -- betrouwbaarder bij kleine steekproeven dan de
    gebruikelijke normale benadering, en het loopt nooit buiten 0-100%.
    """
    if not n:
        return {"laag": 0.0, "hoog": 100.0, "punt": 0.0, "breedte": 100.0}
    p = successen / n
    noemer = 1 + z * z / n
    midden = (p + z * z / (2 * n)) / noemer
    marge = (z / noemer) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    laag = max(0.0, midden - marge)
    hoog = min(1.0, midden + marge)
    return {
        "laag": round(100 * laag, 1),
        "hoog": round(100 * hoog, 1),
        "punt": round(100 * p, 1),
        "breedte": round(100 * (hoog - laag), 1),
    }


def _percentielen(waarden, punten=(5, 25, 50, 75, 95)):
    if not waarden:
        return {f"p{p}": 0.0 for p in punten}
    s = sorted(waarden)
    uit = {}
    for p in punten:
        i = (len(s) - 1) * p / 100
        laag, hoog = math.floor(i), math.ceil(i)
        val = s[laag] if laag == hoog else s[laag] + (s[hoog] - s[laag]) * (i - laag)
        uit[f"p{p}"] = round(val, 2)
    return uit


def _max_drawdown(reeks):
    top, dd = 0.0, 0.0
    stand = 0.0
    for r in reeks:
        stand += r
        top = max(top, stand)
        dd = max(dd, top - stand)
    return dd


def monte_carlo(rs, n_vooruit=VOORUIT, herhalingen=HERHALINGEN):
    """
    Trek met teruglegging uit je eigen R-uitkomsten. Twee vragen:
      - had dezelfde reeks er heel anders uit kunnen zien? (n = je huidige aantal)
      - waar sta je na nog eens 20 trades, als je edge blijft wat hij nu lijkt?
    """
    n = len(rs)
    if n < 2:
        return None

    rnd = random.Random(SEED)
    zelfde, vooruit, drawdowns = [], [], []
    for _ in range(herhalingen):
        reeks = [rnd.choice(rs) for _ in range(n)]
        zelfde.append(sum(reeks))
        drawdowns.append(_max_drawdown(reeks))
        vooruit.append(sum(rnd.choice(rs) for _ in range(n_vooruit)))

    negatief_zelfde = sum(1 for x in zelfde if x < 0)
    negatief_vooruit = sum(1 for x in vooruit if x < 0)

    return {
        "herhalingen": herhalingen,
        "n": n,
        "n_vooruit": n_vooruit,
        "werkelijk_r": round(sum(rs), 2),
        "zelfde": {**_percentielen(zelfde),
                   "kans_negatief": round(100 * negatief_zelfde / herhalingen, 1)},
        "vooruit": {**_percentielen(vooruit),
                    "kans_negatief": round(100 * negatief_vooruit / herhalingen, 1)},
        "drawdown": _percentielen(drawdowns, (50, 75, 95)),
    }


def analyse(trades):
    trades = [t for t in trades if (t.get("status") or "genomen") == "genomen"]
    n = len(trades)
    rs = [edge.r_van_trade(t)[0] for t in trades]
    winners = sum(1 for t in trades if (t.get("resultaat_eur") or 0) > 0)

    wr = wilson(winners, n)
    mc = monte_carlo(rs) if n >= 2 else None

    # Eén zin in gewone taal, want een percentiel zegt niemand iets.
    if n < 5:
        oordeel = ("Te weinig trades om ook maar iets te zeggen. Onder de twintig is "
                   "elk cijfer hier ruis.")
    elif wr["breedte"] > 40:
        oordeel = (f"Je winrate ligt ergens tussen {wr['laag']:.0f}% en {wr['hoog']:.0f}%. "
                   "Dat is geen meting, dat is een gok met foutmarge — je hebt simpelweg "
                   "meer trades nodig.")
    else:
        oordeel = (f"Je winrate ligt met 95% zekerheid tussen {wr['laag']:.0f}% en "
                   f"{wr['hoog']:.0f}%. Dat begint ergens op te lijken.")

    return {
        "n": n,
        "winrate": wr,
        "monte_carlo": mc,
        "oordeel": oordeel,
        "genoeg": n >= 20,
    }
