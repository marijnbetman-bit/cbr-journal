# -*- coding: utf-8 -*-
"""
week_review.py -- de weekmail (WP10).

Leest de journal-database over maandag t/m vrijdag, rekent de weekcijfers, laat
optioneel een Sonnet-narratief schrijven, bouwt een HTML-mail in TradingView-
kleuren en verstuurt hem via SMTP.

Ontworpen om door Windows Taakplanner op de VPS gedraaid te worden, vrijdag
17:00. Alles read-only op de journal; de mail wordt nergens bewaard.

Draaien:
    python week_review.py                 # afgelopen ma-vr, verstuurt
    python week_review.py --droog         # bouwt de mail, print 'm, verstuurt niet
    python week_review.py --van 2026-09-15 --tot 2026-09-19

Config (week_review_config.json naast dit bestand, of pad via --config):
    {
      "db_pad": "cbr_journal.db",
      "ontvanger": "marijn.betman@gmail.com",
      "smtp": {"host": "...", "poort": 465, "gebruiker": "...", "wachtwoord": "...",
               "afzender": "journal@westlane.nl"},
      "api": {"gebruik": true, "model": "claude-sonnet-5"}
    }
De API-sleutel komt uit de omgevingsvariabele ANTHROPIC_API_KEY, niet uit config.
"""

import argparse
import json
import os
import smtplib
import sqlite3
import ssl
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from typing import List, Optional

# TradingView-kleuren zoals in de journal
KLEUR = {
    "bg": "#ffffff", "panel": "#f7f4ef", "rand": "#ddd7cd", "tekst": "#1c1c1c",
    "grijs": "#6b6b6b", "accent": "#6d4dea", "groen": "#26a69a", "rood": "#000000",
    "up": "#2962ff",
}


# --------------------------------------------------------------- DB uitlezen

def _kolommen(conn, tabel="trades") -> set:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({tabel})")}


def _euro(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class Weekcijfers:
    van: str
    tot: str
    n: int = 0
    wins: int = 0
    verlies: int = 0
    winrate: Optional[float] = None
    grades: Counter = field(default_factory=Counter)
    valide_ratio: Optional[float] = None
    pnl: float = 0.0
    beste: Optional[dict] = None
    grootste_fout: Optional[str] = None
    fout_telling: Counter = field(default_factory=Counter)
    per_dag: dict = field(default_factory=dict)
    rijen: list = field(default_factory=list)


def drie_getallen(conn, van: str, tot: str) -> dict:
    """De drie getallen uit de Herziening, met de week ervoor ernaast.
    Valt terug op None waar de velden nog niet gevuld zijn."""
    from datetime import date as _d, timedelta as _td
    def blok(v, t):
        wc = haal_week(conn, v, t)
        schoon = None
        try:
            kol = _kolommen(conn)
            if "schoon" in kol:
                r = conn.execute(
                    "SELECT COUNT(*) n, SUM(COALESCE(schoon,0)) s FROM trades "
                    "WHERE datum>=? AND datum<=? AND (status IS NULL OR status!='overgeslagen')",
                    (v, t)).fetchone()
                if r and r[0]:
                    schoon = round(100 * (r[1] or 0) / r[0])
        except Exception:
            pass
        gem_r = verlies_r = None
        try:
            if "resultaat_r" in _kolommen(conn):
                rs = [x[0] for x in conn.execute(
                    "SELECT resultaat_r FROM trades WHERE datum>=? AND datum<=? "
                    "AND resultaat_r IS NOT NULL", (v, t))]
                if rs:
                    gem_r = round(sum(rs) / len(rs), 2)
                    verl = [abs(x) for x in rs if x < 0]
                    if verl:
                        verlies_r = round(sum(verl) / len(verl), 2)
        except Exception:
            pass
        gelaten = 0
        try:
            gelaten = conn.execute(
                "SELECT COUNT(*) FROM geen_trade WHERE datum>=? AND datum<=? "
                "AND soort='bewust_gelaten'", (v, t)).fetchone()[0]
        except Exception:
            pass
        return {"wc": wc, "schoon_pct": schoon, "gem_r": gem_r,
                "verlies_r": verlies_r, "kansen": wc.n + gelaten}

    v0 = _d.fromisoformat(van)
    vorige = blok((v0 - _td(days=7)).isoformat(),
                  (_d.fromisoformat(tot) - _td(days=7)).isoformat())
    return {"nu": blok(van, tot), "vorig": vorige}


def haal_week(conn, van: str, tot: str) -> Weekcijfers:
    """Alle stats van de week. Verdraagt een journal waar sommige kolommen ontbreken."""
    kol = _kolommen(conn)
    conn.row_factory = sqlite3.Row
    # alleen echte, genomen trades tellen mee (geen no-trades/concepten)
    voorwaarde = "datum >= ? AND datum <= ?"
    if "fase" in kol:
        voorwaarde += " AND fase = 'fase2_actief'"
    if "status" in kol:
        voorwaarde += " AND (status IS NULL OR status != 'overgeslagen')"
    rijen = conn.execute(
        f"SELECT * FROM trades WHERE {voorwaarde} ORDER BY datum, tijd_entry",
        (van, tot)).fetchall()

    wc = Weekcijfers(van=van, tot=tot, n=len(rijen))
    for r in rijen:
        netto = _euro(r["resultaat_eur"] if "resultaat_eur" in r.keys() else 0) \
            + _euro(r["charges"] if "charges" in r.keys() else 0)
        wc.pnl += netto
        gewonnen = netto > 0
        wc.wins += 1 if gewonnen else 0
        wc.verlies += 0 if gewonnen else 1

        graad = (r["grade"] if "grade" in r.keys() else None) or "?"
        wc.grades[graad] += 1

        dag = r["datum"]
        wc.per_dag.setdefault(dag, 0.0)
        wc.per_dag[dag] += netto

        # terugkerende fout: uit foutcode(s) of tags
        for veld in ("foutcodes", "foutcode", "tags"):
            if veld in r.keys() and r[veld]:
                for stuk in str(r[veld]).replace(";", ",").split(","):
                    stuk = stuk.strip()
                    if stuk and stuk.lower() != "handmatig":
                        wc.fout_telling[stuk] += 1
                break

        rij = {"datum": dag,
               "tijd": r["tijd_entry"] if "tijd_entry" in r.keys() else "",
               "richting": r["richting"] if "richting" in r.keys() else "",
               "grade": graad, "netto": round(netto, 2),
               "notities": (r["notities"] if "notities" in r.keys() else "") or ""}
        wc.rijen.append(rij)
        if graad == "A" and (wc.beste is None or netto > wc.beste["netto"]):
            wc.beste = rij

    if wc.n:
        wc.winrate = wc.wins / wc.n
        wc.valide_ratio = (wc.grades["A"] + wc.grades["B"]) / wc.n
    if wc.fout_telling:
        wc.grootste_fout = wc.fout_telling.most_common(1)[0][0]
    return wc


# --------------------------------------------------------------- narratief

def _stats_tekst(wc: Weekcijfers) -> str:
    """Compacte, feitelijke samenvatting die ook zonder API altijd klopt."""
    if not wc.n:
        return "Geen trades deze week."
    r = [f"{wc.n} trades, {wc.wins} winst / {wc.verlies} verlies "
         f"(winrate {wc.winrate*100:.0f}%). Netto {wc.pnl:+.2f} euro.",
         f"Grades: " + ", ".join(f"{g}:{wc.grades[g]}" for g in ('A', 'B', 'C', '?')
                                 if wc.grades[g]) +
         f". Valide-setup-ratio {wc.valide_ratio*100:.0f}%."]
    if wc.beste:
        r.append(f"Beste setup: {wc.beste['datum']} {wc.beste['richting']} "
                 f"(grade A, {wc.beste['netto']:+.2f}).")
    if wc.grootste_fout:
        r.append(f"Meest terugkerende fout: {wc.grootste_fout} "
                 f"({wc.fout_telling[wc.grootste_fout]}x).")
    return " ".join(r)


def narratief(wc: Weekcijfers, api_cfg: dict) -> str:
    """Laat Sonnet de week in gewone taal samenvatten. Valt terug op cijfers."""
    if not api_cfg.get("gebruik") or not os.environ.get("ANTHROPIC_API_KEY"):
        return _stats_tekst(wc)
    try:
        import anthropic
        client = anthropic.Anthropic()
        losse = "\n".join(
            f"- {x['datum']} {x['tijd']} {x['richting']} grade {x['grade']} "
            f"{x['netto']:+.2f}: {x['notities'][:200]}" for x in wc.rijen)
        prompt = (
            "Je bent de vaste trading-coach van Marijn. Hij handelt XAUUSD volgens "
            "het CBR-model (bias eerst, expansie, sweep, type-3 shift, entry op 50%). "
            "Schrijf een korte weekbespreking in het Nederlands, warm maar eerlijk, "
            "in gewone zinnen (geen opsomming). Benoem: wat ging goed, wat ging fout, "
            "wat kan beter, en hoe hij er mentaal in zat (leid dat af uit zijn "
            "notities, verzin niets). Max 180 woorden. Sluit af met EEN concrete "
            "focus voor volgende week.\n\n"
            f"Cijfers: {_stats_tekst(wc)}\n\nDe trades:\n{losse}")
        antwoord = client.messages.create(
            model=api_cfg.get("model", "claude-sonnet-5"),
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}])
        return "".join(getattr(b, "text", "") for b in antwoord.content).strip() \
            or _stats_tekst(wc)
    except Exception as e:
        return _stats_tekst(wc) + f"\n\n(narratief overgeslagen: {e})"


# --------------------------------------------------------------- mail bouwen

def _kleur_pnl(x):
    return KLEUR["groen"] if x > 0 else (KLEUR["tekst"] if x == 0 else "#c0392b")


def _pijl(nu, vorig, hoger_is_beter=True):
    if nu is None or vorig is None:
        return "\u2192", "geen vergelijking", "#6b6b6b"
    v = round(nu - vorig, 2)
    if abs(v) < 0.005:
        return "\u2192", "gelijk aan vorige week", "#6b6b6b"
    beter = (v > 0) if hoger_is_beter else (v < 0)
    return ("\u2191" if v > 0 else "\u2193",
            f"{v:+g} t.o.v. vorige week",
            "#0ca30c" if beter else "#d03b3b")


def bouw_html(wc: Weekcijfers, verhaal: str, drie: dict = None) -> str:
    """De weekmail: drie getallen met hun trend, de foutcodes, en een alinea.
    De tradetabel blijft onderaan als bijlage."""
    k = KLEUR
    nu = (drie or {}).get("nu", {})
    vo = (drie or {}).get("vorig", {})

    def tegel(label, waarde, suffix, nu_v, vo_v, hoger_beter=True):
        pijl, tekst, kleur = _pijl(nu_v, vo_v, hoger_beter)
        groot = "\u2014" if waarde is None else f"{waarde:g}{suffix}"
        return (f'<td style="padding:14px 10px;background:{k["panel"]};'
                f'border:1px solid {k["rand"]};border-radius:10px;text-align:center;'
                f'vertical-align:top">'
                f'<div style="font-size:11px;color:{k["grijs"]};text-transform:uppercase;'
                f'letter-spacing:.05em">{label}</div>'
                f'<div style="font-size:26px;font-weight:700;margin:4px 0 2px;'
                f'font-variant-numeric:tabular-nums">{groot}</div>'
                f'<div style="font-size:11px;color:{kleur}">{pijl} {tekst}</div></td>')

    verlies_r = nu.get("verlies_r")
    verlies_regel = ("nog geen verliezen met R" if verlies_r is None else
                     (f"gemiddeld verlies {verlies_r:g}R \u2014 onder 1R, goed"
                      if verlies_r <= 1 else
                      f"gemiddeld verlies {verlies_r:g}R \u2014 boven 1R, dit is je lek"))

    fouten = ""
    if wc.fout_telling:
        top = wc.fout_telling.most_common(5)
        maxn = top[0][1]
        for naam, aantal in top:
            breedte = round(100 * aantal / maxn)
            fouten += (
                f'<tr><td style="padding:4px 8px 4px 0;font-size:14px;width:45%">{naam}</td>'
                f'<td style="padding:4px 0"><div style="background:{k["rand"]};'
                f'border-radius:4px;height:9px"><div style="width:{breedte}%;height:9px;'
                f'background:{k["accent"]};border-radius:4px"></div></div></td>'
                f'<td style="padding:4px 0 4px 8px;font-size:13px;color:{k["grijs"]};'
                f'text-align:right;width:24px">{aantal}</td></tr>')
        fouten = (f'<h3 style="font-size:15px;margin:22px 0 6px">Foutcodes</h3>'
                  f'<table width="100%" cellspacing="0" cellpadding="0">{fouten}</table>')

    rijen_html = ""
    for x in wc.rijen:
        netto = x["netto"]
        kleur = k["groen"] if netto > 0 else ("#c0392b" if netto < 0 else k["tekst"])
        rijen_html += (
            f'<tr><td style="padding:5px 8px;border-bottom:1px solid {k["rand"]}">{x["datum"]}</td>'
            f'<td style="padding:5px 8px;border-bottom:1px solid {k["rand"]}">{x["tijd"] or "-"}</td>'
            f'<td style="padding:5px 8px;border-bottom:1px solid {k["rand"]}">{x["richting"]}</td>'
            f'<td style="padding:5px 8px;border-bottom:1px solid {k["rand"]};color:{kleur};'
            f'text-align:right;font-variant-numeric:tabular-nums">{netto:+.2f}</td></tr>')

    verhaal_html = "".join(f"<p style='margin:0 0 10px'>{p}</p>"
                           for p in verhaal.split("\n") if p.strip())

    return f"""<!doctype html><html><body style="margin:0;background:{k['bg']};
color:{k['tekst']};font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<div style="max-width:620px;margin:0 auto;padding:22px 16px">
  <div style="font-size:13px;color:{k['grijs']}">Trading-week {wc.van} t/m {wc.tot}</div>
  <h1 style="font-size:21px;margin:4px 0 18px">Drie getallen</h1>
  <table width="100%" cellspacing="8" cellpadding="0" style="border-collapse:separate"><tr>
    {tegel("Schone trades", nu.get("schoon_pct"), "%", nu.get("schoon_pct"), vo.get("schoon_pct"))}
    {tegel("Gemiddelde R", nu.get("gem_r"), "", nu.get("gem_r"), vo.get("gem_r"))}
    {tegel("Kansen", nu.get("kansen"), "", nu.get("kansen"), vo.get("kansen"))}
  </tr></table>
  <p style="font-size:13px;color:{k['grijs']};margin:8px 2px 0">{verlies_regel}</p>
  <div style="background:{k['panel']};border:1px solid {k['rand']};border-radius:10px;
       padding:16px 18px;margin:18px 0;line-height:1.5">
    <div style="font-size:11px;color:{k['accent']};text-transform:uppercase;
         letter-spacing:.05em;margin-bottom:8px">Weekbespreking</div>
    {verhaal_html}
  </div>
  {fouten}
  <h3 style="font-size:15px;margin:22px 0 6px">De trades</h3>
  <table width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-size:14px">
    <tr style="text-align:left;color:{k['grijs']}">
      <th style="padding:5px 8px">Datum</th><th style="padding:5px 8px">Tijd</th>
      <th style="padding:5px 8px">Richting</th>
      <th style="padding:5px 8px;text-align:right">Netto</th></tr>
    {rijen_html}
  </table>
  <p style="font-size:12px;color:{k['grijs']};margin-top:22px">
    Drie getallen, verder niets. Het saldo staat bewust niet bovenaan &mdash; daar
    moet je niet op sturen. De conclusie trek je zelf.</p>
</div></body></html>"""


# --------------------------------------------------------------- versturen

def verstuur(html: str, tekst: str, onderwerp: str, ontvanger: str, smtp: dict):
    msg = EmailMessage()
    msg["Subject"] = onderwerp
    msg["From"] = smtp.get("afzender", smtp["gebruiker"])
    msg["To"] = ontvanger
    msg.set_content(tekst)
    msg.add_alternative(html, subtype="html")
    ctx = ssl.create_default_context()
    poort = int(smtp.get("poort", 465))
    if poort == 465:
        with smtplib.SMTP_SSL(smtp["host"], poort, context=ctx) as s:
            s.login(smtp["gebruiker"], smtp["wachtwoord"])
            s.send_message(msg)
    else:  # 587 STARTTLS
        with smtplib.SMTP(smtp["host"], poort) as s:
            s.starttls(context=ctx)
            s.login(smtp["gebruiker"], smtp["wachtwoord"])
            s.send_message(msg)


# --------------------------------------------------------------- CLI

def _week_ma_vr(vandaag: date):
    """De maandag t/m vrijdag van de week waar 'vandaag' in valt."""
    ma = vandaag - timedelta(days=vandaag.weekday())
    return ma.isoformat(), (ma + timedelta(days=4)).isoformat()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "week_review_config.json"))
    p.add_argument("--van")
    p.add_argument("--tot")
    p.add_argument("--droog", action="store_true", help="bouw + print, verstuur niet")
    a = p.parse_args(argv)

    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    van, tot = (a.van, a.tot) if a.van and a.tot else _week_ma_vr(date.today())

    conn = sqlite3.connect(cfg["db_pad"])
    try:
        wc = haal_week(conn, van, tot)
        drie = drie_getallen(conn, van, tot)
    finally:
        conn.close()

    verhaal = narratief(wc, cfg.get("api", {}))
    html = bouw_html(wc, verhaal, drie)
    onderwerp = f"Trading-week {van} t/m {tot}: {wc.pnl:+.2f} euro, {wc.n} trades"

    if a.droog:
        print(onderwerp)
        print(_stats_tekst(wc))
        print("\n--- narratief ---\n" + verhaal)
        print(f"\n[droog] zou mailen naar {cfg['ontvanger']}")
        return

    verstuur(html, _stats_tekst(wc) + "\n\n" + verhaal, onderwerp,
             cfg["ontvanger"], cfg["smtp"])
    print(f"Weekmail verstuurd naar {cfg['ontvanger']} ({onderwerp})")


if __name__ == "__main__":
    main()
