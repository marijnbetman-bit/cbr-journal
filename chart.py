# -*- coding: utf-8 -*-
"""
Tekent een candlestick-snapshot als SVG -- geen matplotlib of Pillow nodig,
puur tekst. Kleuren volgen Marijns TradingView: witte achtergrond, blauwe
up-candles, zwarte down-candles. Entry/SL/TP komen als lijnen op de chart.

Eén functie: maak_svg(candles, ...) -> str met de SVG-inhoud.
Bewaar die als .svg in de screenshots-map en de journal toont hem gewoon.
"""

from html import escape

# TradingView-kleuren van Marijn
UP = "#2962ff"        # blauwe up-candle
DOWN = "#111111"      # zwarte down-candle
BG = "#ffffff"
GRID = "#eceff4"
AS = "#8a8f98"        # aslabels
ENTRY_KLEUR = "#2962ff"
SL_KLEUR = "#e53935"
TP_KLEUR = "#1a9d5a"


def _fmt(p, decimalen=2):
    return f"{p:,.{decimalen}f}".replace(",", " ").replace(".", ",")


def maak_svg(candles, entry=None, sl=None, tp=None, richting="",
             symbool="XAUUSD", tier="", kop_extra="", rr=None,
             breedte=960, hoogte=540, markers=None, markeer_laatste=True,
             exit_prijs=None, zone_van=None, zone_tot=None, info=None):
    """
    candles : lijst [open, high, low, close], oudste eerst.
    entry/sl/tp : prijsniveaus die als lijn getekend worden (mag None).
    markers     : optioneel [(candle_index, kleur, tekst), ...] -- verticale
                  stippellijn op die candle (bv. waar je in- en uitstapte).
    markeer_laatste : driehoekje boven de laatste candle (signaalmoment).
    exit_prijs  : optioneel; tekent een klein rondje op de exit-marker.
    zone_van/zone_tot : candle-index van in- en uitstap. Dan komt er een
                  TradingView-achtig positievak: rood (entry->SL), groen (entry->TP).
    info        : optioneel label rechtsboven in het plot, bv. "+EUR 6,22 · +0,85R".
    """
    if not candles:
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="60">'
                '<text x="10" y="35">geen candles</text></svg>' % breedte)

    marge_l, marge_r, marge_t, marge_b = 10, 74, 46, 26
    pl_x0, pl_x1 = marge_l, breedte - marge_r
    pl_y0, pl_y1 = marge_t, hoogte - marge_b
    pl_b = pl_x1 - pl_x0
    pl_h = pl_y1 - pl_y0

    niveaus = [n for n in (entry, sl, tp) if n is not None]
    hoog = max(max(c[1] for c in candles), *niveaus) if niveaus else max(c[1] for c in candles)
    laag = min(min(c[2] for c in candles), *niveaus) if niveaus else min(c[2] for c in candles)
    marge = (hoog - laag) * 0.08 or 1.0
    hoog += marge
    laag -= marge
    spanwijdte = hoog - laag or 1.0

    def y(p):
        return pl_y1 - (p - laag) / spanwijdte * pl_h

    n = len(candles)
    slot = pl_b / n
    body = max(1.4, slot * 0.62)

    def x(i):
        return pl_x0 + slot * (i + 0.5)

    delen = []
    delen.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {breedte} {hoogte}" '
        f'width="{breedte}" height="{hoogte}" font-family="Segoe UI, Arial, sans-serif">')
    delen.append(f'<rect width="{breedte}" height="{hoogte}" fill="{BG}"/>')

    # ---- prijs-gridlijnen + labels rechts
    for k in range(5):
        p = laag + spanwijdte * k / 4
        yy = y(p)
        delen.append(f'<line x1="{pl_x0}" y1="{yy:.1f}" x2="{pl_x1}" y2="{yy:.1f}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        delen.append(f'<text x="{pl_x1 + 6}" y="{yy + 4:.1f}" font-size="12" '
                     f'fill="{AS}">{_fmt(p)}</text>')

    # ---- candles
    for i, (o, h, l, c) in enumerate(candles):
        kleur = UP if c >= o else DOWN
        cx = x(i)
        # wick
        delen.append(f'<line x1="{cx:.1f}" y1="{y(h):.1f}" x2="{cx:.1f}" y2="{y(l):.1f}" '
                     f'stroke="{kleur}" stroke-width="1"/>')
        # body
        boven, onder = y(max(o, c)), y(min(o, c))
        hh = max(1.0, onder - boven)
        delen.append(f'<rect x="{cx - body / 2:.1f}" y="{boven:.1f}" width="{body:.1f}" '
                     f'height="{hh:.1f}" fill="{kleur}"/>')

    # ---- entry/SL/TP-lijnen
    def lijn(p, kleur, label, streep=False):
        if p is None:
            return
        yy = y(p)
        dash = ' stroke-dasharray="6 4"' if streep else ""
        delen.append(f'<line x1="{pl_x0}" y1="{yy:.1f}" x2="{pl_x1}" y2="{yy:.1f}" '
                     f'stroke="{kleur}" stroke-width="1.5"{dash}/>')
        delen.append(f'<rect x="{pl_x0}" y="{yy - 9:.1f}" width="86" height="18" '
                     f'fill="{kleur}"/>')
        delen.append(f'<text x="{pl_x0 + 5}" y="{yy + 4:.1f}" font-size="11" '
                     f'fill="#fff" font-weight="600">{label} {_fmt(p)}</text>')

    # ---- positievak (v2.1): risico rood, doel groen, van instap tot uitstap
    if entry is not None and zone_van is not None and 0 <= zone_van < n:
        z1 = zone_tot if (zone_tot is not None and zone_van <= zone_tot < n) else n - 1
        zx0 = x(zone_van) - slot / 2
        zx1 = x(z1) + slot / 2
        if zx1 - zx0 < 24:
            zx1 = zx0 + 24
        for niveau, kleur in ((sl, SL_KLEUR), (tp, TP_KLEUR)):
            if niveau is None:
                continue
            ya, yb = sorted((y(entry), y(niveau)))
            delen.append(f'<rect x="{zx0:.1f}" y="{ya:.1f}" width="{zx1 - zx0:.1f}" '
                         f'height="{max(1.0, yb - ya):.1f}" fill="{kleur}" opacity="0.13"/>')
        if exit_prijs is not None:
            delen.append(f'<line x1="{zx0:.1f}" y1="{y(exit_prijs):.1f}" x2="{zx1:.1f}" '
                         f'y2="{y(exit_prijs):.1f}" stroke="#555" stroke-width="1.2" '
                         f'stroke-dasharray="2 3"/>')
            delen.append(f'<line x1="{x(zone_van):.1f}" y1="{y(entry):.1f}" x2="{x(z1):.1f}" '
                         f'y2="{y(exit_prijs):.1f}" stroke="#555" stroke-width="1" opacity="0.55"/>')
    if info:
        delen.append(f'<rect x="{pl_x1 - 250}" y="{pl_y0 + 4}" width="246" height="22" rx="3" '
                     f'fill="#ffffff" stroke="{GRID}"/>')
        delen.append(f'<text x="{pl_x1 - 10}" y="{pl_y0 + 19}" font-size="12" font-weight="600" '
                     f'fill="#333" text-anchor="end">{escape(info)}</text>')
    if entry is not None and sl is None:
        delen.append(f'<text x="{pl_x0 + 4}" y="{pl_y0 + 18}" font-size="12" fill="{SL_KLEUR}" '
                     f'font-weight="600">SL/TP onbekend — antwoord in Telegram: sl 1234.5 tp 1230.0</text>')

    lijn(tp, TP_KLEUR, "TP", streep=True)
    lijn(entry, ENTRY_KLEUR, "entry")
    lijn(sl, SL_KLEUR, "SL", streep=True)

    # ---- markeer de entry-candle (de laatste; daar vuurt het signaal)
    if markeer_laatste:
        ex = x(n - 1)
        delen.append(f'<polygon points="{ex - 5:.1f},{pl_y0 + 2} {ex + 5:.1f},{pl_y0 + 2} '
                     f'{ex:.1f},{pl_y0 + 11}" fill="{AS}"/>')

    # ---- verticale markers (entry-/exit-moment uit MetaTrader)
    for idx, kleur, tekst in (markers or []):
        if idx is None or not (0 <= idx < n):
            continue
        mx = x(idx)
        delen.append(f'<line x1="{mx:.1f}" y1="{pl_y0}" x2="{mx:.1f}" y2="{pl_y1}" '
                     f'stroke="{kleur}" stroke-width="1.2" stroke-dasharray="3 3" opacity="0.8"/>')
        delen.append(f'<text x="{mx + 4:.1f}" y="{pl_y1 - 6}" font-size="11" '
                     f'fill="{kleur}" font-weight="600">{escape(tekst)}</text>')
        if tekst.startswith("exit") and exit_prijs is not None:
            delen.append(f'<circle cx="{mx:.1f}" cy="{y(exit_prijs):.1f}" r="4" '
                         f'fill="#fff" stroke="{kleur}" stroke-width="2"/>')

    # ---- kop
    richting_txt = {"long": "▲ LONG", "short": "▼ SHORT"}.get(richting, "")
    tier_txt = {"entry": "ENTRY", "rijp": "RIJP", "opgelet": "OPGELET"}.get(tier, tier.upper())
    kop = " · ".join(x for x in [symbool, tier_txt, richting_txt, kop_extra] if x)
    delen.append(f'<text x="{pl_x0}" y="26" font-size="15" font-weight="700" '
                 f'fill="#111">{escape(kop)}</text>')
    if rr is not None:
        delen.append(f'<text x="{pl_x1}" y="26" font-size="13" fill="{AS}" '
                     f'text-anchor="end">RR {_fmt(rr, 1)}</text>')

    delen.append('</svg>')
    return "".join(delen)
