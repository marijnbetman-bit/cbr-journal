"""
Aggregatie voor het performance-dashboard.

Berekent uit de trades: spaarverloop (equity in EUR), equity in R,
kosten (charges) per trade en cumulatief, winrate totaal en per grade,
valide-setup % over tijd, foutcode-frequenties en criterium-kwaliteit.
"""

from collections import defaultdict, OrderedDict

from . import cbr, edge


def _r_multiple_trade(t):
    """R-uitkomst van een trade, netto na kosten. Zelfde bron als edge.py."""
    return edge.r_van_trade(t)[0]


def compute_stats(trades, n_no_trades, startkapitaal=0.0):
    trades = sorted(trades, key=lambda t: (t.get("datum") or "", t.get("id") or 0))

    n = len(trades)
    valide = [t for t in trades if t["grade"] in ("A", "B")]
    winners = [t for t in trades if (t.get("resultaat_eur") or 0) > 0]
    losers = [t for t in trades if (t.get("resultaat_eur") or 0) < 0]

    bruto = sum((t.get("resultaat_eur") or 0) for t in trades)
    kosten = sum((t.get("charges") or 0) for t in trades)   # negatief
    netto = bruto + kosten

    # ---- Spaarverloop (equity EUR) + equity R, per trade ----
    equity_labels, equity_eur, equity_r, kosten_cum, resultaat_per_trade = [], [], [], [], []
    history = []
    running_eur = float(startkapitaal)
    running_valide = float(startkapitaal)   # alleen A/B-setups: de discipline-lijn
    running_r = 0.0
    running_kosten = 0.0
    equity_valide = []
    per_day_index = defaultdict(int)
    for t in trades:
        d = t.get("datum") or ""
        per_day_index[d] += 1
        label = f"{d} #{per_day_index[d]}"
        res = t.get("resultaat_eur") or 0
        ch = t.get("charges") or 0
        rmult = _r_multiple_trade(t)
        running_eur += res + ch
        if t["grade"] in ("A", "B"):
            running_valide += res + ch      # C-trades tellen niet mee
        running_r += rmult
        running_kosten += ch
        equity_labels.append(label)
        equity_eur.append(round(running_eur, 2))
        equity_r.append(round(running_r, 2))
        kosten_cum.append(round(running_kosten, 2))
        equity_valide.append(round(running_valide, 2))
        resultaat_per_trade.append({
            "label": label, "grade": t["grade"],
            "netto": round(res + ch, 2), "resultaat": round(res, 2),
            "charges": round(ch, 2),
        })
        history.append({
            "id": t.get("id"), "datum": d, "tijd": t.get("tijd_entry") or "",
            "instrument": t.get("instrument") or "", "grade": t["grade"],
            "richting": t.get("richting") or "",
            "rr": t.get("rr"), "resultaat": round(res, 2), "netto": round(res + ch, 2),
            "r": round(rmult, 2), "foutcodes": t.get("foutcodes") or "",
        })

    # ---- Per grade ----
    per_grade = {}
    for g in ("A", "B", "C"):
        gts = [t for t in trades if t["grade"] == g]
        gw = [t for t in gts if (t.get("resultaat_eur") or 0) > 0]
        per_grade[g] = {
            "n": len(gts),
            "winrate": round(100 * len(gw) / len(gts)) if gts else 0,
            "netto": round(sum((t.get("resultaat_eur") or 0) + (t.get("charges") or 0) for t in gts), 2),
        }
    # valide (A+B) vs C
    valide_w = [t for t in valide if (t.get("resultaat_eur") or 0) > 0]
    c_trades = [t for t in trades if t["grade"] == "C"]
    c_w = [t for t in c_trades if (t.get("resultaat_eur") or 0) > 0]
    winrate_split = {
        "valide": round(100 * len(valide_w) / len(valide)) if valide else 0,
        "c": round(100 * len(c_w) / len(c_trades)) if c_trades else 0,
    }

    # ---- Per dag ----
    day_agg = OrderedDict()
    for t in trades:
        d = t.get("datum") or ""
        a = day_agg.setdefault(d, {"n": 0, "valide": 0, "netto": 0.0})
        a["n"] += 1
        if t["grade"] in ("A", "B"):
            a["valide"] += 1
        a["netto"] += (t.get("resultaat_eur") or 0) + (t.get("charges") or 0)
    per_dag = [
        {"datum": d, "n": a["n"],
         "valide_pct": round(100 * a["valide"] / a["n"]) if a["n"] else 0,
         "netto": round(a["netto"], 2)}
        for d, a in day_agg.items()
    ]

    # ---- Foutcodes geaggregeerd ----
    fout_count = defaultdict(int)
    for t in trades:
        for code in (t.get("foutcodes") or "").split(","):
            code = code.strip()
            if code:
                fout_count[code] += 1
    foutcodes = sorted(
        [{"code": c, "n": n_, "desc": cbr.all_foutcodes_flat().get(c, "")}
         for c, n_ in fout_count.items()],
        key=lambda x: -x["n"],
    )

    # ---- Criterium-kwaliteit (welk criterium krijgt chronisch ? of X) ----
    crit_quality = []
    for c in cbr.CRITERIA:
        counts = {"yes": 0, "maybe": 0, "no": 0}
        for t in trades:
            v = t.get(c["key"])
            if v in counts:
                counts[v] += 1
        crit_quality.append({
            "key": c["key"], "num": c["num"], "title": c["title"],
            "critical": c["critical"], **counts,
            "probleem": counts["maybe"] + counts["no"],
        })

    # ---- Grade-verdeling ----
    grade_dist = {g: sum(1 for t in trades if t["grade"] == g) for g in ("A", "B", "C")}

    # ---- Streaks (voor het beloningspaneel) ----
    def _streaks(seq):
        """(langste, huidige) reeks van True-waarden."""
        best_s = cur = 0
        for ok in seq:
            cur = cur + 1 if ok else 0
            best_s = max(best_s, cur)
        return best_s, cur

    win_seq = [(t.get("resultaat_eur") or 0) > 0 for t in trades]
    valide_seq = [t["grade"] in ("A", "B") for t in trades]
    win_langste, win_huidig = _streaks(win_seq)
    disc_langste, disc_huidig = _streaks(valide_seq)

    # ---- Mijlpalen op het portfolio ----
    MIJLPALEN = [75, 100, 150, 200, 250, 500, 1000]
    start_f = float(startkapitaal)
    volgende = next((m for m in MIJLPALEN if m > running_eur), None)
    vorige = max([m for m in MIJLPALEN if m <= running_eur] + [start_f])
    if volgende:
        spanne = volgende - vorige
        voortgang = round(100 * (running_eur - vorige) / spanne) if spanne > 0 else 0
    else:
        voortgang = 100
    mijlpaal = {
        "volgende": volgende,
        "vorige": round(vorige, 2),
        "voortgang_pct": max(0, min(100, voortgang)),
        "te_gaan": round(volgende - running_eur, 2) if volgende else 0,
        "behaald": [m for m in MIJLPALEN if m <= running_eur],
    }

    best = max(trades, key=lambda t: (t.get("resultaat_eur") or 0), default=None)
    worst = min(trades, key=lambda t: (t.get("resultaat_eur") or 0), default=None)

    return {
        "kpi": {
            "n_trades": n,
            "n_valide": len(valide),
            "valide_pct": round(100 * len(valide) / n) if n else 0,
            "n_no_trades": n_no_trades,
            "bruto_eur": round(bruto, 2),
            "kosten_eur": round(kosten, 2),
            "netto_eur": round(netto, 2),
            "winrate": round(100 * len(winners) / n) if n else 0,
            "n_winners": len(winners),
            "n_losers": len(losers),
            "avg_win": round(sum((t.get("resultaat_eur") or 0) for t in winners) / len(winners), 2) if winners else 0,
            "avg_loss": round(sum((t.get("resultaat_eur") or 0) for t in losers) / len(losers), 2) if losers else 0,
            "beste_eur": round((best.get("resultaat_eur") or 0), 2) if best else 0,
            "slechtste_eur": round((worst.get("resultaat_eur") or 0), 2) if worst else 0,
            "startkapitaal": round(float(startkapitaal), 2),
            "eindkapitaal": round(running_eur, 2),
            "eindkapitaal_valide": round(running_valide, 2),
            "discipline_edge": round(running_valide - running_eur, 2),
            "groei_pct": round(100 * (running_eur - float(startkapitaal)) / float(startkapitaal), 1) if float(startkapitaal) else 0,
            "totaal_r": round(running_r, 2),
            "win_streak_langste": win_langste,
            "win_streak_huidig": win_huidig,
            "discipline_streak_langste": disc_langste,
            "discipline_streak_huidig": disc_huidig,
        },
        "mijlpaal": mijlpaal,
        "equity": {
            "labels": equity_labels,
            "eur": equity_eur,
            "r": equity_r,
            "kosten_cum": kosten_cum,
            "valide": equity_valide,
        },
        "resultaat_per_trade": resultaat_per_trade,
        "history": history,
        "per_grade": per_grade,
        "winrate_split": winrate_split,
        "per_dag": per_dag,
        "foutcodes": foutcodes,
        "crit_quality": crit_quality,
        "grade_dist": grade_dist,
    }
