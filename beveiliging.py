# -*- coding: utf-8 -*-
"""
beveiliging.py -- eenvoudige wachtwoordpoort voor de journal (blok 7, VPS).

Waarom dit bestaat: de journal draait 24/7 op een server met een publiek
IP-adres. Zonder poort hier zou letterlijk iedereen die dat adres scant je
trades kunnen zien -- en zelfs nieuwe kunnen aanmaken. Dit is geen volwaardig
inlogsysteem, maar een korte, betrouwbare drempel: de browser vraagt om een
wachtwoord (HTTP Basic Auth) voordat er ook maar iets van de journal getoond
wordt.

Alleen actief als de omgevingsvariabele JOURNAL_WACHTWOORD gezet is. Geen
variabele -> geen poort. Zo blijft de journal op je laptop (lokaal netwerk)
gewoon open, en is hij op de VPS (publiek netwerk) altijd dicht tenzij jij
het wachtwoord instelt -- precies zoals ANTHROPIC_API_KEY werkt.

Inhaken in de journal (app/main.py), VOOR de eerste route wordt geraakt --
in de praktijk maakt het niet uit waar in het bestand, als het maar na
`app = FastAPI(...)` staat:

    from beveiliging import zet_wachtwoord_op
    zet_wachtwoord_op(app)

Alleen het wachtwoord wordt gecontroleerd, niet de gebruikersnaam -- je kunt
in het inlogschermpje van je telefoon dus alles als gebruikersnaam intikken.
"""

import base64
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import Response


def zet_wachtwoord_op(app: FastAPI) -> bool:
    """Registreert de wachtwoordcheck op `app`. Geeft True terug als hij
    actief is gezet, False als er geen JOURNAL_WACHTWOORD is (dan blijft
    de journal onbeveiligd -- bedoeld voor lokaal gebruik op je laptop)."""
    wachtwoord = os.environ.get("JOURNAL_WACHTWOORD")
    if not wachtwoord:
        print("[journal] JOURNAL_WACHTWOORD niet gezet -- journal blijft open "
              "(prima op je laptop, NIET op een server met een publiek IP).")
        return False

    @app.middleware("http")
    async def _controleer_wachtwoord(request: Request, call_next):
        auth = request.headers.get("authorization", "")
        toegestaan = False
        if auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth[6:]).decode("utf-8")
                _, _, ingevuld = decoded.partition(":")
                toegestaan = secrets.compare_digest(ingevuld, wachtwoord)
            except Exception:
                toegestaan = False
        if toegestaan:
            return await call_next(request)
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="CBR Journal"'},
        )

    print("[journal] wachtwoordpoort actief.")
    return True
