"""
Proces boven uitkomst (ronde 3, punt 1).

Het probleem dat dit oplost: een winst die je zelf niet aan je edge toeschrijft
telt in een gewone winrate precies even zwaar als een perfecte uitvoering. Zo
glipt geluk je cijfers in als vaardigheid, en beloon je jezelf voor gedrag dat
je juist niet wilt aanleren.

Daarom twee scoreborden naast elkaar:
  - het UITKOMST-bord: winrate en netto, zoals altijd;
  - het PROCES-bord: valide-setup-ratio, en dezelfde cijfers nog eens met de
    trades die jij zelf als geluk markeerde eruit gehaald.

Wijkt het proces-bord sterk af van het uitkomst-bord, dan draait je resultaat
op iets anders dan je model. Dat is precies wat je wilt weten voordat je je
inzet verhoogt.
"""

from . import cbr, edge

MIN_N = 5
VALIDE_GRADES = ("A", "B")


def _netto(t):
    return edge._netto(t)


def _is_luck(t):
    return (t.get("luck_flag") or "").strip() == "ja"


def _valide(t):
    return (t.get("grade") or "") in VALIDE_GRADES


def _winrate(rij):
    if not rij:
        return 0
    return round(100 * len([t for t in rij if _netto(t) > 0]) / len(rij))


def scorebord(trades):
    """Uitkomst tegenover proces, in één blok."""
    n = len(trades)
    if not n:
        return {"n": 0, "genoeg": False, "min_n": MIN_N}

    winnaars = [t for t in trades if _netto(t) > 0]
    valide = [t for t in trades if _valide(t)]
    luck = [t for t in trades if _is_luck(t)]
    luck_winsten = [t for t in luck if _netto(t) > 0]

    # Zonder de trades die jij zelf als geluk markeerde. Niet weggegooid --
    # apart gezet, zodat je ziet wat er van je cijfers overblijft.
    zuiver = [t for t in trades if not _is_luck(t)]

    netto_totaal = round(sum(_netto(t) for t in trades), 2)
    netto_luck = round(sum(_netto(t) for t in luck), 2)
    netto_zuiver = round(netto_totaal - netto_luck, 2)

    per_grade = {}
    for t in trades:
        per_grade.setdefault(t.get("grade") or "?", []).append(t)

    # Hoeveel van je winst komt uit setups die je eigen checklist goedkeurde?
    netto_valide = round(sum(_netto(t) for t in valide), 2)
    aandeel_valide = (round(100 * netto_valide / netto_totaal)
                      if netto_totaal > 0 else None)

    oordeel = ""
    if luck_winsten:
        oordeel = (f"{len(luck_winsten)} van je {len(winnaars)} winsten heb je zelf als geluk "
                   f"gemarkeerd, samen {netto_luck:+.2f} euro. Zonder die trades is je winrate "
                   f"{_winrate(zuiver)}% in plaats van {_winrate(trades)}%.")
    elif n >= MIN_N:
        oordeel = ("Je hebt nog geen enkele winst als geluk gemarkeerd. Dat kan kloppen — "
                   "maar het vinkje is er juist voor de trades waar je achteraf een ongemakkelijk "
                   "gevoel bij hebt.")

    return {
        "n": n,
        "genoeg": n >= MIN_N,
        "min_n": MIN_N,

        # uitkomst
        "winrate": _winrate(trades),
        "netto_eur": netto_totaal,

        # proces
        "valide": len(valide),
        "valide_ratio": round(100 * len(valide) / n),
        "netto_valide_eur": netto_valide,
        "aandeel_valide_pct": aandeel_valide,

        # geluk apart gezet
        "luck": len(luck),
        "luck_winsten": len(luck_winsten),
        "netto_luck_eur": netto_luck,
        "winrate_zonder_luck": _winrate(zuiver),
        "netto_zonder_luck_eur": netto_zuiver,

        "per_grade": {g: {"n": len(r), "netto_eur": round(sum(_netto(t) for t in r), 2),
                          "winrate": _winrate(r)}
                      for g, r in sorted(per_grade.items())},
        "oordeel": oordeel,
    }


def valide_streak(trades):
    """
    Hoeveel valide setups op een rij? Dit is de reeks die je wilt zien groeien --
    niet je winstreeks, want die kun je niet sturen.
    """
    op_volgorde = sorted(trades, key=lambda t: (t.get("datum") or "",
                                                t.get("tijd_entry") or "", t.get("id") or 0))
    nu = langste = 0
    for t in op_volgorde:
        if _valide(t):
            nu += 1
            langste = max(langste, nu)
        else:
            nu = 0
    return {"huidig": nu, "langste": langste}


# ---------- venster-bewaking ----------

def venster(trades, van="10:00", tot="11:00"):
    """
    Hoeveel trades vielen buiten je eigen uur, en wat leverden ze op?
    Zonder entrytijd doen we geen uitspraak -- dat is ontbrekende data,
    geen overtreding.
    """
    binnen, buiten, onbekend = [], [], []
    for t in trades:
        oordeel = cbr.binnen_venster(t.get("tijd_entry"), van, tot)
        (onbekend if oordeel is None else (binnen if oordeel else buiten)).append(t)

    def blok(naam, rij):
        return {
            "naam": naam, "n": len(rij),
            "winrate": _winrate(rij),
            "netto_eur": round(sum(_netto(t) for t in rij), 2),
            "valide_ratio": round(100 * len([t for t in rij if _valide(t)]) / len(rij)) if rij else 0,
        }

    b_in, b_uit = blok("binnen je venster", binnen), blok("buiten je venster", buiten)
    oordeel = ""
    if binnen and buiten:
        verschil = round(b_in["netto_eur"] - b_uit["netto_eur"], 2)
        if b_uit["netto_eur"] < 0:
            oordeel = (f"Buiten je venster sta je op {b_uit['netto_eur']:+.2f} euro over "
                       f"{b_uit['n']} trades. Dat is geen edge, dat is een lek.")
        elif b_in["valide_ratio"] > b_uit["valide_ratio"]:
            oordeel = (f"Binnen je venster is {b_in['valide_ratio']}% van je setups valide, "
                       f"daarbuiten {b_uit['valide_ratio']}%. Je uur houdt je scherp.")
        else:
            oordeel = (f"Buiten je venster loopt het tot nu toe niet slechter "
                       f"({verschil:+.2f} euro verschil). Te weinig data om je regel te wijzigen.")

    return {
        "binnen": b_in, "buiten": b_uit,
        "zonder_tijd": len(onbekend),
        "van": van, "tot": tot,
        "van_londen": cbr.londense_tijd(van), "tot_londen": cbr.londense_tijd(tot),
        "oordeel": oordeel, "min_n": MIN_N,
    }


# ---------- de mens-laag ----------

def sessies(rijen, trades):
    """
    Wat je zelf per dag hebt aangevinkt, naast wat die dag opleverde.
    De vraag die dit beantwoordt: kost gehaast of moe zijn je daadwerkelijk geld?
    """
    per_dag = {}
    for t in trades:
        per_dag.setdefault(t.get("datum"), []).append(t)

    verrijkt = []
    for s in rijen:
        dag = per_dag.get(s["datum"], [])
        verrijkt.append({
            **s,
            "n": len(dag),
            "netto_eur": round(sum(_netto(t) for t in dag), 2),
            "valide": len([t for t in dag if _valide(t)]),
        })

    def per_staat(key):
        dagen = [v for v in verrijkt if v.get("staat") == key]
        return {
            "key": key, "dagen": len(dagen),
            "netto_eur": round(sum(d["netto_eur"] for d in dagen), 2),
            "trades": sum(d["n"] for d in dagen),
        }

    staten = [per_staat(s["key"]) for s in cbr.STATEN]
    gevuld = [v for v in verrijkt if v.get("staat") or v.get("les")]

    rustig = next((s for s in staten if s["key"] == "rustig"), None)
    niet_rustig = {
        "dagen": sum(s["dagen"] for s in staten if s["key"] != "rustig"),
        "netto_eur": round(sum(s["netto_eur"] for s in staten if s["key"] != "rustig"), 2),
    }
    oordeel = ""
    if rustig and rustig["dagen"] and niet_rustig["dagen"]:
        oordeel = (f"Rustige dagen: {rustig['netto_eur']:+.2f} euro over {rustig['dagen']} dagen. "
                   f"Gehaast of moe: {niet_rustig['netto_eur']:+.2f} over {niet_rustig['dagen']}. ")
        oordeel += ("Je staat vooraf lijkt er toe te doen."
                    if rustig["netto_eur"] > niet_rustig["netto_eur"]
                    else "Nog geen duidelijk verschil — blijf het invullen.")

    return {
        "rijen": sorted(verrijkt, key=lambda v: v["datum"], reverse=True),
        "staten": staten,
        "ingevuld": len(gevuld),
        "oordeel": oordeel,
        "lessen": [{"datum": v["datum"], "les": v["les"]} for v in verrijkt if (v.get("les") or "").strip()],
    }


def analyse(trades, sessie_rijen, van="10:00", tot="11:00"):
    return {
        "scorebord": scorebord(trades),
        "streak": valide_streak(trades),
        "venster": venster(trades, van, tot),
        "sessies": sessies(sessie_rijen, trades),
        "schone_weken": schone_weken(trades),
    }


# ---------- schone weken (ronde 3, punt 8) ----------

def _maandag_van(datum):
    from datetime import date, timedelta
    d = date.fromisoformat(datum)
    return (d - timedelta(days=d.weekday())).isoformat()


def schone_weken(trades):
    """
    Een 'A-week' is een week waarin je géén enkele C hebt genomen. Niet een week
    met veel winst -- winst kun je niet sturen, je setupkeuze wel. Dit is de
    mijlpaal die iets zegt over jou en niet over de markt.
    """
    per_week = {}
    for t in trades:
        if not t.get("datum"):
            continue
        per_week.setdefault(_maandag_van(t["datum"]), []).append(t)

    weken = []
    for ma in sorted(per_week):
        rij = per_week[ma]
        c = [t for t in rij if (t.get("grade") or "") == "C"]
        a = [t for t in rij if (t.get("grade") or "") == "A"]
        weken.append({
            "maandag": ma, "n": len(rij),
            "n_a": len(a), "n_c": len(c),
            "schoon": len(c) == 0,
            "netto_eur": round(sum(_netto(t) for t in rij), 2),
        })

    schoon = [w for w in weken if w["schoon"]]
    huidig = 0
    for w in reversed(weken):
        if w["schoon"]:
            huidig += 1
        else:
            break

    return {
        "weken": weken,
        "n_schoon": len(schoon),
        "eerste_schone_week": schoon[0]["maandag"] if schoon else None,
        "huidige_reeks": huidig,
        "boodschap": (
            f"Je eerste week zonder enkele C was {schoon[0]['maandag']}."
            if schoon else
            "Nog geen week zonder een enkele C-setup. Dat is de eerstvolgende mijlpaal "
            "die helemaal in jouw hand ligt."
        ),
    }
