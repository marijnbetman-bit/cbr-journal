"""
Rapportkaart per maand en per jaar (fase 12.2) en tag-statistiek (fase 12.4).

De rapportkaart is bedoeld om aan het eind van de maand in twee minuten door te
lezen en daarna weg te leggen: wat deed je, wat ging goed, waar zat je grootste
lek, en wat schreef je zelf op.
"""

from datetime import date

from . import adherentie, cbr, edge, fouten, inzicht

MAANDNAMEN = ["januari", "februari", "maart", "april", "mei", "juni",
              "juli", "augustus", "september", "oktober", "november", "december"]


def periode_grenzen(soort, sleutel):
    """soort 'maand' met sleutel '2026-09', of 'jaar' met sleutel '2026'."""
    if soort == "jaar":
        jaar = int(sleutel)
        return f"{jaar}-01-01", f"{jaar}-12-31", str(jaar)
    jaar, mnd = (int(x) for x in sleutel.split("-")[:2])
    laatste = 31
    for d in (31, 30, 29, 28):
        try:
            date(jaar, mnd, d)
            laatste = d
            break
        except ValueError:
            continue
    return (f"{jaar}-{mnd:02d}-01", f"{jaar}-{mnd:02d}-{laatste:02d}",
            f"{MAANDNAMEN[mnd - 1]} {jaar}")


def _beste_en_slechtste(trades):
    if not trades:
        return None, None
    op_netto = sorted(trades, key=lambda t: edge._netto(t))
    return op_netto[-1], op_netto[0]


def bouw(soort, sleutel, trades, overgeslagen, no_trades, reviews, startkapitaal=0.0):
    van, tot, titel = periode_grenzen(soort, sleutel)

    n = len(trades)
    rs = [edge.r_van_trade(t)[0] for t in trades]
    winners = [t for t in trades if (t.get("resultaat_eur") or 0) > 0]
    valide = [t for t in trades if t.get("grade") in ("A", "B")]
    perfect = [t for t in trades if t.get("grade") == "A"]

    e = edge.analyse(trades, startkapitaal) if trades else None
    adh = adherentie.analyse(trades)
    ft = fouten.analyse(trades)
    disc = inzicht.discipline(trades, overgeslagen)

    beste, slechtste = _beste_en_slechtste(trades)

    # De vaakste fout mét de corrigerende regel -- dat is het enige actiepunt dat telt.
    top_fout = None
    alle_fouten = sorted(ft.get("alle", []), key=lambda c: -c.get("aantal", 0))
    if alle_fouten:
        eerste = alle_fouten[0]
        top_fout = {
            "code": eerste.get("code"),
            "aantal": eerste.get("aantal"),
            "omschrijving": eerste.get("omschrijving") or cbr.all_foutcodes_flat().get(eerste.get("code"), ""),
            "correctie": eerste.get("correctie") or cbr.CORRECTIES.get(eerste.get("code"), ""),
        }

    dagen = sorted({t.get("datum") for t in trades})
    netto = round(sum(edge._netto(t) for t in trades), 2)

    lessen = [t.get("les") for t in trades if (t.get("les") or "").strip()]

    return {
        "soort": soort,
        "sleutel": sleutel,
        "titel": titel,
        "van": van,
        "tot": tot,
        "kop": {
            "n_trades": n,
            "handelsdagen": len(dagen),
            "netto_eur": netto,
            "netto_r": round(sum(rs), 2),
            "winrate": round(100 * len(winners) / n) if n else 0,
            "valide_pct": round(100 * len(valide) / n) if n else 0,
            "n_perfect": len(perfect),
            "n_no_trades": len(no_trades),
            "n_overgeslagen": len(overgeslagen),
            "expectancy_r": e["expectancy_r"] if e else 0.0,
            "profit_factor": e["profit_factor"] if e else None,
            "adherentie": adh["pct"],
            "adherentie_band": adh["band"]["label"],
            "discipline": disc["gemiddeld"],
        },
        "beste": _kort(beste),
        "slechtste": _kort(slechtste),
        "top_fout": top_fout,
        "patronen": ft.get("patronen", []),
        "lessen": lessen[-8:],
        "reviews": reviews,
        "genoeg": n >= 20,
    }


def _kort(t):
    if not t:
        return None
    return {
        "id": t.get("id"), "datum": t.get("datum"), "grade": t.get("grade"),
        "richting": t.get("richting"), "rr": t.get("rr"),
        "netto_eur": round(edge._netto(t), 2), "les": t.get("les") or "",
    }


# ---------- 12.4 tag-statistiek ----------

def tag_stats(trades, min_n=3):
    per_tag = {}
    for t in trades:
        for tag in (t.get("tags") or "").split(","):
            tag = tag.strip()
            if tag:
                per_tag.setdefault(tag, []).append(t)

    uit = []
    for tag, rij in per_tag.items():
        cel = inzicht._cel(tag, rij)
        cel["tag"] = tag
        cel["betrouwbaar"] = len(rij) >= min_n
        uit.append(cel)
    uit.sort(key=lambda c: (-c["n"], c["tag"]))
    return {"tags": uit, "min_n": min_n, "n_getagd":
            sum(1 for t in trades if (t.get("tags") or "").strip())}


# =====================================================================
# Terugkerende-patroondetector (ronde 3, punt 6).
#
# De foutcode-detector in fouten.py kijkt naar vaste codes. Deze kijkt naar
# je eigen woorden: de tags die je zelf aan trades hangt ("soft break",
# "SL binnen sweep", "geen sweep"). Jij zag zelf dat trade 1 en trade 8 op
# elkaar leken -- de journal hoort dat vóór jou te zien.
# =====================================================================

DREMPEL = 3          # vanaf drie keer noemen we het een patroon


def terugkerend(trades, drempel=DREMPEL):
    """Tags die vaak terugkomen, met wat ze je opleveren of kosten."""
    st = tag_stats(trades, min_n=drempel)
    patronen = []
    for cel in st["tags"]:
        if cel["n"] < drempel:
            continue
        kostend = cel["netto_eur"] < 0 or cel["expectancy_r"] < 0
        patronen.append({
            **cel,
            "kostend": kostend,
            "oordeel": (
                f"\u201c{cel['tag']}\u201d kwam {cel['n']}\u00d7 terug en staat op "
                f"{cel['netto_eur']:+.2f} euro ({cel['expectancy_r']:+.2f}R per trade). "
                + ("Dit is geen incident meer, dit is een patroon."
                   if kostend else
                   "Dit werkt voor je \u2014 zoek er meer van.")
            ),
        })
    # eerst wat je geld kost, en daarbinnen wat het vaakst voorkomt
    patronen.sort(key=lambda p: (not p["kostend"], -p["n"]))

    kostend = [p for p in patronen if p["kostend"]]
    return {
        "patronen": patronen,
        "kostend": kostend,
        "drempel": drempel,
        "n_getagd": st["n_getagd"],
        "samenvatting": (
            f"{len(kostend)} terugkerend patroon kost je geld."
            if len(kostend) == 1 else
            f"{len(kostend)} terugkerende patronen kosten je geld."
            if kostend else
            ("Nog geen tag die {0}\u00d7 of vaker terugkomt. Tag je trades kort "
             "(\u201csoft break\u201d, \u201cgeen sweep\u201d), dan ziet de journal "
             "herhaling eerder dan jij.").format(drempel)
        ),
    }
