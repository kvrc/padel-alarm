import json
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# --- Einstellungen ---
CLUB_ID = "a8b0e7b9-7db0-4c45-8569-28bf775e9208"
DAUER = 90              # Minuten
TAGE_VORAUS = 14
MIT_KALTHALLE = False   # auf True setzen, wenn Padel 7 (Kalthalle) mitgemeldet werden soll
NTFY_KANAL = os.environ["NTFY_KANAL"]

# Wochentag: 0 = Montag, 1 = Dienstag, ... 6 = Sonntag (deutsche Uhrzeit)
ZEITFENSTER = {
    0: [("17:30", "20:30")],
    1: [("17:30", "20:30")],
    2: [("17:30", "20:30")],
    3: [("17:30", "20:30")],
    6: [("09:00", "12:00"), ("17:00", "21:00")],
}

PLATZNAMEN = {
    "543d3cfe-432e-4f5f-8366-ea0ffd1d5f4f": "Padel 1",
    "babbab61-8671-4030-87b2-a9ba26783c44": "Padel 2",
    "117f1e58-e664-4d26-9f27-b2e57140f3c5": "Padel 3",
    "598d0b49-dd20-440b-891d-9f85f73f2cde": "Padel 4",
    "be12a1c7-f9ba-4075-a829-89d94efcdb5f": "Padel 5",
    "2dc18c2f-a0d2-492a-8b18-135501f168ee": "Padel 6",
    "61261925-988f-48cc-ad86-2e53f72df112": "Padel 7 Kalthalle",
}
KALTHALLE = "61261925-988f-48cc-ad86-2e53f72df112"

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
BERLIN = ZoneInfo("Europe/Berlin")
MERKDATEI = Path(__file__).parent / "gesehen.json"
CLUB_LINK = f"https://playtomic.com/tenant/{CLUB_ID}"


def hole_verfuegbarkeit(datum):
    """Holt die freien Slots aller Plätze für ein Datum."""
    url = (
        "https://playtomic.com/api/clubs/availability"
        f"?tenant_id={CLUB_ID}&date={datum}&sport_id=PADEL"
    )
    anfrage = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(anfrage) as antwort:
        return json.load(antwort)


def sende_nachricht(titel, text):
    """Schickt eine Push-Nachricht über ntfy aufs Handy."""
    anfrage = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_KANAL}",
        data=text.encode("utf-8"),
        headers={
            "Title": titel,
            "Tags": "tennis",
            "Click": CLUB_LINK,
        },
    )
    urllib.request.urlopen(anfrage)


def in_ortszeit(datum, uhrzeit):
    """Rechnet Datum + Uhrzeit aus den Playtomic-Daten (UTC) in deutsche Zeit um."""
    utc = datetime.fromisoformat(f"{datum}T{uhrzeit}").replace(tzinfo=timezone.utc)
    return utc.astimezone(BERLIN)


def passt_ins_fenster(uhrzeit, fenster):
    """Prüft, ob eine Uhrzeit in einem der Zeitfenster liegt."""
    for von, bis in fenster:
        if von <= uhrzeit <= bis:
            return True
    return False


def finde_passende_slots():
    """Sammelt alle aktuell freien Slots, die zu den Wünschen passen."""
    jetzt = datetime.now(BERLIN)
    gefunden = {}

    for i in range(TAGE_VORAUS):
        tag = jetzt.date() + timedelta(days=i)
        if tag.weekday() not in ZEITFENSTER:
            continue

        for platz in hole_verfuegbarkeit(tag.isoformat()):
            pid = platz["resource_id"]
            if pid == KALTHALLE and not MIT_KALTHALLE:
                continue
            name = PLATZNAMEN.get(pid, pid[:8])

            for slot in platz["slots"]:
                if slot["duration"] != DAUER:
                    continue
                beginn = in_ortszeit(platz["start_date"], slot["start_time"])
                fenster = ZEITFENSTER.get(beginn.weekday())
                if fenster is None:
                    continue
                uhrzeit = beginn.strftime("%H:%M")
                if not passt_ins_fenster(uhrzeit, fenster):
                    continue
                if beginn <= jetzt:
                    continue  # schon vorbei

                schluessel = f"{beginn:%Y-%m-%d %H:%M} {pid}"
                text = (f"{WOCHENTAGE[beginn.weekday()]} {beginn:%d.%m.} "
                        f"um {uhrzeit} Uhr, {name} ({slot['price']})")
                gefunden[schluessel] = text

        time.sleep(1)

    return gefunden


def lade_gesehene():
    """Liest die Slots vom letzten Lauf. None, wenn es keinen gab."""
    if not MERKDATEI.exists():
        return None
    return set(json.loads(MERKDATEI.read_text()))


def speichere_gesehene(schluessel):
    MERKDATEI.write_text(json.dumps(sorted(schluessel), indent=2))


# --- Hauptprogramm ---
aktuell = finde_passende_slots()
gesehen = lade_gesehene()

if gesehen is None:
    print(f"Erster Lauf: {len(aktuell)} passende Slots gemerkt:")
    for s in sorted(aktuell):
        print("  " + aktuell[s])
    sende_nachricht("Padel-Alarm aktiv",
                    f"Aktuell {len(aktuell)} passende Slots frei. "
                    "Ab jetzt melde ich nur neu frei gewordene.")
else:
    neu = sorted(s for s in aktuell if s not in gesehen)
    if neu:
        zeilen = [aktuell[s] for s in neu]
        print(f"{len(neu)} neu frei gewordene(r) Slot(s):")
        for z in zeilen:
            print("  " + z)
        sende_nachricht(f"{len(neu)} Padel-Slot(s) frei", "\n".join(zeilen))
    else:
        print("Keine neuen Slots.")

speichere_gesehene(aktuell.keys())
