# -*- coding: utf-8 -*-
"""
weekgetallen.py -- de drie weekgetallen en het scherm /hoe-sta-ik-ervoor (blok 3).

Drie getallen, en verder niets:

  1. schone-trade-%   -- aandeel trades waar alle vijf pre-trade vinkjes aan stonden
  2. R                -- gemiddelde R, en vooral: blijft je gemiddelde verlies onder 1R
  3. gemist/genomen   -- hoeveel setups langskwamen en wat je ermee deed

Bewust géén saldo als eerste tegel: daar moet je niet op sturen. Het saldo staat
onderaan bij de tabel, waar het hoort.

Inhaken in de journal (app/main.py):
    from weekgetallen import router as weekgetallen_router
    app.include_router(weekgetallen_router)
"""

import os
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

HIER = os.path.dirname(os.path.abspath(__file__))
DB_PAD = os.path.join(HIER, "cbr_journal.db")

CHECK_LABELS = {
    "check_venster": "binnen venster",
    "check_dagmax": "binnen dagmaximum",
    "check_bias": "bias gecheckt",
    "check_entry50": "entry op 50%",
    "check_sl": "SL voorbij sweep",
}


def _conn(pad=None):
    con = sqlite3.connect(pad or DB_PAD)
    con.row_factory = sqlite3.Row
    return con


def _kolommen(con, tabel="trades"):
    return {r[1] for r in con.execute(f"PRAGMA table_info({tabel})")}


def week_sleutel(d: date) -> str:
    jaar, week, _ = d.isocalendar()
    return f"{jaar}-W{week:02d}"


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def verzamel(con, weken: int = 8, vandaag: Optional[date] = None) -> List[dict]:
    """Per week de drie getallen. Oudste week eerst, huidige week als laatste."""
    vandaag = vandaag or date.today()
    kol = _kolommen(con)
    heeft_schoon = "schoon" in kol
    heeft_r = "resultaat_r" in kol
    tabellen = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    heeft_geen_trade = "geen_trade" in tabellen

    start = week_start(vandaag) - timedelta(weeks=weken - 1)
    rijen = con.execute(
        "SELECT * FROM trades WHERE datum >= ? "
        "AND (status IS NULL OR status != 'overgeslagen') ORDER BY datum",
        (start.isoformat(),)).fetchall()

    per_week = {}
    for i in range(weken):
        d = start + timedelta(weeks=i)
        per_week[week_sleutel(d)] = {
            "week": week_sleutel(d), "van": d.isoformat(),
            "trades": 0, "schoon": 0, "r_som": 0.0, "r_n": 0,
            "verlies_r": [], "pnl": 0.0,
            "gelaten": 0, "niets_gezien": 0,
            "faal": Counter(), "foutcodes": Counter(),
        }

    for r in rijen:
        try:
            d = date.fromisoformat(r["datum"])
        except (TypeError, ValueError):
            continue
        w = per_week.get(week_sleutel(d))
        if w is None:
            continue
        w["trades"] += 1
        w["pnl"] += (r["resultaat_eur"] or 0) + (
            r["charges"] if "charges" in r.keys() and r["charges"] else 0)
        if heeft_schoon and r["schoon"]:
            w["schoon"] += 1
        if heeft_schoon:
            for k in CHECK_LABELS:
                if k in r.keys() and r[k] == 0:
                    w["faal"][k] += 1
        if heeft_r and r["resultaat_r"] is not None:
            w["r_som"] += r["resultaat_r"]
            w["r_n"] += 1
            if r["resultaat_r"] < 0:
                w["verlies_r"].append(abs(r["resultaat_r"]))
        if "foutcodes" in r.keys() and r["foutcodes"]:
            for c in str(r["foutcodes"]).split(","):
                c = c.strip()
                if c:
                    w["foutcodes"][c] += 1

    if heeft_geen_trade:
        for g in con.execute("SELECT datum, soort FROM geen_trade WHERE datum >= ?",
                             (start.isoformat(),)):
            try:
                w = per_week.get(week_sleutel(date.fromisoformat(g["datum"])))
            except (TypeError, ValueError):
                continue
            if w:
                if g["soort"] == "bewust_gelaten":
                    w["gelaten"] += 1
                else:
                    w["niets_gezien"] += 1

    uit = []
    for w in sorted(per_week.values(), key=lambda x: x["van"]):
        n = w["trades"]
        w["schoon_pct"] = round(100 * w["schoon"] / n) if n else None
        w["gem_r"] = round(w["r_som"] / w["r_n"], 2) if w["r_n"] else None
        w["gem_verlies_r"] = (round(sum(w["verlies_r"]) / len(w["verlies_r"]), 2)
                              if w["verlies_r"] else None)
        w["kansen"] = n + w["gelaten"]
        w["pnl"] = round(w["pnl"], 2)
        uit.append(w)
    return uit


def _delta(nu, vorig):
    """(tekst, richting) voor de vergelijking met vorige week."""
    if nu is None or vorig is None:
        return "geen vergelijking", "neutraal"
    v = round(nu - vorig, 2)
    if abs(v) < 0.005:
        return "gelijk aan vorige week", "neutraal"
    return (f"{v:+g} t.o.v. vorige week", "op" if v > 0 else "neer")


# --------------------------------------------------------------- tekenen

def _lijn_svg(punten, *, breedte=300, hoogte=64, kleur="var(--serie)", suffix=""):
    """Kleine trendlijn. Eén serie, dus geen legenda nodig -- de titel benoemt hem.
    Punten: lijst van (label, waarde|None). None = week zonder data, wordt gat."""
    echte = [(i, v) for i, (_, v) in enumerate(punten) if v is not None]
    if len(echte) < 2:
        return ('<div class="geenchart">nog te weinig weken om een lijn te '
                'tekenen</div>')
    xs = [i for i, _ in echte]
    ys = [v for _, v in echte]
    lo, hi = min(ys), max(ys)
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    pad_l, pad_r, pad_t, pad_b = 6, 34, 10, 16
    bx = breedte - pad_l - pad_r
    by = hoogte - pad_t - pad_b
    n = max(1, len(punten) - 1)

    def px(i):
        return pad_l + bx * i / n

    def py(v):
        return pad_t + by * (1 - (v - lo) / (hi - lo))

    d = " ".join(f"{'M' if k == 0 else 'L'}{px(i):.1f},{py(v):.1f}"
                 for k, (i, v) in enumerate(echte))
    # markers >= 8px raakvlak; grid recessief; laatste punt krijgt een direct label
    punten_svg = "".join(
        f'<circle class="pt" cx="{px(i):.1f}" cy="{py(v):.1f}" r="3.5" '
        f'data-label="{punten[i][0]}" data-waarde="{v:g}{suffix}"/>'
        for i, v in echte)
    li, lv = echte[-1]
    label = (f'<text class="eindlabel" x="{px(li) + 7:.1f}" y="{py(lv) + 4:.1f}">'
             f'{lv:g}{suffix}</text>')
    return (f'<svg class="trend" viewBox="0 0 {breedte} {hoogte}" role="img" '
            f'preserveAspectRatio="none">'
            f'<line class="as" x1="{pad_l}" y1="{hoogte - pad_b}" '
            f'x2="{breedte - pad_r}" y2="{hoogte - pad_b}"/>'
            f'<path class="lijn" d="{d}" style="stroke:{kleur}"/>{punten_svg}{label}</svg>')


def _balken(tellingen, labels=None, maxbreedte=100):
    """Horizontale balkjes voor 'waar ging het mis'. Eén serie, magnitude."""
    if not tellingen:
        return '<div class="geenchart">niets te tonen — mooi zo</div>'
    top = max(tellingen.values())
    rijen = ""
    for sleutel, aantal in tellingen.most_common(7):
        naam = (labels or {}).get(sleutel, sleutel)
        pct = round(100 * aantal / top)
        rijen += (f'<div class="balkrij"><span class="balklabel">{naam}</span>'
                  f'<span class="balkbaan"><span class="balk" style="width:{pct}%"></span></span>'
                  f'<span class="balkgetal">{aantal}</span></div>')
    return rijen


# --------------------------------------------------------------- route

@router.get("/hoe-sta-ik-ervoor", response_class=HTMLResponse)
def overzicht():
    con = _conn()
    try:
        weken = verzamel(con, weken=8)
    finally:
        con.close()
    return bouw_pagina(weken)


def bouw_pagina(weken: List[dict]) -> str:
    nu = weken[-1] if weken else {}
    vorig = weken[-2] if len(weken) > 1 else {}

    def tegel(titel, waarde, suffix, uitleg, punten, sleutel, omgekeerd=False):
        w = nu.get(sleutel)
        v = vorig.get(sleutel)
        tekst, richting = _delta(w, v)
        if omgekeerd and richting in ("op", "neer"):
            richting = "neer" if richting == "op" else "op"
        pijl = {"op": "↑", "neer": "↓", "neutraal": "→"}[richting]
        groot = "—" if w is None else f"{w:g}{suffix}"
        return (f'<section class="tegel"><h2>{titel}</h2>'
                f'<div class="groot">{groot}</div>'
                f'<div class="delta {richting}">{pijl} {tekst}</div>'
                f'<p class="uitleg">{uitleg}</p>'
                f'{_lijn_svg(punten, suffix=suffix)}</section>')

    p_schoon = [(w["week"][-3:], w["schoon_pct"]) for w in weken]
    p_r = [(w["week"][-3:], w["gem_r"]) for w in weken]
    p_kans = [(w["week"][-3:], w["kansen"] or None) for w in weken]

    faal = Counter()
    fout = Counter()
    for w in weken[-4:]:
        faal.update(w["faal"])
        fout.update(w["foutcodes"])

    verlies_r = nu.get("gem_verlies_r")
    verlies_tekst = ("nog geen verliezen met R" if verlies_r is None else
                     f"gemiddeld verlies {verlies_r:g}R "
                     + ("— onder 1R, goed" if verlies_r <= 1
                        else "— boven 1R, dit is je lek"))

    def _tabelrij(w):
        schoon = "—" if w["schoon_pct"] is None else f'{w["schoon_pct"]}%'
        r = "—" if w["gem_r"] is None else f'{w["gem_r"]:g}'
        return (f'<tr><td>{w["week"]}</td><td>{w["trades"]}</td><td>{schoon}</td>'
                f'<td>{r}</td><td>{w["kansen"]}</td>'
                f'<td class="num">{w["pnl"]:+.2f}</td></tr>')

    tabel = "".join(_tabelrij(w) for w in weken)

    return PAGINA \
        .replace("__TEGELS__",
                 tegel("Schone trades", None, "%",
                       "Alle vijf vinkjes aan vóór je instapte. Dit is het enige "
                       "getal dat volledig van jou is.", p_schoon, "schoon_pct")
                 + tegel("Gemiddelde R", None, "",
                         verlies_tekst, p_r, "gem_r")
                 + tegel("Kansen deze week", None, "",
                         "Genomen plus bewust gelaten. Zonder dit getal weet je niet "
                         "of een rustige week discipline was of afwezigheid.",
                         p_kans, "kansen"))\
        .replace("__FAAL__", _balken(faal, CHECK_LABELS))\
        .replace("__FOUT__", _balken(fout))\
        .replace("__TABEL__", tabel)


PAGINA = """<!doctype html><html lang="nl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hoe sta ik ervoor</title>
<style>
 :root{--bg:#f7f4ef;--panel:#fff;--rand:#ddd7cd;--tekst:#1c1c1c;--grijs:#6b6b6b;
       --serie:#6d4dea;--goed:#0ca30c;--slecht:#d03b3b;--raster:#e7e1d6}
 @media (prefers-color-scheme: dark){:root:where(:not([data-theme=light])){
   --bg:#1a1a19;--panel:#232321;--rand:#3a3a36;--tekst:#f5f4f0;--grijs:#a8a69c;
   --serie:#9085e9;--goed:#0ca30c;--slecht:#e06060;--raster:#33332f}}
 :root[data-theme=dark]{--bg:#1a1a19;--panel:#232321;--rand:#3a3a36;--tekst:#f5f4f0;
   --grijs:#a8a69c;--serie:#9085e9;--raster:#33332f}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--tekst);padding:16px;max-width:560px;
      margin:0 auto;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
 h1{font-size:20px;margin:4px 0 14px}
 h2{font-size:13px;font-weight:600;color:var(--grijs);text-transform:uppercase;
    letter-spacing:.05em;margin:0 0 6px}
 h3{font-size:15px;margin:22px 0 8px}
 .tegel{background:var(--panel);border:1px solid var(--rand);border-radius:12px;
        padding:14px 16px;margin-bottom:12px}
 .groot{font-size:34px;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums}
 .delta{font-size:13px;margin-top:2px}
 .delta.op{color:var(--goed)} .delta.neer{color:var(--slecht)} .delta.neutraal{color:var(--grijs)}
 .uitleg{font-size:13px;color:var(--grijs);margin:8px 0 2px;line-height:1.45}
 svg.trend{width:100%;height:64px;overflow:visible;margin-top:6px}
 .lijn{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
 .pt{fill:var(--panel);stroke:var(--serie);stroke-width:2}
 .as{stroke:var(--raster);stroke-width:1}
 .eindlabel{font-size:11px;fill:var(--grijs);font-variant-numeric:tabular-nums}
 .geenchart{font-size:13px;color:var(--grijs);padding:14px 0 4px}
 .balkrij{display:flex;align-items:center;gap:10px;margin:7px 0;font-size:14px}
 .balklabel{flex:0 0 42%;color:var(--tekst)}
 .balkbaan{flex:1;height:10px;background:var(--raster);border-radius:5px;overflow:hidden}
 .balk{display:block;height:100%;background:var(--serie);border-radius:5px}
 .balkgetal{flex:0 0 22px;text-align:right;color:var(--grijs);font-variant-numeric:tabular-nums}
 table{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
 th,td{padding:6px 8px;border-bottom:1px solid var(--rand);text-align:left}
 th{color:var(--grijs);font-weight:600}
 td.num{text-align:right;font-variant-numeric:tabular-nums}
 details{margin-top:20px} summary{cursor:pointer;color:var(--grijs);font-size:14px}
 #tip{position:fixed;pointer-events:none;background:var(--panel);border:1px solid var(--rand);
      border-radius:8px;padding:6px 9px;font-size:13px;display:none;box-shadow:0 2px 8px rgba(0,0,0,.12)}
</style></head><body>
<h1>Hoe sta ik ervoor</h1>
__TEGELS__

<h3>Waar het misgaat</h3>
<div class="tegel">__FAAL__
<p class="uitleg">Hoe vaak elk vinkje uit stond, over de laatste vier weken. De
bovenste is je werk voor volgende week.</p></div>

<h3>Foutcodes</h3>
<div class="tegel">__FOUT__</div>

<details><summary>De cijfers als tabel</summary>
<table><tr><th>Week</th><th>Trades</th><th>Schoon</th><th>Gem R</th><th>Kansen</th>
<th class="num">Saldo</th></tr>__TABEL__</table></details>

<div id="tip"></div>
<script>
const tip=document.getElementById('tip');
document.querySelectorAll('svg.trend .pt').forEach(p=>{
  const toon=e=>{const r=p.getBoundingClientRect();
    tip.textContent=p.dataset.label+': '+p.dataset.waarde;
    tip.style.display='block';
    tip.style.left=Math.min(window.innerWidth-120, r.left)+'px';
    tip.style.top=(r.top-34)+'px';};
  p.addEventListener('mouseenter',toon);
  p.addEventListener('touchstart',toon,{passive:true});
  p.addEventListener('mouseleave',()=>tip.style.display='none');
  p.addEventListener('touchend',()=>setTimeout(()=>tip.style.display='none',1200));
});
</script></body></html>"""
