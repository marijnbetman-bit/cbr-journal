# -*- coding: utf-8 -*-
"""
pdf_rapport.py -- kerncijfers van een gekozen periode als 1-pagina PDF.

Puur fpdf2, geen systeemafhankelijkheden. De mini-saldocurve wordt met
lijnstukken getekend, dus geen matplotlib/Pillow nodig. Kerncijfers komen uit
prestaties.analyse + edge.analyse; alles automatisch uit de MT5-data.
"""

from datetime import date

# fpdf2. Kern-fonts zijn latin-1, dus we schrijven "EUR" i.p.v. het euroteken.
from fpdf import FPDF

INK = (24, 28, 37)
MUTED = (134, 143, 159)
GREEN = (6, 121, 95)
RED = (201, 37, 47)
LINE = (221, 215, 205)


def _eur(n):
    if n is None:
        return "-"
    return f"EUR {n:+.2f}".replace(".", ",")


def _eur_kaal(n):
    if n is None:
        return "-"
    return f"EUR {n:.2f}".replace(".", ",")


def _pct(n):
    if n is None:
        return "-"
    return f"{n:+.1f}%".replace(".", ",")


def _kleur(pdf, waarde):
    pdf.set_text_color(*(GREEN if (waarde or 0) > 0 else RED if (waarde or 0) < 0 else INK))


def bouw_pdf(periode_label, bron, kern, edge, equity, per_uur_beste, r_liggen):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    W = 210
    marge = 16

    # ---- Kop ----
    pdf.set_xy(marge, 16)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*INK)
    pdf.cell(0, 9, "CBR Trading Journal", ln=1)
    pdf.set_x(marge)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, f"Kerncijfers  -  {periode_label}  -  bron: {bron}", ln=1)
    pdf.set_x(marge)
    pdf.cell(0, 6, f"Gegenereerd op {date.today().strftime('%d-%m-%Y')}", ln=1)

    # ---- Grote cijfers (tegels) ----
    tegels = [
        ("Saldo", _eur_kaal(kern.get("saldo")), None),
        ("Netto P/L", _eur(kern.get("netto_eur")), kern.get("netto_eur")),
        ("Rendement", _pct(kern.get("groei_pct")), kern.get("groei_pct")),
        ("Winrate", f"{kern.get('winrate', 0)}%", None),
        ("Expectancy", f"{edge.get('expectancy_r', 0):.2f}R", edge.get("expectancy_r")),
        ("Totaal R", f"{kern.get('netto_r', 0):+.2f}R", kern.get("netto_r")),
        ("Trades", str(kern.get("n", 0)), None),
        ("Beste uur", per_uur_beste.get("naam") if per_uur_beste else "-", None),
    ]
    kol = 4
    tw = (W - 2 * marge) / kol
    th = 22
    y0 = 42
    for i, (label, val, kl) in enumerate(tegels):
        r, c = divmod(i, kol)
        x = marge + c * tw
        y = y0 + r * (th + 4)
        pdf.set_draw_color(*LINE)
        pdf.rect(x, y, tw - 3, th)
        pdf.set_xy(x + 3, y + 3)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*MUTED)
        pdf.cell(tw - 6, 4, label.upper(), ln=2)
        pdf.set_x(x + 3)
        pdf.set_font("Helvetica", "B", 15)
        if kl is None:
            pdf.set_text_color(*INK)
        else:
            _kleur(pdf, kl)
        pdf.cell(tw - 6, 9, val)

    # ---- Foutmarges-strook ----
    dd = edge.get("drawdown", {}) or {}
    y = y0 + 2 * (th + 4) + 6
    pdf.set_xy(marge, y)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*INK)
    pdf.cell(0, 7, "Foutmarges", ln=1)
    regels = [
        ("Profit factor", f"{edge.get('profit_factor', 0):.2f}" if edge.get("profit_factor") is not None else "-"),
        ("Gem. winst", f"{edge.get('gem_winst_r', 0):+.2f}R"),
        ("Gem. verlies", f"{edge.get('gem_verlies_r', 0):.2f}R"),
        ("Max drawdown", _eur(-abs(dd.get("max_eur", 0))) if dd.get("max_eur") else "-"),
        ("R laten liggen (winnaars)", f"{r_liggen.get('gem_winnaars_r', 0):.2f}R" if r_liggen.get("n_winnaars") else "-"),
    ]
    pdf.set_font("Helvetica", "", 10)
    for label, val in regels:
        pdf.set_x(marge)
        pdf.set_text_color(*MUTED)
        pdf.cell(70, 6, label)
        pdf.set_text_color(*INK)
        pdf.cell(0, 6, val, ln=1)

    # ---- Mini-saldocurve ----
    saldos = [p.get("saldo") for p in (equity or []) if p.get("saldo") is not None]
    if len(saldos) >= 2:
        cx, cy = marge, y + 44
        cw, ch = W - 2 * marge, 46
        pdf.set_xy(cx, cy - 7)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*INK)
        pdf.cell(0, 7, "Saldoverloop", ln=1)
        lo, hi = min(saldos), max(saldos)
        spanne = (hi - lo) or 1.0
        pdf.set_draw_color(*LINE)
        pdf.rect(cx, cy, cw, ch)
        n = len(saldos)
        stijgt = saldos[-1] >= saldos[0]
        pdf.set_draw_color(*(GREEN if stijgt else RED))
        pdf.set_line_width(0.5)
        for i in range(1, n):
            x1 = cx + cw * (i - 1) / (n - 1)
            x2 = cx + cw * i / (n - 1)
            y1 = cy + ch - ch * (saldos[i - 1] - lo) / spanne
            y2 = cy + ch - ch * (saldos[i] - lo) / spanne
            pdf.line(x1, y1, x2, y2)
        pdf.set_line_width(0.2)

    # ---- Voet ----
    pdf.set_xy(marge, 285)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, "Automatisch gegenereerd uit MetaTrader-data  -  CBR Journal")

    out = pdf.output()
    return bytes(out)
