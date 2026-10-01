"""
Automatische back-up (fase 12.1).

Bij elke start van de server wordt de database plus de screenshots-map in een zip
gezet in backups/. Zips ouder dan RETENTIE_DAGEN worden opgeruimd.

Waarom: dit is het enige onderdeel van de journal dat je niet achteraf kunt bouwen.
Een database die weg is, is weg — en met tweehonderd trades erin is dat een jaar werk.
"""

import os
import re
import zipfile
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "cbr_journal.db")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

RETENTIE_DAGEN = 30
MIN_INTERVAL_UUR = 6      # niet vaker dan dit een nieuwe back-up maken
NAAM_RE = re.compile(r"^cbr-backup-(\d{8})-(\d{4})\.zip$")


def _bestaande():
    """Alle back-ups, nieuwste eerst, als (pad, datetime)."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    uit = []
    for naam in os.listdir(BACKUP_DIR):
        m = NAAM_RE.match(naam)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
        except ValueError:
            continue
        uit.append((os.path.join(BACKUP_DIR, naam), ts))
    uit.sort(key=lambda x: x[1], reverse=True)
    return uit


def _opruimen():
    grens = datetime.now() - timedelta(days=RETENTIE_DAGEN)
    bewaard = 0
    for pad, ts in _bestaande():
        if ts >= grens:
            bewaard += 1
            continue
        # altijd minstens drie back-ups houden, hoe oud ook
        if bewaard < 3:
            bewaard += 1
            continue
        try:
            os.remove(pad)
        except OSError:
            pass


def maak_backup(force=False):
    """Maakt een zip van db + screenshots. Geeft het pad terug, of None."""
    if not os.path.exists(DB_PATH):
        return None

    if not force:
        recent = _bestaande()
        if recent and datetime.now() - recent[0][1] < timedelta(hours=MIN_INTERVAL_UUR):
            return None

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stempel = datetime.now().strftime("%Y%m%d-%H%M")
    doel = os.path.join(BACKUP_DIR, f"cbr-backup-{stempel}.zip")

    try:
        with zipfile.ZipFile(doel, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(DB_PATH, "cbr_journal.db")
            if os.path.isdir(SCREENSHOTS_DIR):
                for wortel, _dirs, files in os.walk(SCREENSHOTS_DIR):
                    for f in files:
                        vol = os.path.join(wortel, f)
                        rel = os.path.relpath(vol, BASE_DIR)
                        z.write(vol, rel.replace("\\", "/"))
            z.writestr(
                "LEESMIJ.txt",
                "Automatische back-up van je CBR Trading Journal.\n"
                f"Gemaakt op {datetime.now().strftime('%d-%m-%Y %H:%M')}.\n\n"
                "Terugzetten: pak deze zip uit over de map cbr-journal heen.\n"
                "cbr_journal.db bevat al je trades; de map screenshots je afbeeldingen.\n",
            )
    except OSError:
        return None

    _opruimen()
    return doel


def status():
    """Voor het dashboard: hoeveel back-ups, en hoe oud is de nieuwste."""
    lijst = _bestaande()
    if not lijst:
        return {"aantal": 0, "laatste": None, "uur_geleden": None, "map": BACKUP_DIR}
    pad, ts = lijst[0]
    uur = round((datetime.now() - ts).total_seconds() / 3600, 1)
    return {
        "aantal": len(lijst),
        "laatste": ts.strftime("%d-%m-%Y %H:%M"),
        "uur_geleden": uur,
        "map": BACKUP_DIR,
        "bestand": os.path.basename(pad),
    }


# ---------- dubbele trades ----------

def mogelijke_dubbels(trades):
    """
    Twee trades op dezelfde dag met dezelfde entry-tijd, of met hetzelfde
    resultaat én dezelfde RR, zijn vrijwel altijd één trade die je twee keer
    hebt ingevoerd. Meldt het, verwijdert nooit iets zelf.
    """
    per_dag = {}
    for t in trades:
        per_dag.setdefault(t.get("datum"), []).append(t)

    meldingen = []
    for datum, rij in per_dag.items():
        for i in range(len(rij)):
            for j in range(i + 1, len(rij)):
                a, b = rij[i], rij[j]
                reden = None
                if a.get("tijd_entry") and a.get("tijd_entry") == b.get("tijd_entry"):
                    reden = "zelfde entry-tijd"
                elif (
                    a.get("resultaat_eur") is not None
                    and a.get("resultaat_eur") == b.get("resultaat_eur")
                    and a.get("rr") == b.get("rr")
                    and a.get("richting") == b.get("richting")
                ):
                    reden = "zelfde resultaat, RR en richting"
                if reden:
                    meldingen.append({
                        "datum": datum,
                        "reden": reden,
                        "ids": [a.get("id"), b.get("id")],
                        "tijd": a.get("tijd_entry") or "",
                    })
    return meldingen
