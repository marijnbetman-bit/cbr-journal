"""
structuur_detector.py -- de CBR-setup zoals Marijn hem traded (plan v3, fase 1, 7 okt 2026).

Naast setup_detector.py (die blijft ongewijzigd: het journal en de Kampioen draaien erop). Pure functies, geen I/O;
tijden zijn Python-ints (epoch-seconden), net als in setup_detector.py.

Short na een expansie omhoog (long = gespiegeld):
  1 Sweep op candle t: high[t] > S = hoogste high van t-10..t-1, en high[t] - S <= sweep_max (40 points).
    Elke sweep is een eigen kandidaat; er is geen 'bezet'-slot (een eerdere kleine top blokkeert de echte niet).
  2 Expansie eindigt in t: het laagste begin i in t-90..t-4 waarbij binnen i..t geen terugval > 50% van de beweging tot
    dan (gemeten op candles NA een nieuwe high) en hooguit 15 candles onder de vorige high; grootte >= 4 x ATR(14).
  3 Structuur = laagste low tussen de geveegde high en de sweep. BOS (type 3) = eerste low eronder binnen 15 candles na
    het LAATSTE sweep-extreme (de sweep mag verlengen tot S + sweep_max). Variant: BOS op close (bos_op_close).
  4 BOS-been afmaken tot een candle geen nieuwe low maakt. Entry = midden van sweep-extreme en dat laagste punt.
  5 SL = sweep + sl_marge (1 point). TP: 1:1, 50% van de expansie, of de verste van die twee.
  6 De limietorder ligt er vanaf de candle NA het einde van het BOS-been (geen blik vooruit) en vervalt na 30 candles
    of als de TP eerst geraakt wordt.

    kandidaten(bars, cfg)  -> alle kandidaten (short en long) met kenmerken
    simuleer(bars, k, tp)  -> uitkomst van de limietorder (candles = bid; long koopt op ask, short sluit op ask)

bars = [(tijd, open, high, low, close[, spread]), ...] met tijd in epoch-seconden; spread in prijs (optioneel, standaard 0).
"""

import math
from datetime import datetime
from zoneinfo import ZoneInfo

AMS = ZoneInfo("Europe/Amsterdam")

STANDAARD = {
    "punt": 0.10,                  # 1 point = 0,10 in prijs (goud)
    "atr_periode": 14,
    "sweep_zoek": 10,              # de geveegde high: hoogste high van de 10 candles voor de sweep
    "sweep_max_points": 40,        # sweep hooguit 40 points voorbij die high (ook als hij verlengt)
    "expansie_max_candles": 90,
    "expansie_min_candles": 4,
    "expansie_min_atr": 4.0,
    "max_terugval": 0.5,           # binnen de expansie nooit meer dan 50% terug (pas getoetst vanaf 2 x ATR beweging)
    "max_onder_water": 15,         # hooguit 15 candles achter elkaar onder de vorige high
    "bos_max_candles": 15,         # na het laatste sweep-extreme
    "bos_op_close": False,         # False = type 3: een wick onder de structuur is genoeg
    "entry_max_candles": 30,       # zo lang ligt de limietorder er
    "sl_marge_points": 1,
}

TP_SLEUTELS = ("tp_11", "tp_50", "tp_max")


def _cfg(cfg):
    return {**STANDAARD, **(cfg or {})}


def _atr_reeks(H, L, C, n):
    """ATR[i] = gemiddelde true range over de n candles VOOR i (zoals setup_detector.atr)."""
    tr = [0.0] * len(H)
    for k in range(1, len(H)):
        tr[k] = max(H[k] - L[k], abs(H[k] - C[k - 1]), abs(L[k] - C[k - 1]))
    uit = [0.0] * len(H)
    s = 0.0
    for i in range(len(H)):
        if i - n >= 1:
            if i - n == 1:
                s = sum(tr[1:i])
            else:
                s += tr[i - 1] - tr[i - n - 1]
            uit[i] = s / n
    return uit


def _expansie(H, L, A, t, top, c):
    """Grootste geldige expansie die eindigt in t (high = top). Geeft (i, begin, tussenstukjes) of None."""
    beste = None
    lo_min = math.inf
    for i in range(t - c["expansie_min_candles"] + 1, max(c["atr_periode"] + 1, t - c["expansie_max_candles"]) - 1, -1):
        if L[i] >= lo_min:                       # i moet het laagste punt van i..t zijn
            continue
        lo_min = L[i]
        M, onder, ok, stukjes = -math.inf, 0, True, 0
        for k in range(i, t + 1):
            if H[k] > M:
                if onder:
                    stukjes += 1                 # een tussenstukje: even onder de high, dan verder omhoog
                M, onder = H[k], 0
                continue                         # terugval pas meten op candles NA een nieuwe high
            onder += 1
            if onder > c["max_onder_water"]:
                ok = False
                break
            beweging = M - lo_min
            if beweging > 0 and (M - L[k]) / beweging > c["max_terugval"] and beweging >= 2 * max(A[i], 1e-9):
                ok = False
                break
        if not ok:
            continue
        if A[i] <= 0 or (top - lo_min) / A[i] < c["expansie_min_atr"]:
            continue
        beste = (i, lo_min, stukjes)             # verder terug = groter; de laatste geldige wint
    return beste


def _scan_kant(T, O, H, L, C, c, vanaf):
    """Shorts op deze (eventueel gespiegelde) reeks. Prijzen in de reeks; omrekenen doet kandidaten()."""
    n, punt = len(H), c["punt"]
    smax = c["sweep_max_points"] * punt
    A = _atr_reeks(H, L, C, c["atr_periode"])
    uit, gezien = [], set()
    for t in range(max(c["atr_periode"] + c["expansie_min_candles"] + 2, vanaf, c["sweep_zoek"]), n - 2):
        lo = t - c["sweep_zoek"]
        s_idx = max(range(lo, t), key=lambda k: H[k])
        S = H[s_idx]
        if not (H[t] > S and H[t] - S <= smax):
            continue
        exp = _expansie(H, L, A, t, H[t], c)
        if exp is None:
            continue
        struct = min(L[k] for k in range(s_idx, t + 1))
        sweep, sweep_t, bos = H[t], t, None
        k = t + 1
        while k < n and k - sweep_t <= c["bos_max_candles"]:
            if H[k] > sweep:
                if H[k] - S > smax:
                    break                        # te ver door: geen sweep maar een nieuwe impuls
                sweep, sweep_t = H[k], k
            niveau = C[k] if c["bos_op_close"] else L[k]
            if niveau < struct:
                bos = k
                break
            k += 1
        if bos is None:
            continue
        leg, k = L[bos], bos + 1                 # BOS-been afmaken
        while k < n and L[k] < leg and H[k] <= sweep:
            leg, k = L[k], k + 1
        if k >= n - 1 or H[k] > sweep or (sweep_t, k) in gezien:
            continue                             # been nog niet af (live), de sweep liep door, of dezelfde order al gezien
        gezien.add((sweep_t, k))                 # zelfde sweep + zelfde einde van het been = dezelfde order
        entry = (sweep + leg) / 2
        sl = sweep + c["sl_marge_points"] * punt
        risico = sl - entry
        if risico <= 0:
            continue
        i, begin, stukjes = exp
        midden = (begin + sweep) / 2
        tp_11 = entry - risico
        tp_50 = midden if midden < entry else None
        uit.append({"i_begin": i, "i_geveegd": s_idx, "i_sweep": sweep_t, "i_bos": bos, "i_klaar": k, "i_order": k + 1,
                    "geveegd": S, "structuur": struct, "sweep": sweep, "bos_laag": leg, "entry": entry, "sl": sl,
                    "risico": risico, "begin": begin, "midden": midden, "tp_11": tp_11, "tp_50": tp_50,
                    "tp_max": tp_11 if tp_50 is None else min(tp_11, tp_50),
                    "_k": {"exp_atr": (sweep - begin) / A[i] if A[i] > 0 else None, "exp_candles": sweep_t - i,
                           "tussenstukjes": stukjes, "terug_bij_sweep": (S - struct) / (S - begin) if S > begin else None,
                           "sweep_points": (sweep - S) / punt,
                           "n_highs": sum(1 for q in range(lo, t) if H[q] >= S - 10 * punt),
                           "bos_close": C[bos] < struct, "bos_been_atr": (sweep - leg) / A[i] if A[i] > 0 else None,
                           "risico_points": risico / punt, "rr_50": (entry - midden) / risico if tp_50 is not None else None}})
    return uit


def _vorig_uur(T, H, idx, sweep):
    """Brak de sweep de high van het vorige volle uur (epoch-uren, zoals setup_detector.vorige_1h_extreme)?"""
    uur = (int(T[idx]) // 3600) * 3600
    hs = [H[q] for q in range(max(0, idx - 130), idx) if uur - 3600 <= int(T[q]) < uur]
    return None if not hs else sweep > max(hs)


def kandidaten(bars, cfg=None, vanaf_index=0):
    """Alle kandidaten (short en long) in volgorde van het orderindex, met kenmerken. Prijzen zijn echte prijzen."""
    c = _cfg(cfg)
    T = [int(b[0]) for b in bars]
    O = [b[1] for b in bars]
    H = [b[2] for b in bars]
    L = [b[3] for b in bars]
    C = [b[4] for b in bars]
    SP = [(b[5] or 0.0) if len(b) > 5 else 0.0 for b in bars]
    dag = [datetime.fromtimestamp(t, AMS).strftime("%Y-%m-%d") for t in T]
    uit = []
    for trade, reeks in (("short", (T, O, H, L, C)), ("long", (T, [-x for x in O], [-x for x in L], [-x for x in H], [-x for x in C]))):
        teken = 1 if trade == "short" else -1
        Hs = reeks[2]
        dagmax = [None] * len(T)                  # hoogste high van dezelfde (Amsterdamse) dag vóór deze candle
        m = None
        for q in range(len(T)):
            if q == 0 or dag[q] != dag[q - 1]:
                m = None
            dagmax[q] = m
            m = Hs[q] if m is None else max(m, Hs[q])
        for s in _scan_kant(*reeks, c, vanaf_index):
            k = s.pop("_k")
            for veld in ("geveegd", "structuur", "sweep", "bos_laag", "entry", "sl", "begin", "midden", "tp_11", "tp_50", "tp_max"):
                if s[veld] is not None:
                    s[veld] = round(teken * s[veld], 5)
            io = min(s["i_order"], len(T) - 1)
            ams = datetime.fromtimestamp(T[io], AMS)
            dag_extreem = dagmax[s["i_sweep"]]
            k.update({"brak_1h": _vorig_uur(T, Hs, s["i_sweep"], teken * s["sweep"]),
                      "minuut_ams": ams.hour * 60 + ams.minute, "weekdag": ams.weekday(), "spread": SP[io],
                      "afstand_dag_extreem_points": None if dag_extreem is None else (teken * s["sweep"] - dag_extreem) / c["punt"]})
            s.update({"trade": trade, "sleutel": "%s-%d-%d" % (trade, T[s["i_sweep"]], T[s["i_bos"]]),
                      "sweep_tijd": T[s["i_sweep"]], "bos_tijd": T[s["i_bos"]], "order_tijd": T[io],
                      "begin_tijd": T[s["i_begin"]], "datum": ams.strftime("%Y-%m-%d"), "kenmerken": k})
            uit.append(s)
    uit.sort(key=lambda s: (s["i_order"], s["trade"]))
    return uit


def _doorlopend(bars, kand, tp, c):
    """Zoals Marijn handmatig doet: vanaf de candle na de BOS ligt er steeds een limietorder op het midden van de sweep en
    het laagste punt TOT NU TOE (bijgewerkt na elke gesloten candle). Een vulling kan dus ook vóór het einde van het been
    vallen (op een minder goed midden). Geeft (fill_index, entry, tp-prijs) of (None, None, status)."""
    long_ = kand["trade"] == "long"
    t = -1 if long_ else 1                                   # rekenen alsof het een short is (long = gespiegeld)
    sweep, sl = t * kand["sweep"], t * kand["sl"]
    sp = lambda b: (b[5] or 0.0) if len(b) > 5 else 0.0
    hoog = lambda b: (-b[3] - sp(b)) if long_ else b[2]       # long koopt op ask
    laag = lambda b: -b[2] if long_ else b[3]
    leg = laag(bars[kand["i_bos"]])
    for k in range(kand["i_bos"] + 1, min(len(bars), kand["i_order"] + c["entry_max_candles"])):
        order = (sweep + leg) / 2
        risico = sl - order
        doel = order - risico if tp == "tp_11" else (t * kand["midden"] if tp == "tp_50" else min(order - risico, t * kand["midden"]))
        if doel >= order:
            return None, None, "ongeldig"
        if hoog(bars[k]) >= order:
            return k, t * order, t * doel                    # gevuld (ook als dit niet het laagste punt van het been was)
        if laag(bars[k]) < leg:
            leg = laag(bars[k])                              # been loopt door: order schuift mee omlaag
            continue
        if (laag(bars[k]) + (0 if long_ else sp(bars[k]))) <= doel:
            return None, None, "vervallen_tp"
    return None, None, "vervallen_tijd"


def simuleer(bars, kand, tp="tp_11", cfg=None, doorlopend=False):
    """Limietorder vanaf kand['i_order']; vervalt na entry_max_candles of als de TP eerst geraakt wordt.
    doorlopend=True: de meeschuivende order zoals Marijn hem handmatig legt (zie _doorlopend).
    Candles zijn bid: long koopt op ask (bid + spread) en sluit op bid; short verkoopt op bid en sluit op ask.
    Geeft {'status', 'r', 'fill_tijd', 'uit_tijd'}; status: tp, sl, onbeslist (SL en TP in één candle), vervallen_tp,
    vervallen_tijd, open (data op), ongeldig (geen TP aan de goede kant)."""
    c = _cfg(cfg)
    doel = kand.get(tp)
    long_ = kand["trade"] == "long"
    e, sl = kand["entry"], kand["sl"]
    sp = lambda b: (b[5] or 0.0) if len(b) > 5 else 0.0
    n, k0 = len(bars), kand["i_order"]
    fill = None
    if doorlopend:
        fill, e, doel = _doorlopend(bars, kand, tp, c)
        if fill is None:
            return {"status": doel, "r": None, "fill_tijd": None, "uit_tijd": None}
        k0 = fill
    if doel is None or (doel <= e if long_ else doel >= e):
        return {"status": "ongeldig", "r": None, "fill_tijd": None, "uit_tijd": None}
    r_tp = abs(doel - e) / abs(e - sl)
    for k in range(k0, n):
        b = bars[k]
        h, l = b[2], b[3]
        if fill is None:
            if k - k0 >= c["entry_max_candles"]:
                return {"status": "vervallen_tijd", "r": None, "fill_tijd": None, "uit_tijd": int(b[0])}
            geraakt = (l + sp(b) <= e) if long_ else (h >= e)
            tp_eerst = (h >= doel) if long_ else (l + sp(b) <= doel)
            if not geraakt:
                if tp_eerst:
                    return {"status": "vervallen_tp", "r": None, "fill_tijd": None, "uit_tijd": int(b[0])}
                continue
            fill = k
        sl_hier = (l <= sl) if long_ else (h + sp(b) >= sl)
        tp_hier = (h >= doel) if long_ else (l + sp(b) <= doel)
        if sl_hier and tp_hier:
            return {"status": "onbeslist", "r": None, "fill_tijd": int(bars[fill][0]), "uit_tijd": int(b[0])}
        if sl_hier:
            return {"status": "sl", "r": -1.0, "fill_tijd": int(bars[fill][0]), "uit_tijd": int(b[0])}
        if tp_hier and k > fill:
            return {"status": "tp", "r": round(r_tp, 4), "fill_tijd": int(bars[fill][0]), "uit_tijd": int(b[0])}
        if tp_hier:                              # TP in de fill-candle zelf: volgorde onbekend
            return {"status": "onbeslist", "r": None, "fill_tijd": int(bars[fill][0]), "uit_tijd": int(b[0])}
    return {"status": "open", "r": None, "fill_tijd": None if fill is None else int(bars[fill][0]), "uit_tijd": None}
