# -*- coding: utf-8 -*-
"""
export_offline.py -- je journal als één los HTML-bestand.

Alles zit erin (cijfers, equitylijn, elke trade met checks, criteria, notities
en chart), dus het bestand opent op elk apparaat: telefoon, iPad, andermans
laptop, als bijlage in een mail. Er hoeft niets te draaien.
"""

import base64
import os
from datetime import date, datetime
from html import escape

CHECKS = [("check_venster", "venster"), ("check_dagmax", "trade 1-2"),
          ("check_bias", "bias gecheckt"), ("check_entry50", "entry 50%"),
          ("check_sl", "SL 5+ pts")]
CRIT = [("f2_bias", "1H-bias"), ("f2_dxy", "DXY invers"), ("f2_expansie", "expansie"),
        ("f2_sweep", "sweep"), ("f2_shift", "type-3 shift")]
MAANDEN = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]
DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
MAX_BEELD = 1_500_000


def _eur(v, teken=True):
    if v is None:
        return "–"
    s = f"{abs(v):.2f}".replace(".", ",")
    if v < 0:
        return "−€" + s
    return ("+€" if teken else "€") + s


def _dag(iso):
    d = date.fromisoformat(iso)
    return f"{DAGEN[d.weekday()]} {d.day} {MAANDEN[d.month - 1]} {d.year}"


def _beeld(hier, pad):
    vol = os.path.join(hier, pad)
    if not os.path.isfile(vol) or os.path.getsize(vol) > MAX_BEELD:
        return ""
    if pad.lower().endswith(".svg"):
        with open(vol, encoding="utf-8") as f:
            svg = f.read()
        return svg.replace("<svg ", '<svg class="chart" ', 1)
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "gif": "image/gif"}.get(pad.rsplit(".", 1)[-1].lower())
    if not mime:
        return ""
    with open(vol, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f'<img class="chart" alt="screenshot" src="data:{mime};base64,{b64}">'


def _vinkjes(t):
    uit = []
    for k, lbl in CHECKS:
        v = t.get(k)
        cls = "ja" if v == 1 else ("nee" if v == 0 else "leeg")
        uit.append(f'<span class="vk {cls}">{escape(lbl)}</span>')
    uit.append('<span class="scheid"></span>')
    for k, lbl in CRIT:
        v = t.get(k)
        cls = "ja" if v == "yes" else ("nee" if v == "no" else "leeg")
        uit.append(f'<span class="vk {cls}">{escape(lbl)}</span>')
    return "".join(uit)


def _equity(trades):
    punten, som = [0.0], 0.0
    for t in trades:
        if t.get("netto") is not None:
            som += t["netto"]
            punten.append(round(som, 2))
    if len(punten) < 3:
        return ""
    b, h, ml, mr, mt, mb = 720, 180, 8, 64, 14, 22
    lo, hi = min(punten), max(punten)
    if hi == lo:
        hi = lo + 1
    sx = (b - ml - mr) / (len(punten) - 1)

    def y(v):
        return mt + (hi - v) / (hi - lo) * (h - mt - mb)
    pts = " ".join(f"{ml + i * sx:.1f},{y(v):.1f}" for i, v in enumerate(punten))
    nul = y(0) if lo <= 0 <= hi else None
    eind = punten[-1]
    kleur = "var(--groen)" if eind >= 0 else "var(--rood)"
    delen = [f'<svg class="equity" viewBox="0 0 {b} {h}" role="img" '
             f'aria-label="Cumulatief netto resultaat">']
    for k in range(3):
        v = lo + (hi - lo) * k / 2
        delen.append(f'<line x1="{ml}" x2="{b - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                     f'<text x="{b - mr + 6}" y="{y(v) + 4:.1f}" class="as">{_eur(v, False)}</text>')
    if nul is not None:
        delen.append(f'<line x1="{ml}" x2="{b - mr}" y1="{nul:.1f}" y2="{nul:.1f}" class="nul"/>')
    delen.append(f'<polygon points="{ml},{y(lo):.1f} {pts} {ml + (len(punten) - 1) * sx:.1f},{y(lo):.1f}" '
                 f'fill="{kleur}" opacity="0.10"/>')
    delen.append(f'<polyline points="{pts}" fill="none" stroke="{kleur}" stroke-width="2"/>')
    ex, ey = ml + (len(punten) - 1) * sx, y(eind)
    delen.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3.5" fill="{kleur}"/>')
    delen.append("</svg>")
    return "".join(delen)


def maak(con, trades, hier, fase=2):
    n = len(trades)
    met = [t for t in trades if t.get("netto") is not None]
    netto = sum(t["netto"] for t in met)
    winst = [t for t in met if t["netto"] > 0]
    winrate = (len(winst) / len(met) * 100) if met else 0
    rs = [t["resultaat_r"] for t in trades if t.get("resultaat_r") is not None]
    gem_r = sum(rs) / len(rs) if rs else None
    gecheckt = [t for t in trades if t.get("schoon") is not None]
    schoon = (sum(1 for t in gecheckt if t["schoon"] == 1) / len(gecheckt) * 100) if gecheckt else None
    grades = {g: sum(1 for t in trades if t.get("grade") == g) for g in "ABC"}

    tegels = [
        ("trades", str(n), ""),
        ("netto", _eur(netto), "pos" if netto >= 0 else "neg"),
        ("winrate", f"{winrate:.0f}%", ""),
        ("gem. R", "–" if gem_r is None else f"{gem_r:+.2f}R".replace(".", ","), ""),
        ("schone trades", "–" if schoon is None else f"{schoon:.0f}%", ""),
        ("grade A · B · C", f"{grades['A']} · {grades['B']} · {grades['C']}", ""),
    ]
    tegels_html = "".join(f'<div class="tegel"><span>{escape(l)}</span><b class="{c}">{escape(w)}</b></div>'
                          for l, w, c in tegels)

    # screenshots per trade
    shots = {}
    for r in con.execute("SELECT trade_id, pad FROM screenshots WHERE trade_id IS NOT NULL ORDER BY id"):
        shots.setdefault(r["trade_id"], []).append(r["pad"])

    per_dag = {}
    for t in trades:
        per_dag.setdefault(t["datum"], []).append(t)

    dagen_html = []
    for d in sorted(per_dag, reverse=True):
        rij = per_dag[d]
        dn = sum(t["netto"] or 0 for t in rij if t.get("netto") is not None)
        kaarten = []
        for t in sorted(rij, key=lambda x: (x.get("tijd_entry") or "", x["id"])):
            beelden = "".join(_beeld(hier, p) for p in shots.get(t["id"], []))
            r_txt = "" if t.get("resultaat_r") is None else f'{t["resultaat_r"]:+.2f}R'.replace(".", ",")
            meta = " · ".join(x for x in [
                (t.get("richting") or "").upper(),
                f'{t.get("tijd_entry") or ""}' + (f'–{t["tijd_exit"]}' if t.get("tijd_exit") else ""),
                t.get("exit_reden") or "",
                f'RR {t["rr"]:.1f}'.replace(".", ",") if t.get("rr") is not None else "",
                f'{t["lot"]:.2f} lot'.replace(".", ",") if t.get("lot") else "",
            ] if x)
            notitie = escape(t.get("notities") or "").replace("\n", "<br>")
            kaarten.append(f"""
<article class="trade">
  <header>
    <span class="grade g{escape(t.get('grade') or 'C')}">{escape(t.get('grade') or '–')}</span>
    <div class="kop"><b class="{'pos' if (t.get('netto') or 0) >= 0 else 'neg'}">{_eur(t.get('resultaat_eur'))}</b>
      <small>netto {_eur(t.get('netto'))} {('· ' + r_txt) if r_txt else ''}</small></div>
    <div class="meta">{escape(meta)} <span class="id">#{t['id']}</span></div>
  </header>
  <div class="vinkjes">{_vinkjes(t)}</div>
  {f'<p class="notitie">{notitie}</p>' if notitie else ''}
  {f'<details><summary>chart</summary>{beelden}</details>' if beelden else ''}
</article>""")
        dagen_html.append(f"""
<section class="dag">
  <h2>{_dag(d)} <span class="{'pos' if dn >= 0 else 'neg'}">{_eur(dn)}</span></h2>
  {''.join(kaarten)}
</section>""")

    fase_txt = "fase 2 — bias eerst" if fase == 2 else ("fase 1 — archief" if fase == 1 else "alle trades")
    return f"""<!doctype html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CBR journal · {date.today().day} {MAANDEN[date.today().month - 1]}</title>
<style>
:root{{--bg:#f7f4ef;--panel:#fff;--rand:#ddd7cd;--tekst:#1d1b19;--zacht:#6b665f;
  --accent:#6d4dea;--groen:#1a9d5a;--rood:#d23c36;--leeg:#ece7de}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16151a;--panel:#1f1e25;--rand:#34323b;
  --tekst:#ece9e4;--zacht:#a39e96;--accent:#9d86f5;--groen:#3cc47d;--rood:#f0625c;--leeg:#2c2a32}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tekst);
  font:15px/1.5 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding:0 16px 48px}}
.wrap{{max-width:860px;margin:0 auto}}
h1{{font-size:24px;margin:28px 0 2px;text-wrap:balance}}
.sub{{color:var(--zacht);font-size:13px;margin-bottom:18px}}
.tegels{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px}}
.tegel{{background:var(--panel);border:1px solid var(--rand);border-radius:10px;padding:10px 12px}}
.tegel span{{display:block;font-size:11px;color:var(--zacht);letter-spacing:.04em;text-transform:uppercase}}
.tegel b{{font-size:20px;font-variant-numeric:tabular-nums}}
.pos{{color:var(--groen)}}.neg{{color:var(--rood)}}
.equity{{width:100%;height:auto;margin:16px 0 4px;background:var(--panel);border:1px solid var(--rand);border-radius:10px}}
.equity .grid{{stroke:var(--rand)}}.equity .nul{{stroke:var(--zacht);stroke-dasharray:3 3}}
.equity .as{{fill:var(--zacht);font-size:11px}}
.dag h2{{font-size:15px;margin:28px 0 8px;display:flex;justify-content:space-between;
  border-bottom:1px solid var(--rand);padding-bottom:6px}}
.trade{{background:var(--panel);border:1px solid var(--rand);border-radius:12px;padding:12px 14px;margin-bottom:8px}}
.trade header{{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;align-items:center}}
.grade{{grid-row:span 2;width:38px;height:38px;border-radius:9px;display:grid;place-items:center;
  font-weight:700;font-size:18px;color:#fff;background:var(--zacht)}}
.gA{{background:var(--groen)}}.gB{{background:var(--accent)}}.gC{{background:#9b948a}}
.kop b{{font-size:18px;font-variant-numeric:tabular-nums}}.kop small{{color:var(--zacht);margin-left:6px}}
.meta{{color:var(--zacht);font-size:13px}}.id{{opacity:.6}}
.vinkjes{{display:flex;flex-wrap:wrap;gap:4px;margin:10px 0 2px}}
.vk{{font-size:12px;padding:2px 8px;border-radius:99px;background:var(--leeg);color:var(--zacht)}}
.vk.ja{{background:color-mix(in srgb,var(--groen) 16%,transparent);color:var(--groen)}}
.vk.nee{{background:color-mix(in srgb,var(--rood) 14%,transparent);color:var(--rood);text-decoration:line-through}}
.scheid{{width:10px}}
.notitie{{font-size:14px;margin:8px 0 0;max-width:68ch}}
details{{margin-top:8px}}summary{{cursor:pointer;color:var(--accent);font-size:13px}}
.chart{{width:100%;height:auto;border-radius:8px;margin-top:8px;border:1px solid var(--rand)}}
.voet{{margin-top:36px;color:var(--zacht);font-size:12px}}
</style></head><body><div class="wrap">
<h1>CBR journal</h1>
<div class="sub">{escape(fase_txt)} · export van {_dag(date.today().isoformat())}, {datetime.now():%H:%M}
 · resultaten zoals de broker ze boekte</div>
<div class="tegels">{tegels_html}</div>
{_equity(trades)}
{''.join(dagen_html) or '<p>Nog geen trades.</p>'}
<p class="voet">Groen = ja, doorgestreept = nee, grijs = niet ingevuld.
Eerste vijf zijn je discipline-checks, de laatste vijf je CBR-criteria.</p>
</div></body></html>"""
