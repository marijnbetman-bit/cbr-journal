# -*- coding: utf-8 -*-
"""
journal_bot.py -- de journal-bot in Telegram.

Zodra MT5 een gesloten trade oplevert, stuurt deze bot je één bericht met de
trade en tien knoppen: je 5 checks en je 5 CBR-criteria. Venster en
dagmaximum staan al ingevuld (feiten); die kun je nog omzetten. Na elke tik
wordt de grade opnieuw berekend en staat hij in het bericht.

Antwoord op het bericht met tekst = notitie bij die trade.
Commando's: /open (wat nog beoordeeld moet), /vandaag, /help.

Sinds 23 sep is dit de ENIGE bot: ook de signalen (signalen.py) lopen via
deze bot. Commando's: /status, /signalen, /log, /test. Knoppen onder een
signaal ('s:{id}:1|0') gaan naar signalen.callback.

Instellingen in journal_config.json:
    "telegram_journal": {"token": "...", "chat_id": 1560183106, "aan": true}
Wordt elke halve minuut herlezen: token invullen = binnen 30 sec actief.
"""

import json
import re
import os
import sqlite3
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

HIER = os.path.dirname(os.path.abspath(__file__))
DB_PAD = os.path.join(HIER, "cbr_journal.db")
CONFIG_PAD = os.path.join(HIER, "journal_config.json")
STATE_PAD = os.path.join(HIER, "journal_bot_state.json")

import beoordelen as B    # noqa: E402

KORT = {
    "s_impuls": "Impuls valide", "s_top": "Top + mini-pullback",
    "s_sweep": "Sweep ≤30 pts", "s_bos": "BOS candle-close",
    "f2_entry": "Entry op 50%", "f2_sl": "SL 5+ pts voorbij sweep",
    "check_venster": "Binnen venster", "check_dagmax": "Binnen dagmax",
    "check_sl_vast": "SL niet verschoven", "check_beheer": "Laten lopen tot SL/TP",
}
VOLGORDE = B.CRIT_KEYS + B.CHECK_KEYS

_STATUS = {"actief": False, "melding": "nog niet gestart", "bot": None}
_LOCK = threading.Lock()


def cfg():
    try:
        with open(CONFIG_PAD, encoding="utf-8") as f:
            c = json.load(f).get("telegram_journal") or {}
    except (FileNotFoundError, ValueError):
        c = {}
    return {"token": (c.get("token") or "").strip(), "chat_id": c.get("chat_id"),
            "aan": c.get("aan", True)}


def status():
    return dict(_STATUS)


def _conn():
    con = sqlite3.connect(DB_PAD, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS journal_bot_berichten ("
                "message_id INTEGER PRIMARY KEY, trade_id INTEGER, ts TEXT)")
    return con


class Conflict(Exception):
    pass


_SSL = None


def _ssl_ctx():
    """HTTPS naar Telegram. Op sommige servers (VPS met virusscanner/proxy die
    HTTPS inspecteert) kent Python de certificaten niet die Windows wel kent.
    Volgorde: Windows-certificaatopslag (truststore) -> certifi -> standaard.
    Alleen als je in journal_config.json > telegram_journal "ssl_controle": false
    zet, gaat de controle uit (af te raden; alleen als laatste redmiddel)."""
    global _SSL
    if _SSL is not None:
        return _SSL
    import ssl
    try:
        with open(CONFIG_PAD, encoding="utf-8") as f:
            controle = (json.load(f).get("telegram_journal") or {}).get("ssl_controle", True)
    except (FileNotFoundError, ValueError):
        controle = True
    if controle is False:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        print("[journal-bot] LET OP: SSL-controle staat uit (ssl_controle=false)")
    else:
        ctx = None
        try:
            import truststore
            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            ctx = ssl.create_default_context()
            try:
                import certifi
                ctx.load_verify_locations(certifi.where())
            except Exception:
                pass
    _SSL = ctx
    return ctx


def api(token, methode, data=None, timeout=35):
    url = f"https://api.telegram.org/bot{token}/{methode}"
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        tekst = e.read().decode("utf-8", "replace")
        if e.code == 409:
            raise Conflict(tekst)
        if e.code == 400 and "message is not modified" in tekst:
            return {"ok": True}
        raise RuntimeError(f"Telegram {e.code}: {tekst[:200]}")


# ------------------------------------------------------------------ opmaak

def _eur(v):
    if v is None:
        return "–"
    return ("+" if v >= 0 else "−") + "€" + f"{abs(v):.2f}".replace(".", ",")


def tekst_voor(t):
    netto = None if t["resultaat_eur"] is None else (t["resultaat_eur"] or 0) + (t["charges"] or 0)
    kleur = "🟢" if (netto or 0) >= 0 else "🔴"
    regels = [
        f"{kleur} <b>{_eur(t['resultaat_eur'])}</b>  ·  {(t['richting'] or '').upper()}  "
        f"{t['tijd_entry'] or ''}–{t['tijd_exit'] or ''}  ·  {t['exit_reden'] or ''}",
    ]
    bits = []
    if t["resultaat_r"] is not None:
        bits.append(f"{t['resultaat_r']:+.2f}R".replace(".", ","))
    if t["rr"] is not None:
        bits.append(f"RR {t['rr']:.1f}".replace(".", ","))
    if t["sl_afstand_points"] is not None:
        bits.append(f"SL {t['sl_afstand_points']:.0f} pts")
    if t["lot"]:
        bits.append(f"{t['lot']:.2f} lot".replace(".", ","))
    bits.append(f"charges {_eur(t['charges'])}")
    regels.append("  ·  ".join(bits) + f"  ·  #{t['id']}")
    if t["sl_prijs"] is None:
        regels.append("⚠️ <b>SL/TP niet gezien in MT5.</b> Antwoord op dit bericht met "
                      "<code>sl 4152.4 tp 4145.2</code> — dan reken ik R/RR uit en teken ik de chart.")
    regels.append("")
    klaar = t["beoordeeld"] == 1
    if klaar:
        schoon = "schone trade ✅" if t["schoon"] == 1 else "niet schoon"
        regels.append(f"<b>Grade {t['grade']}</b> · {schoon}")
        regels.append("<i>Tik gerust nog om iets te wijzigen. Antwoord op dit bericht voor een notitie.</i>")
    else:
        open_n = sum(1 for k in B.CRIT_KEYS if t[k] not in ("yes", "no"))
        if not t["emotie_voor"]:
            open_n += 1
        regels.append(f"Nog {open_n} te tikken. <b>1–6</b> de setup · <b>7–10</b> discipline (uit MT5) · en je emotie vooraf.")
        regels.append("<i>Discipline heb ik uit MT5 ingevuld; klopt het niet, tik dan om. Uitvoering/les: op de homepage.</i>")
    return "\n".join(regels)


def knoppen_voor(t):
    rijen = []
    for i, k in enumerate(VOLGORDE, 1):
        w = t[k]
        ja = (w == 1) if k in B.CHECK_KEYS else (w == "yes")
        nee = (w == 0) if k in B.CHECK_KEYS else (w == "no")
        rijen.append([
            {"text": f"{'✅' if ja else '▫️'} {i}. {KORT[k]}",
             "callback_data": f"b:{t['id']}:{k}:1"},
            {"text": "❌ nee" if nee else "nee", "callback_data": f"b:{t['id']}:{k}:0"},
        ])
    em = [{"text": ("● " if t["emotie_voor"] == k else "") + lbl, "callback_data": f"e:{t['id']}:{k}"}
          for k, lbl, _ in B.EMOTIES]
    rijen.append(em[:4])
    rijen.append(em[4:])
    return {"inline_keyboard": rijen}


# ------------------------------------------------------------------ versturen

def meld_trade(tid):
    c = cfg()
    if not (c["aan"] and c["token"] and c["chat_id"]):
        return False
    con = _conn()
    try:
        t = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
        if t is None:
            return False
        r = api(c["token"], "sendMessage", {
            "chat_id": c["chat_id"], "text": tekst_voor(t), "parse_mode": "HTML",
            "reply_markup": knoppen_voor(t)})
        mid = (r.get("result") or {}).get("message_id")
        if mid:
            con.execute("INSERT OR REPLACE INTO journal_bot_berichten VALUES (?,?,?)",
                        (mid, tid, datetime.now().isoformat(timespec="seconds")))
            con.commit()
        return True
    finally:
        con.close()


def stuur(c, tekst):
    api(c["token"], "sendMessage", {"chat_id": c["chat_id"], "text": tekst, "parse_mode": "HTML"})


# ------------------------------------------------------------------ ontvangen

def _callback(c, cb):
    data = cb.get("data") or ""
    if data.startswith("s:"):
        import signalen
        signalen.callback(c, cb)
        return
    antwoord = ""
    try:
        if data.startswith("e:"):
            _, tid, waarde = data.split(":")
            sleutel = None
        else:
            _, tid, sleutel, waarde = data.split(":")
        tid = int(tid)
        con = _conn()
        try:
            if sleutel is None:
                B.zet_mens(con, tid, "emotie_voor", waarde)
            else:
                B.zet_antwoord(con, tid, sleutel, waarde)
            t = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
        finally:
            con.close()
        msg = cb.get("message") or {}
        api(c["token"], "editMessageText", {
            "chat_id": msg.get("chat", {}).get("id"), "message_id": msg.get("message_id"),
            "text": tekst_voor(t), "parse_mode": "HTML", "reply_markup": knoppen_voor(t)})
        antwoord = f"Grade {t['grade']}" if t["beoordeeld"] == 1 else "Opgeslagen"
    except Exception as e:
        antwoord = "Kon dit niet opslaan"
        print("[journal-bot] callback:", e)
    api(c["token"], "answerCallbackQuery", {"callback_query_id": cb.get("id"), "text": antwoord})


def _bericht(c, m):
    if str((m.get("chat") or {}).get("id")) != str(c["chat_id"]):
        return                                   # alleen jij
    tekst = (m.get("text") or "").strip()
    reply = m.get("reply_to_message") or {}
    if reply.get("message_id") and tekst and not tekst.startswith("/"):
        # reply op een SIGNAAL-bericht = opmerking voor de dataset (1 okt 2026)
        try:
            import signalen
            sid = signalen.voeg_opmerking_toe(reply["message_id"], tekst)
        except Exception as e:
            sid = None
            print("[journal-bot] opmerking bij signaal:", e)
        if sid:
            stuur(c, f"📝 Opmerking opgeslagen bij signaal #{sid}.")
            return
        con = _conn()
        try:
            r = con.execute("SELECT trade_id FROM journal_bot_berichten WHERE message_id=?",
                            (reply["message_id"],)).fetchone()
            niveaus = dict((k.lower(), v.replace(",", ".")) for k, v in
                           re.findall(r"\b(sl|tp)\s*[:=]?\s*(\d+(?:[.,]\d+)?)", tekst, re.I))
            if r and niveaus:
                try:
                    v = B.zet_niveaus(con, r["trade_id"], niveaus.get("sl"), niveaus.get("tp"))
                    rr = f"{v['rr']:.2f}".replace(".", ",") if v.get("rr") is not None else "–"
                    res = f"{v['resultaat_r']:+.2f}R".replace(".", ",") if v.get("resultaat_r") is not None else "–"
                    stuur(c, f"✅ #{r['trade_id']}: SL {niveaus.get('sl', '–')} · TP {niveaus.get('tp', '–')} "
                             f"opgeslagen. Resultaat {res} · RR {rr} · grade {v.get('grade')}. Chart bijgewerkt.")
                except ValueError as e:
                    stuur(c, f"❌ Niet opgeslagen: {e}")
                return
            if r:
                B.voeg_notitie_toe(con, r["trade_id"], tekst)
                stuur(c, f"📝 Notitie opgeslagen bij trade #{r['trade_id']}.")
                return
        finally:
            con.close()
    cmd = tekst.split()[0].lower() if tekst else ""
    if cmd in ("/start", "/help"):
        stuur(c, "<b>CBR-bot</b> — signalen én journal in één\n\n"
                 "<b>Signalen</b>: 🟡 impuls gezien · 🟠 setup klaar (entry/SL/TP) · 🟢 entry geraakt. "
                 "Onder een klaar-signaal kies je: genomen · niet genomen · gemist: wel · gemist: niet "
                 "(had je hem genomen als je had gekeken?). Neem je hem in MT5, dan koppel ik hem zelf. "
                 "Antwoord op een signaal-bericht = opmerking voor de dataset.\n"
                 "<b>Journal</b>: elke gesloten trade uit MetaTrader komt hier met tien knoppen.\n"
                 "Antwoord op een trade-bericht = notitie.\n\n"
                 "/status — draait alles?\n/signalen — de signalen van vandaag\n"
                 "/log — wat de wachter de laatste 15 keer zag (/log 40 voor meer)\n"
                 "/open — wat nog beoordeeld moet\n/vandaag — je trades van vandaag\n"
                 "/replay 2026-09-22 — welke setups de wachter die dag gezien had\n"
                 "/test — even kijken of ik je bereik")
    elif cmd == "/status":
        import signalen
        try:
            import mt5_koppeling as K
            m = K.status()
            mt5 = ("MT5: verbonden" if m.get("verbonden") else "MT5: NIET verbonden") + \
                  f" · {m.get('melding', '')}"
        except Exception as e:
            mt5 = f"MT5: onbekend ({e})"
        stuur(c, f"✅ Ik draai.\n{mt5}\n{signalen.status_tekst()}\n"
                 f"Bot: {_STATUS.get('bot') or '?'}")
    elif cmd == "/signalen":
        import signalen
        stuur(c, signalen.vandaag_tekst())
    elif cmd == "/log":
        import signalen
        try:
            n = max(1, min(200, int(tekst.split()[1]))) if len(tekst.split()) > 1 else 15
        except ValueError:
            n = 15
        naam, regels = signalen.laatste_logregels(n)
        if not regels:
            stuur(c, "Nog geen log van de signaalwachter.")
        else:
            import html
            stuur(c, f"<b>{naam}</b>\n<pre>" + html.escape("\n".join(regels))[-3800:] + "</pre>")
    elif cmd == "/replay":
        import signalen
        delen = tekst.split()
        datum = delen[1] if len(delen) > 1 else date.today().isoformat()
        stuur(c, f"Ik speel {datum} opnieuw af, even geduld…")
        stuur(c, signalen.replay_tekst(signalen.replay_aanvraag(datum)))
    elif cmd == "/test":
        stuur(c, "✅ Test: ik bereik je. Signalen en journal lopen via deze bot.")
    elif cmd == "/open":
        con = _conn()
        try:
            ids = [r["id"] for r in con.execute(
                "SELECT id FROM trades WHERE beoordeeld=0 AND verwijderd_op IS NULL "
                "ORDER BY datum DESC, tijd_entry DESC LIMIT 5")]
        finally:
            con.close()
        if not ids:
            stuur(c, "Niets meer te beoordelen. 👌")
        for tid in reversed(ids):
            meld_trade(tid)
    elif cmd == "/vandaag":
        con = _conn()
        try:
            rijen = con.execute(
                "SELECT * FROM trades WHERE datum=? AND verwijderd_op IS NULL "
                "AND (status IS NULL OR status='genomen') ORDER BY tijd_entry",
                (date.today().isoformat(),)).fetchall()
        finally:
            con.close()
        if not rijen:
            stuur(c, "Vandaag nog geen trades.")
            return
        netto = sum((r["resultaat_eur"] or 0) + (r["charges"] or 0) for r in rijen)
        regels = [f"<b>Vandaag: {len(rijen)} trade(s), netto {_eur(netto)}</b>"]
        for r in rijen:
            regels.append(f"{r['tijd_entry'] or '--:--'} {(r['richting'] or '')[:5]:5} "
                          f"{_eur(r['resultaat_eur'])}  grade {r['grade']}"
                          + ("" if r["beoordeeld"] != 0 else "  (nog beoordelen)"))
        stuur(c, "\n".join(regels))


def _lees_offset():
    try:
        with open(STATE_PAD, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _schrijf_offset(st):
    try:
        with open(STATE_PAD, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except OSError:
        pass


def loop():
    st = _lees_offset()
    token_gezien = None
    while True:
        c = cfg()
        if not c["aan"] or not c["token"] or not c["chat_id"]:
            _STATUS.update(actief=False, melding="niet ingesteld (TELEGRAM-BOT-INSTELLEN.bat)")
            time.sleep(30)
            continue
        try:
            if token_gezien != c["token"]:
                me = api(c["token"], "getMe", timeout=15).get("result") or {}
                _STATUS["bot"] = "@" + (me.get("username") or "?")
                token_gezien = c["token"]
                if st.get("token_eind") != c["token"][-6:]:
                    st = {"token_eind": c["token"][-6:], "offset": 0}
            r = api(c["token"], "getUpdates",
                    {"offset": st.get("offset", 0), "timeout": 25,
                     "allowed_updates": ["message", "callback_query"]}, timeout=40)
            _STATUS.update(actief=True, melding="actief", fout=None)
            for u in r.get("result") or []:
                st["offset"] = u["update_id"] + 1
                _schrijf_offset(st)
                try:
                    if "callback_query" in u:
                        _callback(c, u["callback_query"])
                    elif "message" in u:
                        _bericht(c, u["message"])
                except Exception:
                    print("[journal-bot]", traceback.format_exc())
        except Conflict:
            _STATUS.update(actief=False, melding=(
                "Deze bot wordt al gebruikt door een ander programma (waarschijnlijk de "
                "wachter op de VPS). Maak een aparte bot via @BotFather."))
            time.sleep(60)
        except Exception as e:
            _STATUS.update(actief=False, melding=f"geen verbinding met Telegram ({e})")
            time.sleep(30)


_GESTART = False


def start_achtergrond():
    global _GESTART
    if _GESTART or os.environ.get("CBR_GEEN_MT5"):
        return
    _GESTART = True
    threading.Thread(target=loop, name="journal-bot", daemon=True).start()
