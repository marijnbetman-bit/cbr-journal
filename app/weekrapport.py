# -*- coding: utf-8 -*-
"""
weekrapport.py -- je progressie per week (v2.1, 29 sep 2026).

Per ISO-week dezelfde meetlat, zodat je ziet of je BETER wordt -- niet alleen
of je geld verdiende:
  resultaat   netto, R, winrate, expectancy, profit factor
  proces      proces-score, % regels gevolgd, % grade A, uitvoering (1-5)
  mens        % trades met een goede staat (rustig/gefocust), emoties
  discipline  % binnen venster, dagen boven je dagmaximum, R laten liggen
Plus per week: deltas t.o.v. de vorige week, lessen, de auto-fouten en een
automatische focus voor de week erna.
"""

from collections import Counter
from datetime import date, timedelta

from . import prestaties, fouten

GOED = ("rustig", "gefocust")


def maandag_van(d):
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return d - timedelta(days=d.weekday())


def week_label(ma):
    j, w, _ = ma.isocalendar()
    zo = ma + timedelta(days=6)
    M = prestaties.MAANDEN
    if ma.month == zo.month:
        bereik = f"{ma.day}–{zo.day} {M[zo.month - 1][:3]}"
    else:
        bereik = f"{ma.day} {M[ma.month - 1][:3]} – {zo.day} {M[zo.month - 1][:3]}"
    return {"week": w, "jaar": j, "kort": f"wk {w}", "bereik": bereik}


def _pct(teller, noemer):
    return round(100 * teller / noemer) if noemer else None


def meet(trades, cfg=None):
    """Alle weekcijfers voor een lijst trades."""
    n = len(trades)
    cel = prestaties._cel("", trades)
    netto = [prestaties._netto(t) for t in trades]
    winst = sum(x for x in netto if x > 0)
    verlies = abs(sum(x for x in netto if x < 0))
    beoordeeld = [t for t in trades if t.get("beoordeeld") == 1]
    scores = [t["proces_score"] for t in trades if t.get("proces_score") is not None]
    uitv = [t["uitvoering"] for t in trades if t.get("uitvoering")]
    emo = [t["emotie_voor"] for t in trades if t.get("emotie_voor")]
    venster = [t for t in trades if t.get("check_venster") is not None]
    per_dag = Counter(t.get("datum") for t in trades)
    dagmax = int((cfg or {}).get("max_trades_dag") or 2)
    rl = prestaties.r_laten_liggen(trades)
    return {
        "n": n,
        "handelsdagen": len(per_dag),
        "netto_eur": cel["netto_eur"],
        "netto_r": cel["netto_r"],
        "winrate": cel["winrate"] if n else None,
        "expectancy_r": cel["expectancy_r"] if n else None,
        "profit_factor": round(winst / verlies, 2) if verlies else (None if not winst else 99.0),
        "proces_score": round(sum(scores) / len(scores)) if scores else None,
        "schoon_pct": _pct(sum(1 for t in beoordeeld if t.get("schoon") == 1), len(beoordeeld)),
        "a_pct": _pct(sum(1 for t in trades if t.get("grade") == "A"), n),
        "uitvoering": round(sum(uitv) / len(uitv), 1) if uitv else None,
        "goede_staat_pct": _pct(sum(1 for e in emo if e in GOED), len(emo)),
        "emoties": dict(Counter(emo)),
        "venster_pct": _pct(sum(1 for t in venster if t["check_venster"] == 1), len(venster)),
        "dagen_boven_max": sum(1 for v in per_dag.values() if v > dagmax),
        "r_liggen": rl["gem_winnaars_r"] if rl["n_winnaars"] else None,
        "gelogd_pct": _pct(len(beoordeeld), n),
    }


# richting per metriek: +1 = hoger is beter, -1 = lager is beter
RICHTING = {
    "netto_eur": 1, "netto_r": 1, "winrate": 1, "expectancy_r": 1, "profit_factor": 1,
    "proces_score": 1, "schoon_pct": 1, "a_pct": 1, "uitvoering": 1, "goede_staat_pct": 1,
    "venster_pct": 1, "dagen_boven_max": -1, "r_liggen": -1, "gelogd_pct": 1, "n": 0,
}
NAMEN = {
    "proces_score": "proces-score", "schoon_pct": "regels gevolgd", "a_pct": "A-setups",
    "uitvoering": "uitvoering", "goede_staat_pct": "goede staat vooraf",
    "venster_pct": "binnen venster", "expectancy_r": "expectancy", "winrate": "winrate",
    "r_liggen": "R laten liggen", "dagen_boven_max": "dagen boven dagmax",
}


def deltas(nu, vorig):
    uit = {}
    for k, richting in RICHTING.items():
        a, b = nu.get(k), (vorig or {}).get(k)
        if a is None or b is None:
            uit[k] = None
            continue
        d = round(a - b, 2)
        uit[k] = {"delta": d, "beter": (d * richting > 0) if richting and d else None}
    return uit


def weken(trades, cfg=None, aantal=None):
    """Alle weken met trades (oud -> nieuw), plus lege weken ertussen."""
    if not trades:
        return []
    per = {}
    for t in trades:
        if t.get("datum"):
            per.setdefault(maandag_van(t["datum"]), []).append(t)
    eerste, laatste = min(per), max(max(per), maandag_van(date.today()))
    rijen, ma = [], eerste
    while ma <= laatste:
        ts = per.get(ma, [])
        rijen.append({"maandag": ma.isoformat(), **week_label(ma), **meet(ts, cfg)})
        ma += timedelta(days=7)
    return rijen[-aantal:] if aantal else rijen


def focus(m, auto_fouten, trades):
    """Eén concreet ding voor volgende week -- het zwaarste lek eerst."""
    sig = [s for s in (auto_fouten or {}).get("signalen", []) if s.get("aantal")]
    if sig:
        s = sig[0]
        return {"titel": s["label"], "tekst": s.get("correctie") or s.get("uitleg") or "",
                "bron": f"{s['aantal']}× deze week"}
    tags = Counter(x.strip() for t in trades for x in (t.get("foutcodes") or "").split(",") if x.strip())
    if tags:
        tag, n = tags.most_common(1)[0]
        return {"titel": tag, "tekst": "Je tagde dit zelf het vaakst. Maak er één regel van en check hem vóór elke entry.",
                "bron": f"{n}× getagd"}
    if m.get("goede_staat_pct") is not None and m["goede_staat_pct"] < 60:
        return {"titel": "Je staat vooraf", "tekst": "Minder dan 60% van je trades nam je rustig of gefocust. Geen trade als je twijfelt, haast hebt of iets wilt terugwinnen.",
                "bron": f"{m['goede_staat_pct']}% goede staat"}
    if m.get("r_liggen") and m["r_liggen"] > 0.3:
        return {"titel": "Laat je winnaars lopen", "tekst": "Je sloot winnaars gemiddeld ruim voor je TP. Zet je TP op 1:1 en blijf eraf.",
                "bron": f"{m['r_liggen']:.2f}R laten liggen".replace(".", ",")}
    return {"titel": "Zo doorgaan", "tekst": "Geen duidelijke lekken deze week. Blijf elke trade loggen — consistentie is de edge.",
            "bron": ""}


def sterke_punten(m, d):
    uit = []
    for k, naam in NAMEN.items():
        x = (d or {}).get(k)
        if x and x.get("beter"):
            eenheid = "%" if k.endswith("pct") else ("R" if k.endswith("_r") else "")
            uit.append(f"{naam} {'+' if x['delta'] > 0 else ''}{x['delta']:g}{eenheid} t.o.v. vorige week".replace(".", ","))
    if m.get("a_pct") and m["a_pct"] >= 50:
        uit.append(f"{m['a_pct']}% van je trades was een A-setup")
    if m.get("schoon_pct") == 100 and m.get("n"):
        uit.append("alle regels gevolgd")
    return uit[:4]


def rapport(trades_week, trades_vorig, trades_alles, cfg=None, verschoven=None, per_dag_alles=None):
    m = meet(trades_week, cfg)
    v = meet(trades_vorig, cfg) if trades_vorig else None
    d = deltas(m, v)
    auto = fouten.auto_analyse(trades_week, cfg, verschoven) if trades_week else {"signalen": []}
    ts = []
    for t in sorted(trades_week, key=lambda x: (x.get("datum") or "", x.get("tijd_entry") or "")):
        ts.append({
            "id": t["id"], "datum": t["datum"], "tijd": t.get("tijd_entry"), "tijd_exit": t.get("tijd_exit"),
            "richting": t.get("richting"), "grade": t.get("grade"), "beoordeeld": t.get("beoordeeld"),
            "r": round(prestaties._r(t), 2), "netto": round(prestaties._netto(t), 2),
            "emotie": t.get("emotie_voor"), "uitvoering": t.get("uitvoering"),
            "proces_score": t.get("proces_score"), "schoon": t.get("schoon"),
            "les": (t.get("les") or "").strip(), "fouten": [x for x in (t.get("foutcodes") or "").split(",") if x.strip()],
            "exit_reden": t.get("exit_reden"), "sessie": prestaties.sessie_van(t.get("tijd_entry")),
            "sl_bekend": t.get("sl_prijs") is not None or t.get("sl") is not None,
        })
    dagen = prestaties.per_dag(trades_week)
    beste = max((x for x in ts if x["netto"] > 0), key=lambda x: ((x["proces_score"] or 0), x["netto"]), default=None)
    leerzaam = min((x for x in ts if x["proces_score"] is not None), key=lambda x: x["proces_score"], default=None)
    if leerzaam and beste and leerzaam["id"] == beste["id"]:
        leerzaam = None
    return {
        "meting": m, "vorige": v, "deltas": d,
        "dagen": [{"datum": x["datum"], "weekdag": x["weekdag"], "n": x["n"], "netto_eur": x["netto_eur"],
                   "netto_r": x["netto_r"], "winrate": x["winrate"]} for x in dagen],
        "trades": ts,
        "lessen": [{"id": x["id"], "datum": x["datum"], "tijd": x["tijd"], "les": x["les"]} for x in ts if x["les"]],
        "auto_fouten": [s for s in auto.get("signalen", []) if s.get("aantal")][:5],
        "focus": focus(m, auto, trades_week),
        "sterk": sterke_punten(m, d),
        "beste": beste, "leerzaam": leerzaam,
        "progressie": weken(trades_alles, cfg, aantal=12),
    }
