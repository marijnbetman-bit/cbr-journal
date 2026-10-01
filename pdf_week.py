# -*- coding: utf-8 -*-
"""
pdf_week.py -- het weekrapport als PDF (v2.1, 29 sep 2026).

Pagina 1: kerncijfers met verschil t.o.v. vorige week, focus voor volgende
week, wat ging goed, je progressie over 12 weken en de dagen.
Daarna: elke trade met zijn chart, checklist-uitkomst, emotie en les.
Laatste blok: je lessen en de automatische fouten van de week.

fpdf2, geen extra pakketten. Lettertype: Segoe UI (Windows) of DejaVu (Linux),
anders Helvetica met eenvoudige tekens.
"""

import os
from datetime import date

from fpdf import FPDF

INK = (24, 28, 37)
DIM = (74, 82, 99)
MUTED = (134, 143, 159)
GREEN = (6, 121, 95)
RED = (201, 37, 47)
PLUM = (109, 77, 234)
LINE = (221, 215, 205)
BG = (247, 244, 239)
C_GREEN = (8, 153, 129)
C_RED = (242, 54, 69)
C_GRIJS = (205, 200, 192)

EMOTIE = {"rustig": "rustig", "gefocust": "gefocust", "twijfel": "twijfel", "gehaast": "gehaast",
          "fomo": "FOMO", "revenge": "revenge", "moe": "moe"}

FONTS = [
    (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


class PDF(FPDF):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.unicode = False
        for gewoon, vet in FONTS:
            if os.path.exists(gewoon) and os.path.exists(vet):
                try:
                    self.add_font("J", "", gewoon)
                    self.add_font("J", "B", vet)
                    self.unicode = True
                    break
                except Exception:
                    pass
        self.fam = "J" if self.unicode else "Helvetica"
        self.voet = ""

    def t(self, s):
        s = "" if s is None else str(s)
        if self.unicode:
            return s
        s = s.replace("€", "EUR").replace("–", "-").replace("—", "-").replace("·", "-").replace("×", "x")
        return s.encode("latin-1", "replace").decode("latin-1")

    def f(self, stijl="", grootte=10, kleur=INK):
        self.set_font(self.fam, stijl, grootte)
        self.set_text_color(*kleur)

    def footer(self):
        self.set_y(-12)
        self.f("", 7.5, MUTED)
        self.cell(0, 5, self.t(f"{self.voet}   ·   pagina {self.page_no()}"), align="C")


def eur(v, teken=True):
    if v is None:
        return "–"
    s = f"{abs(v):.2f}".replace(".", ",")
    return ("+" if v >= 0 else "−") + "€ " + s if teken else "€ " + s


def r2(v):
    return "–" if v is None else (f"{v:+.2f}R").replace(".", ",")


def _delta_tekst(k, d):
    if not d:
        return "", MUTED
    x = d["delta"]
    if k in ("netto_eur",):
        s = eur(x)
    elif k in ("netto_r", "expectancy_r"):
        s = r2(x)
    elif k == "uitvoering":
        s = f"{x:+.1f}".replace(".", ",")
    else:
        s = f"{x:+g}" + ("%" if k.endswith("pct") or k in ("winrate",) else "")
        s = s.replace(".", ",")
    kleur = GREEN if d.get("beter") else RED if d.get("beter") is False else MUTED
    return f"{s} vs vorige week", kleur


def tegels(pdf, m, d, x0, y0, breedte):
    items = [
        ("Netto", eur(m["netto_eur"]), m["netto_eur"], "netto_eur"),
        ("Resultaat", r2(m["netto_r"]), m["netto_r"], "netto_r"),
        ("Winrate", f"{m['winrate']}%" if m["winrate"] is not None else "–", None, "winrate"),
        ("Expectancy", r2(m["expectancy_r"]), m["expectancy_r"], "expectancy_r"),
        ("Proces-score", f"{m['proces_score']}%" if m["proces_score"] is not None else "–", None, "proces_score"),
        ("Regels gevolgd", f"{m['schoon_pct']}%" if m["schoon_pct"] is not None else "–", None, "schoon_pct"),
        ("Goede staat vooraf", f"{m['goede_staat_pct']}%" if m["goede_staat_pct"] is not None else "–", None, "goede_staat_pct"),
        ("Uitvoering", f"{m['uitvoering']}/5".replace(".", ",") if m["uitvoering"] else "–", None, "uitvoering"),
    ]
    kol, tw, th = 4, breedte / 4, 21
    for i, (label, val, teken, key) in enumerate(items):
        r, c = divmod(i, kol)
        x, y = x0 + c * tw, y0 + r * (th + 3)
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(*LINE)
        pdf.rect(x, y, tw - 3, th, style="DF")
        pdf.set_xy(x + 3, y + 2.5)
        pdf.f("", 7, MUTED)
        pdf.cell(tw - 6, 3.5, pdf.t(label.upper()))
        pdf.set_xy(x + 3, y + 6.5)
        kleur = INK if teken is None else (GREEN if teken > 0 else RED if teken < 0 else INK)
        pdf.f("B", 14, kleur)
        pdf.cell(tw - 6, 7, pdf.t(val))
        tekst, kl = _delta_tekst(key, d.get(key))
        pdf.set_xy(x + 3, y + 14.5)
        pdf.f("", 7, kl)
        pdf.cell(tw - 6, 4, pdf.t(tekst))
    return y0 + 2 * (th + 3)


def staaf(pdf, x, y, w, h, titel, weken, key, huidig, eenheid="", nul_midden=False):
    pdf.set_xy(x, y)
    pdf.f("B", 8.5, INK)
    pdf.cell(w, 4, pdf.t(titel))
    y += 6
    h -= 6
    waarden = [wk.get(key) for wk in weken]
    geldig = [v for v in waarden if v is not None]
    pdf.set_draw_color(*LINE)
    if not geldig:
        pdf.set_xy(x, y + h / 2 - 2)
        pdf.f("", 7.5, MUTED)
        pdf.cell(w, 4, pdf.t("nog geen data — log je trades"), align="C")
        return
    hoog = max(max(geldig), 0)
    laag = min(min(geldig), 0)
    if not nul_midden:
        laag = 0
        hoog = max(hoog, 1)
    span = (hoog - laag) or 1
    nul_y = y + h * hoog / span
    pdf.line(x, nul_y, x + w, nul_y)
    n = len(weken)
    slot = w / n
    for i, (wk, v) in enumerate(zip(weken, waarden)):
        if v is None:
            continue
        bh = abs(v) / span * h
        bx = x + i * slot + slot * 0.18
        by = nul_y - bh if v >= 0 else nul_y
        is_nu = wk["maandag"] == huidig
        if nul_midden:
            kleur = (C_GREEN if v >= 0 else C_RED) if is_nu else ((170, 214, 205) if v >= 0 else (245, 178, 183))
        else:
            kleur = PLUM if is_nu else (196, 186, 240)
        pdf.set_fill_color(*kleur)
        pdf.rect(bx, by, slot * 0.64, max(0.4, bh), style="F")
        if is_nu:
            pdf.f("B", 6.5, INK)
            lbl = (f"{v:+.1f}" if nul_midden else f"{v:g}") + eenheid
            pdf.set_xy(bx - 3, (by - 4) if v >= 0 else (by + bh + 0.5))
            pdf.cell(slot * 0.64 + 6, 3.5, pdf.t(lbl.replace(".", ",")), align="C")
    pdf.f("", 6, MUTED)
    for i, wk in enumerate(weken):
        if i % 2 == (n - 1) % 2:
            pdf.set_xy(x + i * slot, y + h + 1)
            pdf.cell(slot, 3, str(wk["week"]), align="C")


def kop(pdf, data, marge, W):
    pdf.set_fill_color(*PLUM)
    pdf.rect(0, 0, W, 3, style="F")
    pdf.set_xy(marge, 11)
    pdf.f("", 9, PLUM)
    pdf.cell(0, 5, pdf.t("CBR TRADING JOURNAL  ·  WEEKRAPPORT"))
    pdf.set_xy(marge, 17)
    pdf.f("B", 22, INK)
    pdf.cell(0, 10, pdf.t(f"Week {data['week']}  ·  {data['bereik']} {data['jaar']}"))
    pdf.set_xy(marge, 28)
    m = data["meting"]
    pdf.f("", 9.5, DIM)
    pdf.cell(0, 5, pdf.t(f"{m['n']} trades over {m['handelsdagen']} handelsdagen  ·  "
                         f"{m['gelogd_pct'] if m['gelogd_pct'] is not None else 0}% gelogd  ·  "
                         f"gemaakt op {date.today().strftime('%d-%m-%Y')}"))


def blok(pdf, x, y, w, titel, regels, kleur=PLUM):
    pdf.set_draw_color(*kleur)
    pdf.set_line_width(0.8)
    start = y
    pdf.set_xy(x + 4, y + 2)
    pdf.f("B", 10, kleur)
    pdf.cell(w - 8, 5, pdf.t(titel))
    y += 8
    for i, (stijl, tekst) in enumerate(regels):
        pdf.set_xy(x + 4, y)
        pdf.f(stijl, 9 if stijl == "B" else 8.5, INK if stijl == "B" else DIM)
        pdf.multi_cell(w - 8, 4.3, pdf.t(tekst), align="L")
        y = pdf.get_y() + 1
    pdf.line(x, start, x, y)
    pdf.set_line_width(0.2)
    return y + 2


def svg_bron(pad):
    """SVG klaarmaken voor fpdf2: die tekent SVG-tekst met de kernfonts, dus
    alleen latin-1 tekens."""
    import io
    with open(pad, encoding="utf-8") as f:
        s = f.read()
    for a, b in {"▼ ": "", "▲ ": "", "▼": "", "▲": "", "·": "-", "—": "-", "–": "-",
                 "€": "EUR", "↔": "<>", "≥": ">=", "≤": "<="}.items():
        s = s.replace(a, b)
    s = s.encode("latin-1", "replace").decode("latin-1")
    return io.BytesIO(s.encode("utf-8"))


def trade_kaart(pdf, t, x, y, w, basis):
    netto = t["netto"]
    pdf.set_xy(x, y)
    pdf.f("B", 10.5, INK)
    richting = "SHORT" if t["richting"] == "short" else "LONG"
    pdf.cell(w * 0.72, 6, pdf.t(f"#{t['id']}  {richting}  ·  {t['datum'][8:]}-{t['datum'][5:7]} "
                               f"{t['tijd'] or ''}–{t['tijd_exit'] or ''}  ·  {t['sessie'] or ''}"))
    pdf.f("B", 10.5, GREEN if netto > 0 else RED if netto < 0 else INK)
    pdf.cell(w * 0.28, 6, pdf.t(f"{eur(netto)}   {r2(t['r'])}"), align="R")
    y += 7
    cw, ch = w * 0.6, 0
    if t.get("chart"):
        pad = os.path.join(basis, t["chart"].lstrip("/").split("?")[0])
        if os.path.exists(pad):
            try:
                pdf.image(svg_bron(pad), x=x, y=y, w=cw)
                ch = cw * 540 / 960
            except Exception:
                ch = 0
    if ch:
        x2, w2 = x + cw + 5, w - cw - 5
    else:
        x2, w2 = x, w
    yy = y

    def regel(label, waarde, kleur=INK, stijl=""):
        nonlocal yy
        pdf.set_xy(x2, yy)
        pdf.f("", 7, MUTED)
        pdf.cell(w2, 3.5, pdf.t(label.upper()))
        pdf.set_xy(x2, yy + 3.6)
        pdf.f(stijl or "B", 9.5, kleur)
        pdf.multi_cell(w2, 4.3, pdf.t(waarde), align="L")
        yy = pdf.get_y() + 1.8

    grade = t.get("grade") or "?"
    if t.get("beoordeeld") == 0:
        regel("status", "nog niet gelogd", RED)
    regel("grade · proces", f"{grade}" + (f"  ·  {t['proces_score']}%" if t.get("proces_score") is not None else ""),
          GREEN if grade == "A" else INK)
    if t.get("schoon") is not None:
        regel("regels", "gevolgd" if t["schoon"] == 1 else "gebroken", GREEN if t["schoon"] == 1 else RED)
    if t.get("emotie") or t.get("uitvoering"):
        regel("staat · uitvoering", f"{EMOTIE.get(t.get('emotie'), t.get('emotie') or '–')}"
              + (f"  ·  {t['uitvoering']}/5" if t.get("uitvoering") else ""))
    if t.get("exit_reden"):
        regel("exit", t["exit_reden"], DIM, "")
    if not t.get("sl_bekend"):
        regel("let op", "SL/TP niet bekend", RED, "")
    if t.get("fouten"):
        regel("fouten", ", ".join(t["fouten"]), RED, "")
    if t.get("les"):
        regel("les", t["les"], PLUM)
    return max(y + ch, yy) + 6


def bouw(data, basis="."):
    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.voet = f"CBR Journal  ·  weekrapport week {data['week']} {data['jaar']}"
    pdf.set_auto_page_break(True, margin=16)
    W, marge = 210, 14
    bw = W - 2 * marge
    m, d = data["meting"], data["deltas"]

    # ---------------- pagina 1
    pdf.add_page()
    kop(pdf, data, marge, W)
    y = tegels(pdf, m, d, marge, 38, bw + 3) + 4

    f = data["focus"]
    links = blok(pdf, marge, y, bw / 2 - 3, "Focus voor volgende week",
                 [("B", f["titel"]), ("", f["tekst"])] + ([("", f["bron"])] if f.get("bron") else []))
    sterk = data.get("sterk") or []
    rechts = blok(pdf, marge + bw / 2 + 3, y, bw / 2 - 3, "Wat ging goed",
                  [("", "• " + s) for s in sterk] or [("", "Nog weinig om te vergelijken — log elke trade.")],
                  kleur=GREEN)
    y = max(links, rechts) + 3

    pdf.set_xy(marge, y)
    pdf.f("B", 11, INK)
    pdf.cell(0, 6, pdf.t("Progressie — laatste 12 weken"))
    y += 8
    weken = data.get("progressie") or []
    gw, gh = bw / 2 - 4, 34
    staaf(pdf, marge, y, gw, gh, "Resultaat per week (R)", weken, "netto_r", data["maandag"], "R", nul_midden=True)
    staaf(pdf, marge + bw / 2 + 4, y, gw, gh, "Proces-score (%)", weken, "proces_score", data["maandag"], "%")
    y += gh + 8
    staaf(pdf, marge, y, gw, gh, "Winrate (%)", weken, "winrate", data["maandag"], "%")
    staaf(pdf, marge + bw / 2 + 4, y, gw, gh, "Regels gevolgd (%)", weken, "schoon_pct", data["maandag"], "%")
    y += gh + 10

    dagen = data.get("dagen") or []
    if dagen and y < 250:
        pdf.set_xy(marge, y)
        pdf.f("B", 11, INK)
        pdf.cell(0, 6, pdf.t("Per dag"))
        y += 7
        cols = [("Dag", 40), ("Trades", 25), ("Winrate", 25), ("R", 30), ("Netto", 35)]
        pdf.set_xy(marge, y)
        pdf.f("", 7.5, MUTED)
        for naam, bw_ in cols:
            pdf.cell(bw_, 5, pdf.t(naam.upper()))
        y += 5
        for dg in dagen:
            pdf.set_draw_color(*LINE)
            pdf.line(marge, y, marge + 155, y)
            pdf.set_xy(marge, y + 0.5)
            pdf.f("", 9, INK)
            pdf.cell(40, 5.5, pdf.t(f"{dg['weekdag']} {dg['datum'][8:]}-{dg['datum'][5:7]}"))
            pdf.cell(25, 5.5, str(dg["n"]))
            pdf.cell(25, 5.5, f"{dg['winrate']}%")
            pdf.f("", 9, GREEN if dg["netto_r"] > 0 else RED if dg["netto_r"] < 0 else INK)
            pdf.cell(30, 5.5, pdf.t(r2(dg["netto_r"])))
            pdf.cell(35, 5.5, pdf.t(eur(dg["netto_eur"])))
            y += 6

    # ---------------- trades
    trades = data.get("trades") or []
    if trades:
        pdf.add_page()
        pdf.set_xy(marge, 14)
        pdf.f("B", 15, INK)
        pdf.cell(0, 8, pdf.t(f"De trades van week {data['week']}"))
        y = 26
        for t in trades:
            nodig = 7 + (bw * 0.6 * 540 / 960 if t.get("chart") else 30) + 8
            if y + nodig > 282:
                pdf.add_page()
                y = 14
            y = trade_kaart(pdf, t, marge, y, bw, basis)
            pdf.set_draw_color(*LINE)
            pdf.line(marge, y - 3, marge + bw, y - 3)

    # ---------------- lessen + fouten
    lessen = data.get("lessen") or []
    auto = data.get("auto_fouten") or []
    if lessen or auto:
        pdf.add_page()
        y = 14
        if lessen:
            y = blok(pdf, marge, y, bw, "Je lessen van deze week",
                     [("", f"#{l['id']} ({l['datum'][8:]}-{l['datum'][5:7]} {l['tijd'] or ''}): {l['les']}") for l in lessen]) + 4
        if auto:
            blok(pdf, marge, y, bw, "Automatisch gevonden (uit MT5-feiten)",
                 [("", f"{a['label']} — {a['aantal']}× ({a['pct']}%). {a.get('correctie') or ''}") for a in auto],
                 kleur=RED)
    return bytes(pdf.output())
