# -*- coding: utf-8 -*-
"""
venster.py -- het handelsvenster als LIJST van blokken (1 okt 2026).

Bron van waarheid: journal_config.json > "venster": [["01:00","09:00"], ["10:00","15:00"]]
Alle tijden in Amsterdamse tijd, vast (ook in de winter; geen UTC-omrekening).
Ontbreekt de lijst, dan valt alles terug op venster_van / venster_tot (oude gedrag).
Het uur 09:00-10:00 valt bewust buiten het venster.

venster_van / venster_tot in de config zijn nu de OMHULLENDE (01:00 / 15:00), zodat
oude code die nog maar 1 blok kent niet breekt; code die dit bestand gebruikt kijkt
naar de echte blokken.
"""
import json
import os

_PAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal_config.json")
_cache = {"mtime": None, "root": {}}


def _minuten(hhmm):
    try:
        h, m = str(hhmm).strip().split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _root():
    try:
        mt = os.path.getmtime(_PAD)
        if mt != _cache["mtime"]:
            with open(_PAD, encoding="utf-8") as f:
                _cache["root"] = json.load(f)
            _cache["mtime"] = mt
    except (OSError, ValueError):
        pass
    return _cache["root"]


def blokken(cfg=None):
    """[(van_min, tot_min), ...] uit cfg["venster"] of de config, anders 1 blok uit van/tot."""
    cfg = cfg if cfg is not None else _root()
    lijst = cfg.get("venster")
    if isinstance(lijst, str):
        try:
            lijst = json.loads(lijst)
        except ValueError:
            lijst = None
    uit = []
    for b in (lijst or []):
        try:
            a, z = _minuten(b[0]), _minuten(b[1])
        except (TypeError, IndexError):
            continue
        if a is not None and z is not None:
            uit.append((a, z))
    if uit:
        return uit
    a, z = _minuten(cfg.get("venster_van", "10:00")), _minuten(cfg.get("venster_tot", "15:00"))
    return [(a, z)] if None not in (a, z) else []


def binnen(tijd, cfg=None):
    """True/False; None als er geen geldige tijd is (geen tijd = geen overtreding)."""
    t = tijd if isinstance(tijd, int) else _minuten(tijd)
    if t is None:
        return None
    return any(a <= t < z for a, z in blokken(cfg))


def sessie(tijd, cfg=None):
    """Korte naam voor de journal: 'Asia', '2e uur Londen' (10-15) of 'buiten venster'."""
    t = tijd if isinstance(tijd, int) else _minuten(tijd)
    if t is None or not binnen(t, cfg):
        return "buiten venster"
    return "Asia" if t < 9 * 60 else "2e uur Londen"


def tekst(cfg=None):
    return " en ".join("%02d:%02d–%02d:%02d" % (a // 60, a % 60, z // 60, z % 60) for a, z in blokken(cfg))
