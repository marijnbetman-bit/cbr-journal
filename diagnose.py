# -*- coding: utf-8 -*-
"""diagnose.py -- waarom praten MT5 en Telegram niet met de journal? Schrijft diagnose.txt."""
import json, os, socket, ssl, subprocess, sys, urllib.request, traceback
HIER = os.path.dirname(os.path.abspath(__file__))
os.chdir(HIER)
regels = []
def p(*a):
    s = " ".join(str(x) for x in a); print(s); regels.append(s)

p("== OMGEVING ==")
p("python:", sys.version.split()[0], sys.executable)
p("map:", HIER)
try:
    import ctypes; p("administrator:", bool(ctypes.windll.shell32.IsUserAnAdmin()))
except Exception as e: p("administrator: ?", e)
for f, merk in (("journal_bot.py", "truststore"), ("mt5_koppeling.py", "schijfletter"), ("app/saldo.py", "kasstromen")):
    try: p(f, "nieuwe versie" if merk in open(f, encoding="utf-8").read() else "OUDE VERSIE")
    except Exception as e: p(f, "ontbreekt", e)
for mod in ("truststore", "certifi", "MetaTrader5", "fpdf", "fastapi"):
    try: m = __import__(mod); p("pakket", mod, "OK", getattr(m, "__version__", ""))
    except Exception as e: p("pakket", mod, "ONTBREEKT", e)

cfg = json.load(open("journal_config.json", encoding="utf-8"))
tg = cfg.get("telegram_journal") or {}
p("config terminal_pad:", repr((cfg.get("mt5") or {}).get("terminal_pad")))
p("config telegram aan:", tg.get("aan"), "token:", (tg.get("token") or "")[:6] + "…", "chat:", tg.get("chat_id"))
try:
    out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    p("poort 8010 in gebruik:", ":8010" in out)
except Exception: pass
try:
    out = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    p("draaiende MT5-terminals:", [l.split()[0] for l in out.splitlines() if "terminal" in l.lower()])
    p("aantal python-processen:", sum(1 for l in out.splitlines() if l.lower().startswith("python")))
except Exception: pass

p("\n== TELEGRAM ==")
url = f"https://api.telegram.org/bot{tg.get('token')}/getMe"
def probeer(naam, ctx):
    try:
        with urllib.request.urlopen(url, timeout=15, context=ctx) as r:
            p(naam, "OK ->", json.loads(r.read())["result"].get("username"))
    except Exception as e: p(naam, "FOUT:", str(e)[:200])
probeer("standaard     :", ssl.create_default_context())
try:
    import truststore; probeer("windows-certs :", truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
except Exception as e: p("windows-certs : niet te testen", e)
try:
    import certifi; probeer("certifi       :", ssl.create_default_context(cafile=certifi.where()))
except Exception as e: p("certifi       : niet te testen", e)
try:
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection(("api.telegram.org", 443), timeout=10) as s:
        with ctx.wrap_socket(s, server_hostname="api.telegram.org") as t:
            der = t.getpeercert(binary_form=True)
    import hashlib
    p("certificaat ontvangen, sha1:", hashlib.sha1(der).hexdigest()[:20])
    try:
        from cryptography import x509
        c = x509.load_der_x509_certificate(der); p("uitgever:", c.issuer.rfc4514_string())
    except Exception:
        txt = der.decode("latin-1", "ignore")
        for merk in ("Avast", "AVG", "Kaspersky", "ESET", "Bitdefender", "Fortinet", "Sophos", "Norton", "Zscaler", "Go Daddy", "Starfield", "DigiCert"):
            if merk in txt: p("uitgever bevat:", merk)
except Exception as e: p("certificaat ophalen FOUT:", e)

p("\n== MT5 ==")
try:
    import MetaTrader5 as mt5
    pad = ((cfg.get("mt5") or {}).get("terminal_pad") or "").strip()
    if pad:
        ok = mt5.initialize(pad); p("initialize(pad):", ok, mt5.last_error()); mt5.shutdown()
    ok = mt5.initialize(); p("initialize():", ok, mt5.last_error())
    if ok:
        a = mt5.account_info(); t = mt5.terminal_info()
        p("account:", a.login if a else None, a.server if a else None, "balans", a.balance if a else None)
        p("terminal:", t.path if t else None, "verbonden:", t.connected if t else None)
        mt5.shutdown()
except Exception:
    p(traceback.format_exc())

open("diagnose.txt", "w", encoding="utf-8").write("\n".join(regels))
p("\nKlaar -> diagnose.txt")
