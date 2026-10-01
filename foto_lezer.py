# -*- coding: utf-8 -*-
"""
foto_lezer.py -- leest de trade-niveaus uit een TradingView-screenshot.

Stuurt de afbeelding naar de Claude API (vision) en vraagt om entry, SL, TP en
richting als strikte JSON. De harde regel: NOOIT gokken. Een niveau dat niet
met zekerheid af te lezen is wordt None, geen schatting.

Ontbreekt na de eerste foto de SL of de TP, dan hoort de webpagina om een
tweede screenshot te vragen waarin de gebruiker de positie op TradingView
opent (de position-tool toont de exacte niveaus als tekst). Roep dan opnieuw
lees_niveaus() aan met is_positie_tool=True en voeg het resultaat samen met
combineer().

Geen netwerk- of API-code buiten lees_niveaus(): de client wordt ingespoten,
zodat de tests draaien zonder echte API-sleutel.
"""

import base64
import json
import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# Haiku is ruim voldoende voor het aflezen van cijfers van een chart en veruit
# het goedkoopst. Bij twijfel kun je hier tijdelijk een sterker model zetten.
MODEL = "claude-haiku-4-5"

# Goud (XAUUSD) staat rond de 4300. Alles ver buiten een plausibele band is
# vrijwel zeker een verkeerd gelezen getal (bijv. een as-label meegepakt).
PRIJS_MIN = 1000.0
PRIJS_MAX = 9000.0

_SYS = (
    "Je bent een precieze uitlezer van TradingView-screenshots van goud "
    "(XAUUSD, prijs rond de 4300). Je leest cijfers af, je interpreteert geen "
    "trade-idee. Je GOKT NOOIT: een niveau dat je niet met zekerheid kunt "
    "aflezen geef je als null."
)

_PROMPT_CHART = (
    "Dit is een chart-screenshot. Er kunnen horizontale lijnen op staan met "
    "een prijslabel aan de rechter-as (entry, stop loss, take profit), of een "
    "long/short-positievak. Lees af wat er ZICHTBAAR en LEESBAAR is.\n\n"
    "Geef ALLEEN een JSON-object terug, zonder tekst eromheen, met deze sleutels:\n"
    '  "richting": "long" | "short" | null   (long = koop/buy, short = verkoop/sell)\n'
    '  "entry": getal | null                 (de instapprijs)\n'
    '  "sl": getal | null                    (de stop loss)\n'
    '  "tp": getal | null                    (de take profit / target)\n'
    '  "zeker": [lijst van veldnamen die je met zekerheid kon aflezen]\n'
    '  "twijfel": [lijst van veldnamen waar je twijfelde]\n\n'
    "Regels: gebruik een punt als decimaalteken (4330.23). Neem NOOIT een "
    "as-schaallabel of het huidige-prijslabel voor een van de niveaus. Kun je "
    "een niveau niet zeker plaatsen, zet het op null en noem het niet in "
    '"zeker".'
)

_PROMPT_POSITIE = (
    "Dit is een screenshot waarin de gebruiker de POSITIE op TradingView heeft "
    "geopend (de position-tool of het order-paneel), dus de exacte niveaus "
    "staan als tekst genoemd: entry/avg, stop loss, take profit, en de "
    "richting (long/short of buy/sell).\n\n"
    "Geef ALLEEN een JSON-object terug met dezelfde sleutels als altijd: "
    '"richting", "entry", "sl", "tp", "zeker", "twijfel". Lees de genoemde '
    "getallen letterlijk over. Gebruik een punt als decimaalteken. Wat er niet "
    "staat is null."
)


@dataclass
class Uitlezing:
    """Wat er uit een enkele foto kwam."""
    richting: Optional[str] = None
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    zeker: List[str] = field(default_factory=list)
    twijfel: List[str] = field(default_factory=list)
    ruw: str = ""          # de ruwe modeltekst, voor als het parsen misging
    fout: str = ""         # gevuld als er iets misging

    @property
    def compleet(self) -> bool:
        """Alle drie de prijsniveaus gelezen."""
        return None not in (self.entry, self.sl, self.tp)

    @property
    def ontbreekt(self) -> List[str]:
        return [naam for naam, waarde in
                (("entry", self.entry), ("sl", self.sl), ("tp", self.tp))
                if waarde is None]

    @property
    def vraag_tweede(self) -> bool:
        """
        Vraag een tweede screenshot als SL of TP ontbreekt. De entry mag uit de
        chart komen, maar zonder SL of TP kun je geen RR en geen grade rekenen,
        dus dan is de position-tool-view nodig.
        """
        return self.sl is None or self.tp is None

    def dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------- getal parsen

def naar_getal(x) -> Optional[float]:
    """
    Maakt een prijs los van hoe het model of de gebruiker hem schreef:
    "4.330,23", "4,330.23", "4330.23", "4330" -> 4330.xx. Onplausibele of
    onleesbare waarden worden None, zodat een foutgelezen as-label niet als
    niveau doorschiet.
    """
    if x is None:
        return None
    if isinstance(x, (int, float)):
        w = float(x)
        return w if PRIJS_MIN <= w <= PRIJS_MAX else None

    s = str(x).strip().replace(" ", "")
    if not s:
        return None
    s = re.sub(r"[^0-9.,]", "", s)
    if not s:
        return None

    if "," in s and "." in s:
        # de laatste van de twee is het decimaalteken; de andere is duizendtal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # alleen komma: 2 decimalen achter -> decimaal, anders duizendtal
        heel, _, staart = s.rpartition(",")
        s = (heel.replace(",", "") + "." + staart) if len(staart) == 2 \
            else s.replace(",", "")
    # alleen punt of niets: laat staan
    try:
        w = float(s)
    except ValueError:
        return None
    return w if PRIJS_MIN <= w <= PRIJS_MAX else None


def _pak_json(tekst: str) -> Optional[dict]:
    """Vist het eerste JSON-object uit de modeltekst (soms staat er ```json omheen)."""
    m = re.search(r"\{.*\}", tekst, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _richting(x) -> Optional[str]:
    if not x:
        return None
    s = str(x).lower()
    if any(w in s for w in ("long", "buy", "koop")):
        return "long"
    if any(w in s for w in ("short", "sell", "verkoop")):
        return "short"
    return None


def _uit_dict(d: dict, ruw: str) -> Uitlezing:
    zeker = d.get("zeker") or []
    # alleen velden die het model in "zeker" zette EN die plausibel parsen
    entry = naar_getal(d.get("entry"))
    sl = naar_getal(d.get("sl"))
    tp = naar_getal(d.get("tp"))
    zeker = [v for v in ("entry", "sl", "tp", "richting")
             if v in zeker and (v == "richting" or locals().get(v) is not None)]
    return Uitlezing(
        richting=_richting(d.get("richting")),
        entry=entry, sl=sl, tp=tp,
        zeker=zeker,
        twijfel=list(d.get("twijfel") or []),
        ruw=ruw,
    )


# --------------------------------------------------------------- de API-aanroep

def _tekst_uit_antwoord(antwoord) -> str:
    """Haalt de platte tekst uit een Anthropic messages-antwoord."""
    delen = getattr(antwoord, "content", None) or []
    stukjes = []
    for blok in delen:
        t = getattr(blok, "text", None)
        if t is None and isinstance(blok, dict):
            t = blok.get("text")
        if t:
            stukjes.append(t)
    return "\n".join(stukjes)


def lees_niveaus(afbeelding_bytes: bytes, client, *,
                 media_type: str = "image/png",
                 model: str = MODEL,
                 is_positie_tool: bool = False,
                 max_tokens: int = 400) -> Uitlezing:
    """
    Leest de niveaus uit een screenshot.

    client        -- een object met .messages.create(...), zoals anthropic.Anthropic().
                     Ingespoten zodat de tests een stub kunnen gebruiken.
    is_positie_tool -- True voor de tweede screenshot (position-tool open).
    """
    b64 = base64.standard_b64encode(afbeelding_bytes).decode("ascii")
    prompt = _PROMPT_POSITIE if is_positie_tool else _PROMPT_CHART
    try:
        antwoord = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=_SYS,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
    except Exception as e:  # netwerk, sleutel, rate limit -- de pagina vangt dit op
        return Uitlezing(fout=f"API-aanroep mislukt: {e}")

    ruw = _tekst_uit_antwoord(antwoord)
    d = _pak_json(ruw)
    if d is None:
        return Uitlezing(ruw=ruw, fout="geen leesbare JSON in het antwoord")
    return _uit_dict(d, ruw)


def combineer(eerste: Uitlezing, tweede: Uitlezing) -> Uitlezing:
    """
    Voegt de tweede (position-tool) uitlezing samen met de eerste. De tweede
    wint per veld, want daar staan de niveaus als exacte tekst; de eerste vult
    aan wat de tweede niet had.
    """
    def kies(veld):
        return getattr(tweede, veld) if getattr(tweede, veld) is not None \
            else getattr(eerste, veld)

    samen = Uitlezing(
        richting=kies("richting"),
        entry=kies("entry"), sl=kies("sl"), tp=kies("tp"),
        ruw=(eerste.ruw + "\n---\n" + tweede.ruw).strip(),
    )
    samen.zeker = sorted(set(eerste.zeker) | set(tweede.zeker))
    samen.twijfel = [v for v in ("entry", "sl", "tp") if v in samen.ontbreekt]
    return samen
