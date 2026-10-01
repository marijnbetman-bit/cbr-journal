# -*- coding: utf-8 -*-
"""
pretrade.py -- de pre-trade kaart, de dagrem en de no-trade knop (blok 2).

Waarom dit bestaat: alles wat de journal tot nu toe deed gebeurde NA de trade.
Deze module werkt ervoor. Je tikt vijf vinkjes voordat je instapt; dat is
tegelijk je rem en je data. Vijf van de vijf heet een "schone trade", en het
percentage schone trades is het weekgetal waar je op stuurt.

Inhaken in de journal (app/main.py):
    from pretrade import router as pretrade_router
    app.include_router(pretrade_router)

Drie routes:
    GET  /kaart           de kaart (mobiel-eerst)
    POST /kaart           kaart opslaan -> geeft voorgenomen_id terug
    POST /geen-trade      "niets gezien" of "bewust gelaten" vastleggen

Het venster komt uit journal_config.json en wordt bij elke aanroep opnieuw
gelezen. Verplaats je je handelsmoment naar een andere sessie, dan hoef je hier
niets aan te passen.
"""

import json
import os
import sqlite3
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()

HIER = os.path.dirname(os.path.abspath(__file__))
CONFIG_PAD = os.path.join(HIER, "journal_config.json")
DB_PAD = os.path.join(HIER, "cbr_journal.db")

STANDAARD_CONFIG = {
    "venster_van": "11:00", "venster_tot": "12:00",
    "dagmaximum": 2, "handelsdagen": [1, 3],
    "foutcodes": ["buiten venster", "tegen bias", "te vroeg ingestapt",
                  "SL te krap", "te vroeg gesloten", "boven dagmaximum",
                  "geen echte shift"],
}

# De vijf vragen. Sleutel -> (korte label, uitleg onder het label).
CHECKS = [
    ("venster",  "Binnen mijn venster",      "het moment waarop ik heb afgesproken te handelen"),
    ("dagmax",   "Trade 1 of 2 van vandaag", "mijn eigen regel: maximaal twee pogingen"),
    ("bias",     "1H-bias gecheckt én akkoord", "niet 'ik denk het' maar 'ik heb gekeken'"),
    ("entry50",  "Entry op de 50%",          "de eerste pullback, niet eerder instappen"),
    ("sl",       "SL 5+ points voorbij de sweep", "zodat een liquidity grab hem niet meepakt"),
]
SLEUTELS = [s for s, _, _ in CHECKS]


def lees_config() -> dict:
    cfg = dict(STANDAARD_CONFIG)
    try:
        with open(CONFIG_PAD, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items()
                        if not k.startswith("_")})
    except FileNotFoundError:
        pass
    return cfg


def dagtype(d: date, cfg: dict) -> str:
    """Thuiswerkdag, kantoordag of weekend -- gratis uit de datum."""
    if d.weekday() >= 5:
        return "weekend"
    return "thuiswerk" if d.weekday() in cfg.get("handelsdagen", []) else "kantoor"


def in_venster(nu: datetime, cfg: dict) -> bool:
    kl = nu.strftime("%H:%M")
    return cfg["venster_van"] <= kl < cfg["venster_tot"]


def _conn(db_pad=None):
    con = sqlite3.connect(db_pad or DB_PAD)
    con.row_factory = sqlite3.Row
    return con


def kaarten_vandaag(con, datum: str) -> int:
    r = con.execute("SELECT COUNT(*) c FROM voorgenomen WHERE datum=?", (datum,)).fetchone()
    return r["c"] if r else 0


def trades_vandaag(con, datum: str) -> int:
    r = con.execute("SELECT COUNT(*) c FROM trades WHERE datum=? "
                    "AND (status IS NULL OR status!='overgeslagen')", (datum,)).fetchone()
    return r["c"] if r else 0


def bewaar_kaart(con, datum: str, checks: dict, volgnummer: int,
                 doorgezet_reden: str = "") -> int:
    schoon = 1 if all(checks.get(s) for s in SLEUTELS) else 0
    cur = con.execute(
        """INSERT INTO voorgenomen
           (ts, datum, check_venster, check_dagmax, check_bias, check_entry50,
            check_sl, schoon, volgnummer, doorgezet_reden)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (datetime.now().isoformat(timespec="seconds"), datum,
         int(bool(checks.get("venster"))), int(bool(checks.get("dagmax"))),
         int(bool(checks.get("bias"))), int(bool(checks.get("entry50"))),
         int(bool(checks.get("sl"))), schoon, volgnummer, doorgezet_reden or None))
    con.commit()
    return cur.lastrowid


def open_kaart(con, datum: str) -> Optional[sqlite3.Row]:
    """De meest recente kaart van vandaag die nog niet aan een trade hangt.
    De foto-/logpagina haalt hem op zodat de vinkjes meereizen naar de trade."""
    return con.execute(
        "SELECT * FROM voorgenomen WHERE datum=? AND gebruikt=0 "
        "ORDER BY id DESC LIMIT 1", (datum,)).fetchone()


def koppel_kaart(con, voorgenomen_id: int) -> dict:
    """Markeert de kaart als gebruikt en geeft de velden terug voor de trade."""
    rij = con.execute("SELECT * FROM voorgenomen WHERE id=?", (voorgenomen_id,)).fetchone()
    if not rij:
        return {}
    con.execute("UPDATE voorgenomen SET gebruikt=1 WHERE id=?", (voorgenomen_id,))
    con.commit()
    return {
        "voorgenomen_id": voorgenomen_id,
        "check_venster": rij["check_venster"], "check_dagmax": rij["check_dagmax"],
        "check_bias": rij["check_bias"], "check_entry50": rij["check_entry50"],
        "check_sl": rij["check_sl"], "schoon": rij["schoon"],
        "checks_vooraf": 1,
    }


def bewaar_geen_trade(con, datum: str, soort: str, notitie: str, dt: str) -> int:
    if soort not in ("niets_gezien", "bewust_gelaten"):
        raise ValueError("onbekende soort")
    cur = con.execute(
        "INSERT INTO geen_trade (ts, datum, soort, notitie, dagtype) VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), datum, soort,
         notitie or None, dt))
    con.commit()
    return cur.lastrowid


# --------------------------------------------------------------- routes

@router.get("/kaart", response_class=HTMLResponse)
def kaart():
    cfg = lees_config()
    nu = datetime.now()
    vandaag = nu.date()
    con = _conn()
    try:
        n_kaarten = kaarten_vandaag(con, vandaag.isoformat())
        n_trades = trades_vandaag(con, vandaag.isoformat())
    finally:
        con.close()

    dt = dagtype(vandaag, cfg)
    binnen = in_venster(nu, cfg)
    volgnummer = n_kaarten + 1
    rem = volgnummer > cfg["dagmaximum"]

    # de eerste twee vinkjes weten we zelf al -- die staan voorgevuld maar
    # blijven aanpasbaar, want jij bent de baas over je eigen kaart.
    voorgevuld = {"venster": binnen, "dagmax": volgnummer <= cfg["dagmaximum"]}

    vinkjes = "".join(
        f'<label class="vink{" uit" if not voorgevuld.get(s, False) else ""}">'
        f'<input type="checkbox" name="{s}" {"checked" if voorgevuld.get(s) else ""}>'
        f'<span><b>{label}</b><small>{uitleg}</small></span></label>'
        for s, label, uitleg in CHECKS)

    context = (f'{dt} · {nu:%H:%M} · venster {cfg["venster_van"]}–{cfg["venster_tot"]}'
               f' · kaart {volgnummer} van vandaag')
    rem_html = ""
    if rem:
        rem_html = (
            f'<div class="rem"><b>Dit wordt poging {volgnummer} vandaag.</b><br>'
            f'Je eigen regel zegt maximaal {cfg["dagmaximum"]} per dag, en klaar na '
            f'één winst. Ga je door, geef dan even aan waarom — dat telt mee in je week.'
            f'<input type="text" id="reden" placeholder="waarom zet ik toch door?"></div>')

    return PAGINA.replace("__VINKJES__", vinkjes)\
                 .replace("__CONTEXT__", context)\
                 .replace("__REM__", rem_html)\
                 .replace("__BUITEN__", "" if binnen else
                          '<div class="waarschuw">Je zit <b>buiten je venster</b>. '
                          'Dat mag, maar het telt mee als niet-schoon.</div>')


@router.post("/kaart")
async def kaart_opslaan(venster: Optional[str] = Form(None),
                        dagmax: Optional[str] = Form(None),
                        bias: Optional[str] = Form(None),
                        entry50: Optional[str] = Form(None),
                        sl: Optional[str] = Form(None),
                        doorgezet_reden: str = Form("")):
    cfg = lees_config()
    vandaag = date.today().isoformat()
    checks = {"venster": bool(venster), "dagmax": bool(dagmax), "bias": bool(bias),
              "entry50": bool(entry50), "sl": bool(sl)}
    con = _conn()
    try:
        volgnummer = kaarten_vandaag(con, vandaag) + 1
        vid = bewaar_kaart(con, vandaag, checks, volgnummer, doorgezet_reden)
    finally:
        con.close()
    schoon = all(checks.values())
    ontbreekt = [lbl for s, lbl, _ in CHECKS if not checks[s]]
    return JSONResponse({"ok": True, "voorgenomen_id": vid, "schoon": schoon,
                         "ontbreekt": ontbreekt, "volgnummer": volgnummer})


@router.post("/geen-trade")
async def geen_trade(soort: str = Form(...), notitie: str = Form("")):
    cfg = lees_config()
    vandaag = date.today()
    con = _conn()
    try:
        gid = bewaar_geen_trade(con, vandaag.isoformat(), soort, notitie,
                                dagtype(vandaag, cfg))
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        con.close()
    return JSONResponse({"ok": True, "id": gid})


# --------------------------------------------------------------- de pagina

PAGINA = """<!doctype html><html lang="nl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Voor je instapt</title>
<style>
 :root{--bg:#f7f4ef;--panel:#fff;--rand:#ddd7cd;--tekst:#1c1c1c;--grijs:#6b6b6b;
       --accent:#6d4dea;--groen:#26a69a;--waarschuw:#b26a00}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--tekst);padding:16px;max-width:520px;
      margin:0 auto;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
 h1{font-size:20px;margin:4px 0 2px}
 .context{font-size:13px;color:var(--grijs);margin-bottom:14px}
 .kaart{background:var(--panel);border:1px solid var(--rand);border-radius:12px;padding:8px 14px}
 .vink{display:flex;gap:12px;align-items:flex-start;padding:14px 2px;
       border-bottom:1px solid var(--rand);cursor:pointer}
 .vink:last-child{border-bottom:none}
 .vink input{width:22px;height:22px;margin-top:2px;flex:none}
 .vink span{display:flex;flex-direction:column}
 .vink small{color:var(--grijs);font-size:13px;margin-top:2px}
 .score{text-align:center;padding:16px 0 4px;font-size:15px}
 .score b{font-size:28px;display:block}
 .schoon{color:var(--groen)}.vuil{color:var(--waarschuw)}
 button{width:100%;font-size:17px;padding:16px;border:none;border-radius:10px;
        background:var(--accent);color:#fff;font-weight:600;margin-top:14px;cursor:pointer}
 button.grijs{background:#fff;color:var(--tekst);border:1px solid var(--rand);font-weight:500}
 .waarschuw,.rem{padding:12px;border-radius:10px;margin:12px 0;font-size:14px}
 .waarschuw{background:#fff3cd;border:1px solid #ffe08a}
 .rem{background:#ffe9e9;border:1px solid #f5b5b5}
 .rem input{width:100%;margin-top:8px;padding:10px;border:1px solid var(--rand);border-radius:8px;font-size:16px}
 .uitkomst{padding:14px;border-radius:10px;margin-top:12px;font-size:15px;display:none}
 .ok{background:#e7f7f4;border:1px solid var(--groen)}
 .let{background:#fff3cd;border:1px solid #ffe08a}
 .scheiding{margin:22px 0 8px;font-size:13px;color:var(--grijs);text-align:center}
</style></head><body>
<h1>Voor je instapt</h1>
<div class="context">__CONTEXT__</div>
__BUITEN__
__REM__
<form id="f" class="kaart">__VINKJES__</form>
<div class="score" id="score"></div>
<button id="start">Ik stap in</button>
<div class="uitkomst" id="uit"></div>

<div class="scheiding">of</div>
<button class="grijs" onclick="geenTrade('niets_gezien')">Vandaag niets gezien</button>
<button class="grijs" onclick="geenTrade('bewust_gelaten')">Setup gezien, bewust gelaten</button>

<script>
const f=document.getElementById('f'), score=document.getElementById('score');
function ververs(){
  const aan=[...f.querySelectorAll('input[type=checkbox]')].filter(c=>c.checked).length;
  const schoon = aan===5;
  score.innerHTML='<b class="'+(schoon?'schoon':'vuil')+'">'+aan+' / 5</b>'+
    (schoon?'schone trade':'dit telt als niet-schoon');
  f.querySelectorAll('.vink').forEach(v=>{
    v.classList.toggle('uit', !v.querySelector('input').checked);});
}
f.addEventListener('change', ververs); ververs();

document.getElementById('start').onclick=async()=>{
  const fd=new FormData(f);
  const reden=document.getElementById('reden');
  if(reden) fd.append('doorgezet_reden', reden.value);
  const r=await (await fetch('/kaart',{method:'POST',body:fd})).json();
  const u=document.getElementById('uit');
  u.style.display='block';
  if(r.schoon){ u.className='uitkomst ok';
    u.innerHTML='<b>Schone trade.</b> Alle vijf staan aan. Succes — log \'m straks met een foto.';
  } else { u.className='uitkomst let';
    u.innerHTML='<b>Genoteerd, '+(5-r.ontbreekt.length)+' van 5.</b><br>Niet afgevinkt: '+
      r.ontbreekt.join(', ')+'.<br><small>Je mag gewoon door — het telt alleen mee in je weekcijfer.</small>';
  }
};

async function geenTrade(soort){
  const notitie = soort==='bewust_gelaten'
    ? (prompt('Waarom liet je hem lopen? (mag leeg)')||'') : '';
  const fd=new FormData(); fd.append('soort',soort); fd.append('notitie',notitie);
  const r=await (await fetch('/geen-trade',{method:'POST',body:fd})).json();
  const u=document.getElementById('uit');
  u.style.display='block'; u.className='uitkomst ok';
  u.innerHTML='<b>Vastgelegd.</b> Ook een dag zonder trade telt mee — zonder die dagen kun je discipline niet meten.';
}
</script></body></html>"""
