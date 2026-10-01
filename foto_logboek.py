# -*- coding: utf-8 -*-
"""
foto_logboek.py -- de mobiele foto-uploadpagina van de journal (WP9).

Een FastAPI-router die je in de bestaande app inhaakt:

    from foto_logboek import router as foto_router
    app.include_router(foto_router)

Drie endpoints:
    GET  /logboek/foto          -> de mobielvriendelijke pagina
    POST /logboek/foto/lees     -> leest niveaus uit 1 of 2 screenshots (foto_lezer)
    POST /logboek/foto/bewaar   -> schrijft de bevestigde trade in de journal

De API-sleutel komt uit de omgevingsvariabele ANTHROPIC_API_KEY (op de VPS
gezet), nooit uit code. Zonder sleutel blijft de pagina werken: je kunt dan de
niveaus met de hand invullen.

Losse koppeling met de journal: de insert gaat via een injecteerbare
bewaar-functie. Standaard probeert hij app.db + app.cbr te gebruiken (de
bestaande journal), maar je kunt in de test een eigen functie meegeven.
"""

import base64
import json
import os
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

import foto_lezer

router = APIRouter()

# de acht CBR-poorten; wat de gebruiker aanvinkt komt als f2_<sleutel> = yes/maybe
POORTEN = [
    ("bias", "1H-bias goed"), ("dxy", "DXY-correlatie invers"),
    ("expansie", "schone expansie"), ("sweep", "sweep van 1H high/low"),
    ("shift", "type-3 shift"), ("entry", "entry op 50%"),
    ("sl", "SL netjes geplaatst"), ("tp", "TP-logica goed"),
]


# --------------------------------------------------------------- client

def _client():
    """Bouwt een Anthropic-client, of None als er geen sleutel is."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        return anthropic.Anthropic()
    except Exception:
        return None


# --------------------------------------------------------------- bewaren

def _standaard_bewaar(trade: dict) -> int:
    """
    Schrijft de trade in de echte journal via de bestaande app-modules.
    Wordt alleen aangeroepen op de VPS/laptop waar de journal draait.
    """
    from app import db, cbr  # lazy: alleen nodig als er echt bewaard wordt

    basis = dict(
        instrument="XAUUSD", fase=cbr.FASE_ACTIEF, bron="live", status="genomen",
        tags="foto", sessie="",
        f2_bias="maybe", f2_dxy="maybe", f2_expansie="maybe", f2_sweep="maybe",
        f2_shift="maybe", f2_entry="maybe", f2_sl="maybe", f2_tp="maybe",
        crit1_conditie="maybe", crit2_sweep="maybe", crit3_shift="maybe",
        crit4_entry="maybe", crit5_tp="maybe", bias_1hr="", dxy_richting="",
    )
    basis.update(trade)
    basis["grade"] = cbr.compute_grade_f2(basis)
    with db.get_conn() as conn:
        return db._insert_trade(conn, basis)


# de bewaar-functie is vervangbaar (voor de test)
bewaar_functie = _standaard_bewaar


# --------------------------------------------------------------- endpoints

@router.get("/logboek/foto", response_class=HTMLResponse)
def pagina():
    return PAGINA_HTML


@router.post("/logboek/foto/lees")
async def lees(foto: UploadFile = File(...),
               is_positie_tool: bool = Form(False),
               eerste: Optional[str] = Form(None)):
    """
    Leest de niveaus uit een screenshot. 'eerste' is de JSON van een eerdere
    uitlezing (bij de tweede foto), zodat we ze kunnen samenvoegen.
    """
    client = _client()
    if client is None:
        return JSONResponse({"fout": "geen_sleutel",
                             "boodschap": "Geen API-sleutel op de server; vul de "
                             "niveaus met de hand in."}, status_code=200)

    inhoud = await foto.read()
    media = foto.content_type or "image/png"
    u = foto_lezer.lees_niveaus(inhoud, client, media_type=media,
                                is_positie_tool=is_positie_tool)
    if eerste:
        try:
            e = foto_lezer.Uitlezing(**{k: v for k, v in json.loads(eerste).items()
                                        if k in foto_lezer.Uitlezing.__dataclass_fields__})
            u = foto_lezer.combineer(e, u)
        except Exception:
            pass  # bij twijfel houden we gewoon de nieuwe uitlezing aan

    d = u.dict()
    d.pop("ruw", None)  # ruwe modeltekst hoeft niet naar de browser
    d["compleet"] = u.compleet
    d["vraag_tweede"] = u.vraag_tweede
    d["ontbreekt"] = u.ontbreekt
    return JSONResponse(d)


@router.post("/logboek/foto/bewaar")
async def bewaar(datum: str = Form(...), richting: str = Form(...),
                 tijd_entry: str = Form(""),
                 entry: Optional[float] = Form(None),
                 sl: Optional[float] = Form(None),
                 tp: Optional[float] = Form(None),
                 resultaat_eur: Optional[float] = Form(None),
                 charges: Optional[float] = Form(None),
                 lot: Optional[float] = Form(None),
                 staat_vooraf: str = Form(""),
                 notities: str = Form(""),
                 poorten_json: str = Form("{}"),
                 foutcodes: str = Form(""),
                 gelezen_json: str = Form(""),
                 tweede_foto: bool = Form(False)):
    """Schrijft de bevestigde trade weg. Grade wordt in de journal berekend."""
    if richting not in ("long", "short"):
        raise HTTPException(400, "richting moet long of short zijn")

    trade = dict(datum=datum, richting=richting, tijd_entry=tijd_entry,
                 entry_prijs=entry, sl_prijs=sl, tp_prijs=tp,
                 resultaat_eur=resultaat_eur, charges=charges, lot=lot,
                 staat_vooraf=staat_vooraf, notities=notities,
                 foutcodes=foutcodes or None)

    # minuut in het uur -- gratis uit de entrytijd, en nodig voor de vraag
    # "op welk moment van het uur ben ik succesvol"
    if tijd_entry and ":" in tijd_entry:
        try:
            trade["minuut_in_uur"] = int(tijd_entry.split(":")[1])
        except ValueError:
            pass

    # de pre-trade kaart van vandaag eraan hangen, als je er een invulde
    try:
        import pretrade
        con = pretrade._conn()
        try:
            kaart = pretrade.open_kaart(con, datum)
            if kaart:
                trade.update(pretrade.koppel_kaart(con, kaart["id"]))
            trade["dagtype"] = pretrade.dagtype(
                __import__("datetime").date.fromisoformat(datum), pretrade.lees_config())
        finally:
            con.close()
    except Exception:
        pass  # zonder pretrade-module werkt het logboek gewoon door
    # RR uit de niveaus, als ze er zijn
    if entry and sl and tp and entry != sl:
        trade["rr"] = round(abs(tp - entry) / abs(entry - sl), 2)
    # aangevinkte poorten -> f2_<sleutel> = yes, de rest blijft maybe
    try:
        aangevinkt = json.loads(poorten_json)
    except Exception:
        aangevinkt = {}
    for sleutel, _ in POORTEN:
        if aangevinkt.get(sleutel):
            trade[f"f2_{sleutel}"] = "yes"

    trade = {k: v for k, v in trade.items() if v is not None}
    try:
        tid = bewaar_functie(trade)
    except Exception as e:
        raise HTTPException(500, f"kon niet bewaren: {e}")

    # De foto-lezer meet zichzelf: elke correctie die jij maakt is een gratis
    # meting van zijn nauwkeurigheid. Zonder dit blijft het een black box.
    meet_lezer(gelezen_json,
               {"richting": richting, "entry": entry, "sl": sl, "tp": tp},
               tweede_foto)
    return JSONResponse({"ok": True, "id": tid})


def _gelijk(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return abs(float(a) - float(b)) < 0.005
    except (TypeError, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()


def meet_lezer(gelezen_json: str, definitief: dict, tweede_foto: bool = False) -> int:
    """Legt per veld vast wat het model las en wat jij ervan maakte.
    Stil falen is prima -- dit mag het loggen van een trade nooit blokkeren."""
    if not gelezen_json:
        return 0
    try:
        gelezen = json.loads(gelezen_json)
    except Exception:
        return 0
    try:
        import pretrade
        con = pretrade._conn()
    except Exception:
        return 0
    n = 0
    try:
        from datetime import datetime as _dt
        for veld in ("richting", "entry", "sl", "tp"):
            g, d = gelezen.get(veld), definitief.get(veld)
            if g is None and d is None:
                continue
            con.execute(
                """INSERT INTO lezer_meting (ts, veld, gelezen, gecorrigeerd,
                   klopte, tweede_foto) VALUES (?,?,?,?,?,?)""",
                (_dt.now().isoformat(timespec="seconds"), veld,
                 None if g is None else str(g), None if d is None else str(d),
                 1 if _gelijk(g, d) else 0, 1 if tweede_foto else 0))
            n += 1
        con.commit()
    except Exception:
        pass
    finally:
        con.close()
    return n


# --------------------------------------------------------------- de pagina

# Mobiel-eerst, geen frameworks, geen externe scripts. In-memory state, geen
# localStorage (draait straks in een normale browser, maar we houden het simpel).
_POORT_VINKJES = "".join(
    f'<label class="vink"><input type="checkbox" name="poort" value="{s}">{lbl}</label>'
    for s, lbl in POORTEN)

# De zeven vaste foutcodes uit de Herziening. Knoppen in plaats van vrije tekst,
# zodat de weekmail ze kan optellen ("drie keer buiten venster").
FOUTCODES = ["buiten venster", "tegen bias", "te vroeg ingestapt", "SL te krap",
             "te vroeg gesloten", "boven dagmaximum", "geen echte shift"]
_FOUTCODE_KNOPPEN = "".join(
    f'<span class="fout" data-code="{c}" onclick="this.classList.toggle(\'aan\')">{c}</span>'
    for c in FOUTCODES)

PAGINA_HTML = """<!doctype html><html lang="nl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade loggen met foto</title>
<style>
  :root{--bg:#f7f4ef;--panel:#fff;--rand:#ddd7cd;--tekst:#1c1c1c;--grijs:#6b6b6b;--accent:#6d4dea;--groen:#26a69a}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--tekst);font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
       padding:16px;max-width:520px;margin:0 auto;-webkit-text-size-adjust:100%}
  h1{font-size:20px;margin:4px 0 16px}
  .kaart{background:var(--panel);border:1px solid var(--rand);border-radius:12px;padding:16px;margin-bottom:14px}
  label{display:block;font-size:14px;margin:10px 0 4px;color:var(--grijs)}
  input[type=text],input[type=number],input[type=date],select,textarea,button{
    width:100%;font-size:16px;padding:12px;border:1px solid var(--rand);border-radius:10px;background:#fff}
  textarea{min-height:70px}
  .knop{background:var(--accent);color:#fff;border:none;font-weight:600;padding:16px;cursor:pointer}
  .knop.groot{font-size:17px}
  .rij{display:flex;gap:10px}.rij>*{flex:1}
  .vink{display:flex;align-items:center;gap:8px;font-size:15px;color:var(--tekst);margin:6px 0}
  .vink input{width:auto}
  .verborgen{display:none}
  .fout{display:inline-block;padding:9px 13px;margin:4px 4px 0 0;border:1px solid var(--rand);
        border-radius:20px;font-size:14px;background:#fff;cursor:pointer;user-select:none}
  .fout.aan{background:#ffe9e9;border-color:#e08a8a;font-weight:600}
  .melding{padding:12px;border-radius:10px;margin:10px 0;font-size:14px}
  .info{background:#eef;border:1px solid #ccd}.warn{background:#fff3cd;border:1px solid #ffe08a}
  .ok{background:#e7f7f4;border:1px solid var(--groen)}
  .niveau{font-variant-numeric:tabular-nums;font-weight:600}
  small{color:var(--grijs)}
</style></head><body>
<h1>Trade loggen</h1>

<div class="kaart" id="stap-foto">
  <label>Screenshot van de chart</label>
  <input type="file" id="foto" accept="image/*" capture="environment">
  <button class="knop groot" id="lees-knop" style="margin-top:12px">Lees niveaus uit foto</button>
  <div id="lees-melding"></div>
</div>

<div class="kaart verborgen" id="stap-tweede">
  <div class="melding warn">De SL of TP was niet leesbaar. Open de positie op
    TradingView (zodat entry/SL/TP als tekst staan) en upload die screenshot.</div>
  <input type="file" id="foto2" accept="image/*" capture="environment">
  <button class="knop groot" id="lees2-knop" style="margin-top:12px">Lees tweede foto</button>
</div>

<form id="form" class="kaart verborgen">
  <div class="rij">
    <div><label>Datum</label><input type="date" name="datum" required></div>
    <div><label>Tijd entry</label><input type="text" name="tijd_entry" placeholder="10:29"></div>
  </div>
  <label>Richting</label>
  <select name="richting" required><option value="long">long (buy)</option>
    <option value="short">short (sell)</option></select>
  <div class="rij">
    <div><label>Entry</label><input type="number" step="0.01" name="entry"></div>
    <div><label>SL</label><input type="number" step="0.01" name="sl"></div>
    <div><label>TP</label><input type="number" step="0.01" name="tp"></div>
  </div>
  <div class="rij">
    <div><label>Resultaat &euro;</label><input type="number" step="0.01" name="resultaat_eur"></div>
    <div><label>Charges &euro;</label><input type="number" step="0.01" name="charges"></div>
    <div><label>Lot</label><input type="number" step="0.01" name="lot"></div>
  </div>
  <label>Staat vooraf</label>
  <select name="staat_vooraf"><option value="">-</option><option>rustig</option>
    <option>gehaast</option><option>moe</option></select>
  <label>Wat ging goed / klopte?</label>
  __POORTEN__
  <label>Ging er iets mis? (tik aan wat van toepassing is)</label>
  <div id="foutcodes">__FOUTCODES__</div>
  <label>Notities</label>
  <textarea name="notities" placeholder="Wat zag je, wat brak je?"></textarea>
  <button type="submit" class="knop groot" style="margin-top:14px">Bewaar in journal</button>
  <div id="bewaar-melding"></div>
</form>

<script>
let uitlezing = null;
let tweedeGebruikt = false;

function toon(id){document.getElementById(id).classList.remove('verborgen');}
function verberg(id){document.getElementById(id).classList.add('verborgen');}
function meld(waar, klasse, tekst){
  document.getElementById(waar).innerHTML = '<div class="melding '+klasse+'">'+tekst+'</div>';}

function vulForm(u){
  const f = document.getElementById('form');
  if(u.richting) f.richting.value = u.richting;
  if(u.entry!=null) f.entry.value = u.entry;
  if(u.sl!=null) f.sl.value = u.sl;
  if(u.tp!=null) f.tp.value = u.tp;
  if(!f.datum.value) f.datum.valueAsDate = new Date();
}

async function leesFoto(inputId, isTweede){
  if(isTweede) tweedeGebruikt = true;
  const inp = document.getElementById(inputId);
  if(!inp.files.length){meld('lees-melding','warn','Kies eerst een foto.');return;}
  const fd = new FormData();
  fd.append('foto', inp.files[0]);
  fd.append('is_positie_tool', isTweede ? 'true':'false');
  if(isTweede && uitlezing) fd.append('eerste', JSON.stringify(uitlezing));
  meld('lees-melding','info','Bezig met lezen...');
  let r;
  try{ r = await (await fetch('/logboek/foto/lees',{method:'POST',body:fd})).json(); }
  catch(e){ meld('lees-melding','warn','Lezen mislukt. Vul de niveaus met de hand in.'); toon('form'); return; }

  if(r.fout==='geen_sleutel'){ meld('lees-melding','warn',r.boodschap); toon('form'); vulForm({}); return; }
  if(r.fout){ meld('lees-melding','warn','Kon de niveaus niet lezen. Vul met de hand in.'); toon('form'); return; }

  uitlezing = r;
  vulForm(r);
  if(r.vraag_tweede && !isTweede){
    meld('lees-melding','info','Entry gelezen, maar SL/TP nog niet compleet.');
    toon('stap-tweede');
    return;
  }
  const n = [];
  if(r.entry!=null) n.push('entry <span class="niveau">'+r.entry+'</span>');
  if(r.sl!=null) n.push('SL <span class="niveau">'+r.sl+'</span>');
  if(r.tp!=null) n.push('TP <span class="niveau">'+r.tp+'</span>');
  meld('lees-melding','ok','Gelezen: '+(r.richting||'?')+' &middot; '+n.join(' &middot; ')+
       '<br><small>Controleer en corrigeer hieronder voordat je bewaart.</small>');
  toon('form');
}

document.getElementById('lees-knop').onclick = (e)=>{e.preventDefault();leesFoto('foto',false);};
document.getElementById('lees2-knop').onclick = (e)=>{e.preventDefault();leesFoto('foto2',true);};

document.getElementById('form').onsubmit = async (e)=>{
  e.preventDefault();
  const f = e.target, fd = new FormData(f);
  const poorten = {};
  f.querySelectorAll('input[name=poort]:checked').forEach(c=>poorten[c.value]=true);
  fd.delete('poort'); fd.append('poorten_json', JSON.stringify(poorten));
  const fouten=[...document.querySelectorAll('#foutcodes .fout.aan')].map(b=>b.dataset.code);
  fd.append('foutcodes', fouten.join(','));
  // wat de lezer ervan maakte meesturen, zodat hij zijn eigen nauwkeurigheid meet
  if(uitlezing){
    fd.append('gelezen_json', JSON.stringify({richting:uitlezing.richting,
      entry:uitlezing.entry, sl:uitlezing.sl, tp:uitlezing.tp}));
    fd.append('tweede_foto', tweedeGebruikt ? 'true' : 'false');
  }
  meld('bewaar-melding','info','Bewaren...');
  try{
    const r = await (await fetch('/logboek/foto/bewaar',{method:'POST',body:fd})).json();
    if(r.ok){ meld('bewaar-melding','ok','Opgeslagen als trade #'+r.id+'. Je kunt de pagina sluiten.'); f.querySelector('button[type=submit]').disabled=true; }
    else meld('bewaar-melding','warn','Bewaren mislukt.');
  }catch(err){ meld('bewaar-melding','warn','Bewaren mislukt: '+err); }
};
</script>
</body></html>""".replace("__POORTEN__", _POORT_VINKJES)\
                 .replace("__FOUTCODES__", _FOUTCODE_KNOPPEN)
