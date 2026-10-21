# -*- coding: utf-8 -*-
"""
Haalt weg wat de journal schreef terwijl er een DEMO-account aan MT5 hing
(bv. 20 okt 2026 op Marijns pc: saldo schoot naar ~10k).

Hoe hij de demo-periode vindt: in mt5_account_log staan de saldo's die de
journal las. Je live-account staat rond de paar honderd euro; alles met een
saldo vanaf --drempel (standaard 1000) komt van een ander account. Van de
eerste tot de laatste zo'n meting (plus een marge, en hooguit tot de volgende
normale meting) is de 'demo-periode'. Alles wat de MT5-koppeling in die periode
schreef gaat weg:

  mt5_account_log      metingen met saldo >= drempel
  kasstromen           bron 'mt5' aangemaakt in de periode + de aansluitingsregels
                       van die dagen (worden bij de volgende live-ronde opnieuw berekend)
  trades               bron 'live' aangemaakt in de periode (+ screenshots-rijen,
                       mt5_verwerkt, Telegram-koppelingen, v3-trade-berichten)
  mt5_posities / mt5_positie_events / mt5_orders van die posities / uit die periode

Met de hand gelogde trades, oordelen, labels en notities blijven staan.

Gebruik (in de journal-map, journal eerst afsluiten):
    python herstel_demo_vervuiling.py            # alleen laten zien wat weg zou gaan
    python herstel_demo_vervuiling.py --echt     # eerst een back-up, dan weghalen

Daarna de journal weer starten met MT5 ingelogd op 1705040: trades van je
live-account in die periode komen dan vanzelf opnieuw binnen.
"""
import argparse, os, shutil, sqlite3, sys
from datetime import datetime, timedelta, timezone

HIER = os.path.dirname(os.path.abspath(__file__))
MARGE = timedelta(minutes=10)


def lokaal_naar_utc(ts):
    """mt5_account_log.ts is lokale tijd; created_at is UTC (sqlite)."""
    return datetime.fromisoformat(ts).astimezone(timezone.utc).replace(tzinfo=None)


def tabel_bestaat(con, naam):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (naam,)).fetchone() is not None


def zoek(con, drempel):
    rijen = con.execute("SELECT ts, balance FROM mt5_account_log ORDER BY ts").fetchall()
    hoog = [r for r in rijen if r[1] is not None and r[1] >= drempel]
    if not hoog:
        return None
    eerste, laatste = hoog[0][0], hoog[-1][0]
    na = [r[0] for r in rijen if r[0] > laatste and r[1] < drempel]
    voor = [r[0] for r in rijen if r[0] < eerste and r[1] < drempel]
    van = datetime.fromisoformat(eerste) - MARGE
    if voor:
        van = max(van, datetime.fromisoformat(voor[-1]) + timedelta(seconds=1))
    tot = (datetime.fromisoformat(na[0]) - timedelta(seconds=1) if na
           else max(datetime.now(), datetime.fromisoformat(laatste) + MARGE))
    plan = {"van": van, "tot": tot, "hoog": len(hoog),
            "max_saldo": max(r[1] for r in hoog)}
    van_s, tot_s = van.isoformat(timespec="seconds"), tot.isoformat(timespec="seconds")
    van_u = lokaal_naar_utc(van_s).strftime("%Y-%m-%d %H:%M:%S")
    tot_u = lokaal_naar_utc(tot_s).strftime("%Y-%m-%d %H:%M:%S")
    dagen = sorted({(van + timedelta(days=i)).date().isoformat()
                    for i in range((tot.date() - van.date()).days + 1)})

    plan["trades"] = con.execute(
        "SELECT id, datum, tijd_entry, richting, resultaat_eur, positie_id FROM trades "
        "WHERE bron='live' AND created_at BETWEEN ? AND ?", (van_u, tot_u)).fetchall()
    tids = [t[0] for t in plan["trades"]]
    pids = [t[5] for t in plan["trades"] if t[5]]
    plan["kasstromen"] = con.execute(
        "SELECT id, datum, soort, bedrag, notitie FROM kasstromen WHERE "
        "(bron='mt5' AND created_at BETWEEN ? AND ?) OR sleutel IN (%s)"
        % ",".join("?" * len(dagen)),
        [van_u, tot_u] + [f"aansluiting-{d}" for d in dagen]).fetchall()
    plan["account_log"] = [r for r in hoog]
    plan["posities"] = con.execute(
        "SELECT positie_id FROM mt5_posities WHERE eerst_gezien BETWEEN ? AND ?",
        (van_s, tot_s)).fetchall()
    pids = sorted(set(pids) | {p[0] for p in plan["posities"]})
    plan["pids"], plan["tids"] = pids, tids
    plan["events"] = con.execute(
        "SELECT COUNT(*) FROM mt5_positie_events WHERE positie_id IN (%s) OR ts BETWEEN ? AND ?"
        % ",".join("?" * len(pids) or "NULL"), pids + [van_s, tot_s]).fetchone()[0] \
        if pids else con.execute("SELECT COUNT(*) FROM mt5_positie_events WHERE ts BETWEEN ? AND ?",
                                 (van_s, tot_s)).fetchone()[0]
    plan["van_s"], plan["tot_s"], plan["van_u"], plan["tot_u"] = van_s, tot_s, van_u, tot_u
    plan["drempel"] = drempel
    return plan


def toon(plan):
    print(f"Demo-periode: {plan['van_s']} t/m {plan['tot_s']} (lokale tijd)")
    print(f"  {plan['hoog']} saldo-metingen >= {plan['drempel']:.0f} (hoogste {plan['max_saldo']:.2f})")
    print(f"  {len(plan['trades'])} trades van MT5:")
    for t in plan["trades"][:40]:
        print(f"     #{t[0]} {t[1]} {t[2]} {t[3]} {t[4]:+.2f}")
    if len(plan["trades"]) > 40:
        print(f"     ... en nog {len(plan['trades']) - 40}")
    print(f"  {len(plan['kasstromen'])} kasstromen:")
    for k in plan["kasstromen"]:
        print(f"     #{k[0]} {k[1]} {k[2]} {k[3]:+.2f}  {k[4][:60]}")
    print(f"  {len(plan['pids'])} MT5-posities, {plan['events']} positie-events")


def voer_uit(con, plan):
    q = lambda xs: ",".join("?" * len(xs)) or "NULL"
    tids, pids = plan["tids"], plan["pids"]
    con.execute("DELETE FROM mt5_account_log WHERE balance >= ?", (plan["drempel"],))
    if plan["kasstromen"]:
        ids = [k[0] for k in plan["kasstromen"]]
        con.execute(f"DELETE FROM kasstromen WHERE id IN ({q(ids)})", ids)
    if tids:
        con.execute(f"DELETE FROM screenshots WHERE trade_id IN ({q(tids)})", tids)
        con.execute(f"DELETE FROM mt5_verwerkt WHERE trade_id IN ({q(tids)})", tids)
        if tabel_bestaat(con, "journal_bot_berichten"):
            con.execute(f"DELETE FROM journal_bot_berichten WHERE trade_id IN ({q(tids)})", tids)
        if tabel_bestaat(con, "v3_berichten"):
            con.execute(f"DELETE FROM v3_berichten WHERE soort='trade' AND ref IN ({q(tids)})",
                        [str(t) for t in tids])
        if tabel_bestaat(con, "signalen"):
            con.execute(f"UPDATE signalen SET trade_id=NULL, genomen=0 WHERE trade_id IN ({q(tids)})", tids)
        con.execute(f"DELETE FROM trades WHERE id IN ({q(tids)})", tids)
    if pids:
        con.execute(f"DELETE FROM mt5_verwerkt WHERE positie_id IN ({q(pids)})", pids)
        con.execute(f"DELETE FROM mt5_posities WHERE positie_id IN ({q(pids)})", pids)
        con.execute(f"DELETE FROM mt5_positie_events WHERE positie_id IN ({q(pids)})", pids)
    con.execute("DELETE FROM mt5_positie_events WHERE ts BETWEEN ? AND ?",
                (plan["van_s"], plan["tot_s"]))
    if tabel_bestaat(con, "mt5_orders"):
        # niet-gevulde orders hebben geen positie; geplaatst is Amsterdamse tijd (minuten)
        con.execute("DELETE FROM mt5_orders WHERE geplaatst BETWEEN ? AND ?",
                    (plan["van_s"][:16].replace("T", " "), plan["tot_s"][:16].replace("T", " ")))
    con.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(HIER, "cbr_journal.db"))
    ap.add_argument("--drempel", type=float, default=1000.0,
                    help="saldo vanaf hier = niet je live-account (standaard 1000)")
    ap.add_argument("--echt", action="store_true", help="echt weghalen (anders alleen tonen)")
    a = ap.parse_args()
    con = sqlite3.connect(a.db)
    plan = zoek(con, a.drempel)
    if plan is None:
        print(f"Geen saldo-metingen >= {a.drempel:.0f} gevonden: geen demo-vervuiling te zien.")
        return 0
    toon(plan)
    if not a.echt:
        print("\nNiets veranderd. Klopt dit? Sluit de journal en draai met --echt.")
        return 0
    con.close()
    map_ = os.path.join(os.path.dirname(os.path.abspath(a.db)), "backups")
    os.makedirs(map_, exist_ok=True)
    kopie = os.path.join(map_, f"cbr_journal-voor-demo-herstel-{datetime.now():%Y%m%d-%H%M%S}.db")
    shutil.copy2(a.db, kopie)
    print(f"\nBack-up: {kopie}")
    con = sqlite3.connect(a.db)
    voer_uit(con, plan)
    con.close()
    print("Klaar. Start de journal met MT5 ingelogd op 1705040; je live-trades komen vanzelf terug.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
