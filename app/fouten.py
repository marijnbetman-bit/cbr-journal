"""
Foutenanalyse (fase 4).

Detecteert patronen: herhaalt een foutcode zich 3x binnen 10 opeenvolgende
trades, dan is het geen incident maar een patroon. Koppelt er de corrigerende
regel aan en laat zien of je aan het verbeteren bent.
"""

from collections import defaultdict

from . import cbr

PATROON_DREMPEL = 3     # aantal keer...
PATROON_VENSTER = 10    # ...binnen dit aantal opeenvolgende trades


def _codes(trade):
    return [c.strip() for c in (trade.get("foutcodes") or "").split(",") if c.strip()]


def _groep_van(code):
    return code[0] if code else "?"


def analyse(trades):
    """trades: chronologisch gesorteerd (oudste eerst)."""
    trades = sorted(trades, key=lambda t: (t.get("datum") or "", t.get("id") or 0))
    n = len(trades)
    flat = cbr.all_foutcodes_flat()

    # ---- Frequentie, laatste voorkomen, posities ----
    posities = defaultdict(list)      # code -> [index in trades]
    for i, t in enumerate(trades):
        for c in _codes(t):
            posities[c].append(i)

    # ---- Patroon-detectie: 3x binnen een venster van 10 trades ----
    patronen = []
    for code, idxs in posities.items():
        beste = None
        for a in range(len(idxs)):
            # hoeveel voorkomens vallen binnen [idxs[a], idxs[a]+VENSTER)
            in_venster = [i for i in idxs[a:] if i < idxs[a] + PATROON_VENSTER]
            if len(in_venster) >= PATROON_DREMPEL:
                kandidaat = {
                    "aantal": len(in_venster),
                    "van_trade": in_venster[0] + 1,
                    "tot_trade": in_venster[-1] + 1,
                }
                if beste is None or kandidaat["aantal"] > beste["aantal"]:
                    beste = kandidaat
        if beste:
            patronen.append({
                "code": code,
                "groep": _groep_van(code),
                "omschrijving": flat.get(code, ""),
                "correctie": cbr.CORRECTIES.get(code, ""),
                "totaal": len(idxs),
                **beste,
            })
    patronen.sort(key=lambda p: (-p["aantal"], -p["totaal"]))

    # ---- Alle codes op een rij ----
    alle = []
    for code, idxs in posities.items():
        laatste_idx = idxs[-1]
        alle.append({
            "code": code,
            "groep": _groep_van(code),
            "omschrijving": flat.get(code, ""),
            "correctie": cbr.CORRECTIES.get(code, ""),
            "aantal": len(idxs),
            "laatste_datum": trades[laatste_idx].get("datum") or "",
            "trades_geleden": n - 1 - laatste_idx,
            "is_patroon": any(p["code"] == code for p in patronen),
        })
    alle.sort(key=lambda x: (-x["aantal"], x["code"]))

    # ---- Per groep (E/R/M/P/D) ----
    per_groep = []
    for g, data in cbr.FOUTCODES.items():
        totaal = sum(x["aantal"] for x in alle if x["groep"] == g)
        per_groep.append({"groep": g, "label": data["label"], "aantal": totaal})

    # ---- Verbeter je? Fouten per trade, laatste 10 vs. daarvoor ----
    def _fpt(subset):
        if not subset:
            return None
        return round(sum(len(_codes(t)) for t in subset) / len(subset), 2)

    recent = trades[-10:]
    eerder = trades[-20:-10]
    fpt_recent, fpt_eerder = _fpt(recent), _fpt(eerder)
    if fpt_recent is None or fpt_eerder is None:
        richting = "onbekend"
    elif fpt_recent < fpt_eerder:
        richting = "beter"
    elif fpt_recent > fpt_eerder:
        richting = "slechter"
    else:
        richting = "gelijk"

    # ---- Fouten per trade over tijd (voor de grafiek) ----
    reeks = []
    per_dag = defaultdict(lambda: {"fouten": 0, "trades": 0})
    for t in trades:
        d = t.get("datum") or ""
        per_dag[d]["fouten"] += len(_codes(t))
        per_dag[d]["trades"] += 1
    for d in sorted(per_dag):
        a = per_dag[d]
        reeks.append({"datum": d, "per_trade": round(a["fouten"] / a["trades"], 2),
                      "fouten": a["fouten"], "trades": a["trades"]})

    schoon = [t for t in trades if not _codes(t)]
    totaal_fouten = sum(len(_codes(t)) for t in trades)

    return {
        "n_trades": n,
        "totaal_fouten": totaal_fouten,
        "fouten_per_trade": round(totaal_fouten / n, 2) if n else 0,
        "n_schoon": len(schoon),
        "schoon_pct": round(100 * len(schoon) / n) if n else 0,
        "patronen": patronen,
        "alle": alle,
        "per_groep": per_groep,
        "trend": {
            "recent": fpt_recent, "eerder": fpt_eerder, "richting": richting,
        },
        "reeks": reeks,
        "drempel": PATROON_DREMPEL,
        "venster": PATROON_VENSTER,
    }


# =====================================================================
# Automatische foutenanalyse (23 sep 2026).
#
# De oude analyse hierboven leest handmatige foutcodes; die vul je niet meer
# in, dus die liep leeg. Deze versie leidt de fouten zelf af uit de feiten die
# MT5 al aanlevert: entrytijd, MFE/MAE, SL-afstand, exit-reden, resultaat in R,
# en of je je stop verschoof. Niets in te vullen.
# =====================================================================

def _minuten(hhmm):
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


AUTO_DEFS = {
    "te_vroeg_dicht": {
        "label": "Te vroeg gesloten",
        "uitleg": "Een winnaar die je met de hand sloot terwijl er duidelijk meer in de kaars zat.",
        "correctie": "Laat je target staan. Sluit pas handmatig als de structuur écht draait, niet bij de eerste winst.",
    },
    "sl_te_krap": {
        "label": "SL te krap — eerst je kant op, toen gepakt",
        "uitleg": "De trade liep eerst flink in je voordeel en werd daarna alsnog op je stop gepakt.",
        "correctie": "Zet je SL 5+ points voorbij de sweep, zodat een liquidity grab hem niet meepakt.",
    },
    "buiten_venster": {
        "label": "Buiten je venster",
        "uitleg": "Ingestapt buiten je afgesproken handelsvenster of op een niet-handelsdag.",
        "correctie": "Handel binnen je venster. Buiten het venster is de kans kleiner en de emotie groter.",
    },
    "boven_dagmax": {
        "label": "Boven je dagmaximum",
        "uitleg": "Meer trades op één dag dan je eigen maximum toestaat.",
        "correctie": "Stop na je dagmaximum. Doorgaan is bijna altijd revenge of verveling.",
    },
    "stop_verschoven": {
        "label": "Stop verschoven",
        "uitleg": "Je hebt tijdens de trade je stop verplaatst.",
        "correctie": "Laat je stop staan waar je hem zette. Verschuiven tegen je in verandert je risico ongemerkt.",
    },
}


def auto_analyse(trades, cfg=None, verschoven=None):
    """Leidt fouten automatisch af uit de trade-feiten. Geen handmatige codes."""
    cfg = cfg or {}
    verschoven = verschoven or {}
    import sys as _s, os as _o                       # blokken-venster (Asia + 10-15), 1 okt 2026
    _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
    import venster as _venster_blokken
    trades = sorted(trades, key=lambda t: (t.get("datum") or "", t.get("id") or 0))
    n = len(trades)

    van = _minuten(cfg.get("venster_van", "10:00"))
    tot = _minuten(cfg.get("venster_tot", "15:00"))
    dagen = cfg.get("handelsdagen")
    dagmax = int(cfg.get("max_trades_dag") or cfg.get("dagmaximum") or 0)

    getroffen = {code: [] for code in AUTO_DEFS}

    # dagmaximum: tel per dag
    per_dag_teller = {}

    from datetime import date as _date
    for t in trades:
        tid = t.get("id")
        datum = t.get("datum") or ""
        tijd = (t.get("tijd_entry") or "").strip()
        rr_r = t.get("resultaat_r")
        res = t.get("resultaat_eur") or 0
        mfe = t.get("mfe_points")
        sl_afst = t.get("sl_afstand_points")
        reden = (t.get("exit_reden") or "").lower()

        # 1) te vroeg gesloten
        if (res > 0 and "handmatig" in reden and mfe and sl_afst and sl_afst > 0
                and rr_r is not None):
            max_r = mfe / sl_afst
            liggen = round(max_r - rr_r, 2)
            if liggen >= 0.5:
                getroffen["te_vroeg_dicht"].append(
                    {"id": tid, "datum": datum, "tijd": tijd,
                     "detail": f"pakte {rr_r:+.2f}R van {max_r:.2f}R — liet {liggen:.2f}R liggen"})

        # 2) SL te krap: ging eerst je kant op, toen alsnog SL
        if reden.startswith("sl") and mfe and sl_afst and sl_afst > 0 and mfe >= 0.4 * sl_afst:
            getroffen["sl_te_krap"].append(
                {"id": tid, "datum": datum, "tijd": tijd,
                 "detail": f"liep eerst +{mfe:.0f}pt (SL-afstand {sl_afst:.0f}pt), daarna gestopt"})

        # 3) buiten venster / niet-handelsdag
        redenen = []
        if dagen and datum:
            try:
                if _date.fromisoformat(datum).weekday() not in dagen:
                    redenen.append("geen handelsdag")
            except ValueError:
                pass
        m = _minuten(tijd)
        if m is not None and _venster_blokken.binnen(m, cfg) is False:
            redenen.append(f"om {tijd}")
        if redenen:
            getroffen["buiten_venster"].append(
                {"id": tid, "datum": datum, "tijd": tijd, "detail": ", ".join(redenen)})

        # 4) boven dagmaximum
        per_dag_teller[datum] = per_dag_teller.get(datum, 0) + 1
        if dagmax and per_dag_teller[datum] > dagmax:
            getroffen["boven_dagmax"].append(
                {"id": tid, "datum": datum, "tijd": tijd,
                 "detail": f"trade {per_dag_teller[datum]} van de dag (max {dagmax})"})

        # 5) stop verschoven
        if verschoven.get(t.get("positie_id"), (0, 0))[0]:
            getroffen["stop_verschoven"].append(
                {"id": tid, "datum": datum, "tijd": tijd, "detail": "SL tijdens de trade verplaatst"})

    signalen = []
    for code, lijst in getroffen.items():
        if not lijst:
            continue
        d = AUTO_DEFS[code]
        signalen.append({
            "code": code, "label": d["label"], "uitleg": d["uitleg"],
            "correctie": d["correctie"], "aantal": len(lijst),
            "pct": round(100 * len(lijst) / n) if n else 0,
            "trades": lijst[-8:][::-1],
        })
    signalen.sort(key=lambda s: -s["aantal"])

    geraakt_ids = {r["id"] for lijst in getroffen.values() for r in lijst}
    schoon = [t for t in trades if t.get("id") not in geraakt_ids]

    return {
        "n_trades": n,
        "n_signalen": sum(s["aantal"] for s in signalen),
        "n_schoon": len(schoon),
        "schoon_pct": round(100 * len(schoon) / n) if n else 0,
        "signalen": signalen,
    }
