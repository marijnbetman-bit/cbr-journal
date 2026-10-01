# -*- coding: utf-8 -*-
"""
mt5_check.py -- kijkt of de MT5-koppeling kan werken. Verandert NIETS.
Start via MT5-CHECK.bat.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)
import mt5_koppeling as mk   # noqa: E402

V, X, I = "[v]", "[X]", "[i]"


def main(mt5=None, db_pad=None):
    print("\n  MT5-CHECK  (leest alleen, verandert niets)\n  " + "=" * 44)
    cfg = mk.lees_config()
    print(f"{I} instellingen: vanaf {cfg['sync_vanaf']}, elke {cfg['interval_sec']} s, "
          f"symbool {cfg['symbool']}, {'AAN' if cfg.get('aan', True) else 'UIT'}")
    if mt5 is None:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            print(f"{X} Het MetaTrader5-pakket ontbreekt. Start START-JOURNAL.bat één keer, "
                  "die installeert het.")
            return 1
    print(f"{V} MetaTrader5-pakket {getattr(mt5, '__version__', '')}")

    pad = (cfg.get("terminal_pad") or "").strip()
    if not (mt5.initialize(pad) if pad else mt5.initialize()):
        print(f"{X} MetaTrader 5 niet bereikbaar: {mt5.last_error()}")
        print("    -> Open MetaTrader 5 op deze laptop en log in bij Vantage.")
        print("    -> Meerdere MT5's geïnstalleerd? Zet het pad naar terminal64.exe in")
        print('       journal_config.json bij "mt5" -> "terminal_pad".')
        return 1
    acc, ti = mt5.account_info(), mt5.terminal_info()
    if acc is None:
        print(f"{X} MT5 draait, maar er is geen account ingelogd.")
        return 1
    print(f"{V} ingelogd: account …{str(acc.login)[-3:]} op {acc.server} ({acc.currency})")
    if ti is not None:
        print(f"{V if ti.connected else X} verbinding met de broker: "
              f"{'ja' if ti.connected else 'NEE -- check je internet / login'}")

    offset = None
    for sym in [cfg.get("symbool"), "XAUUSD+", "XAUUSD"]:
        if not sym:
            continue
        mt5.symbol_select(sym, True)
        tick = mt5.symbol_info_tick(sym)
        if tick is not None:
            offset = mk.detecteer_offset(tick.time, time.time())
            if offset is not None:
                print(f"{V} serverklok: UTC{offset:+d} (automatisch bepaald via {sym})")
                break
    if offset is None:
        offset = int(cfg.get("broker_offset_uur", 3))
        print(f"{I} serverklok niet live te bepalen (markt dicht?) -> config: UTC{offset:+d}")

    open_ = [p for p in (mt5.positions_get() or ()) if cfg["symbool_bevat"].upper() in p.symbol.upper()]
    print(f"{I} open goud-posities nu: {len(open_)}")

    van = datetime.now(timezone.utc) - timedelta(days=14)
    deals = mt5.history_deals_get(van, datetime.now(timezone.utc) + timedelta(days=2)) or ()
    pos = [p for p in mk.groepeer([mk._deal_dict(d) for d in deals]).values()
           if p["gesloten"] and cfg["symbool_bevat"].upper() in (p["symbool"] or "").upper()]
    pos.sort(key=lambda p: p["open_ts"])
    print(f"\n  Gesloten goud-trades, laatste 14 dagen ({len(pos)}):")
    con = mk.verbind_db(db_pad)
    try:
        tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        verwerkt = {}
        if "mt5_verwerkt" in tabellen:
            verwerkt = {r[0]: r[1] for r in con.execute("SELECT positie_id, trade_id FROM mt5_verwerkt")}
        vanaf = datetime.fromisoformat(cfg["sync_vanaf"]).date()
        for p in pos[-15:]:
            t = mk.server_naar_amsterdam(p["open_ts"], offset)
            reden = mk.REDEN_TEKST.get(p["reden"], "gesloten")
            if p["positie_id"] in verwerkt:
                st = f"in journal (#{verwerkt[p['positie_id']]})"
            elif t.date() < vanaf:
                st = "voor sync_vanaf, blijft buiten"
            else:
                st = "komt erin bij de volgende ronde"
            print(f"    {t:%d-%m %H:%M}  {p['richting']:5}  {p['bruto']:+7.2f}  "
                  f"charges {p['charges']:+.2f}  {reden:18}  {st}")
    finally:
        con.close()
    mt5.shutdown()

    try:
        with open(mk.CONFIG_PAD, encoding="utf-8") as f:
            tg = json.load(f).get("telegram_journal") or {}
    except (FileNotFoundError, ValueError):
        tg = {}
    if tg.get("token"):
        print(f"\n{V} Telegram journal-bot ingesteld (chat {tg.get('chat_id')})")
    else:
        print(f"\n{I} Telegram journal-bot nog niet ingesteld -> TELEGRAM-BOT-INSTELLEN.bat")
    print("\n  Alles groen? Dan pakt de journal je trades vanzelf op zolang hij draait.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
