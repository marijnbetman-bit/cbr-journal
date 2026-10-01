# -*- coding: utf-8 -*-
"""
telegram_instellen.py -- koppelt je (nieuwe) journal-bot. Start via
TELEGRAM-BOT-INSTELLEN.bat. Vraagt alleen het token; de rest gaat vanzelf.
"""
import json
import os
import sys
import urllib.error
import urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
CONFIG_PAD = os.path.join(HIER, "journal_config.json")
STANDAARD_CHAT = 1560183106


def api(token, methode, data=None):
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{methode}",
                                 data=json.dumps(data or {}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def main():
    print("""
  JOURNAL-BOT INSTELLEN
  =====================
  Dit is een ANDERE bot dan @CBR_signals_bot (die hoort bij de wachter op
  de VPS; twee programma's kunnen niet naar dezelfde bot luisteren).

  1. Open Telegram, zoek @BotFather en stuur:  /newbot
  2. Naam: bv. "CBR Journal". Gebruikersnaam: moet op 'bot' eindigen,
     bv. marijn_cbr_journal_bot
  3. BotFather geeft je een token (iets als 123456789:AA...).
  4. Open je nieuwe bot en druk op START (anders mag hij jou niet berichten).
""")
    token = input("  Plak hier het token en druk op Enter: ").strip()
    if ":" not in token or len(token) < 30:
        print("\n  [X] Dat lijkt geen token. Kopieer de hele regel uit BotFather.")
        return 1
    try:
        me = api(token, "getMe")["result"]
    except Exception as e:
        print(f"\n  [X] Telegram kent dit token niet ({e}).")
        return 1
    naam = me.get("username", "")
    if naam.lower() == "cbr_signals_bot":
        print("\n  [X] Dit is je SIGNAAL-bot van de VPS. Maak via /newbot een aparte bot.")
        return 1
    print(f"  [v] bot gevonden: @{naam}")

    try:
        with open(CONFIG_PAD, encoding="utf-8") as f:
            cfg = json.load(f)
    except (FileNotFoundError, ValueError):
        cfg = {}
    tg = cfg.get("telegram_journal") or {}
    chat = tg.get("chat_id") or STANDAARD_CHAT
    cfg["telegram_journal"] = {"token": token, "chat_id": chat, "aan": True}
    with open(CONFIG_PAD, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print("  [v] opgeslagen in journal_config.json")

    try:
        api(token, "sendMessage", {"chat_id": chat, "parse_mode": "HTML", "text":
            "✅ <b>Journal-bot gekoppeld.</b>\nElke gesloten trade uit MetaTrader komt hier "
            "binnen met tien knoppen: je 5 checks en je 5 CBR-criteria.\n/help voor meer."})
        print("  [v] testbericht verstuurd -- kijk in Telegram.")
    except urllib.error.HTTPError as e:
        print(f"\n  [!] Testbericht lukte niet ({e.code}). Druk in Telegram op START bij "
              f"@{naam} en draai dit script nog een keer.")
        return 1
    print("\n  Klaar. Draait de journal al? Dan is de bot binnen 30 seconden actief,"
          "\n  zonder herstart.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
