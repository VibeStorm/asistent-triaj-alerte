"""Generator de loguri Windows SINTETICE (4624/4625).

Toate adresele IP vin din intervalele rezervate pentru documentație (RFC 5737), iar
utilizatorii sunt inventați. Același `seed` produce mereu aceleași date.
"""
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from asistent_triaj.db import SecurityEvent

USERS = ["ana.pop", "bogdan.ionescu", "carmen.stan", "dan.radu", "elena.matei",
         "florin.dobre", "gabriela.tudor", "horia.lungu", "irina.neagu", "jenica.vlad"]
INTERNAL_IPS = [f"192.0.2.{n}" for n in range(10, 40)]
WORKSTATIONS = ["WS-CONTAB-01", "WS-HR-02", "WS-IT-03", "SRV-FILE-01", "SRV-DC-01"]

# Scenariile "ascunse" din date; testele și întrebările de demo se bazează pe ele.
BRUTE_FORCE_IP = "203.0.113.50"   # multe parole pe contul "administrator", ultimele ~6h; apoi un login reușit
SPRAY_IP = "198.51.100.23"        # 3 încercări pe fiecare utilizator, ultimele ~24h
OLD_ATTACK_IP = "203.0.113.99"    # atac vechi (acum ~40h): trebuie să iasă din fereastra de 24h
LOCKOUT_USER = "dan.radu"         # utilizator legitim care greșește parola de pe IP intern


def _event(ts, event_id, username, ip, rng, logon_type=None) -> SecurityEvent:
    return SecurityEvent(
        timestamp=ts, event_id=event_id, username=username, source_ip=ip,
        workstation=rng.choice(WORKSTATIONS),
        logon_type=logon_type if logon_type is not None else rng.choice([2, 3, 10]),
    )


def generate_events(now: datetime, seed: int = 42) -> list[SecurityEvent]:
    """Întoarce evenimentele din ultimele 48h față de `now`."""
    rng = random.Random(seed)
    events: list[SecurityEvent] = []

    # 1) trafic normal: login-uri reușite și câteva parole greșite din greșeală
    for _ in range(1500):
        ts = now - timedelta(seconds=rng.randint(0, 48 * 3600))
        user = rng.choice(USERS)
        ip = rng.choice(INTERNAL_IPS)
        events.append(_event(ts, 4625 if rng.random() < 0.04 else 4624, user, ip, rng))

    # 2) brute-force: o adresă, un cont, multe încercări, apoi succes
    start = now - timedelta(hours=6)
    for i in range(300):
        ts = start + timedelta(seconds=i * 60)
        events.append(_event(ts, 4625, "administrator", BRUTE_FORCE_IP, rng, logon_type=10))
    events.append(_event(start + timedelta(seconds=300 * 60 + 30), 4624,
                         "administrator", BRUTE_FORCE_IP, rng, logon_type=10))

    # 3) password spraying: puține încercări pe mulți utilizatori
    start = now - timedelta(hours=20)
    for user in USERS:
        for k in range(3):
            ts = start + timedelta(minutes=rng.randint(0, 600))
            events.append(_event(ts, 4625, user, SPRAY_IP, rng, logon_type=3))

    # 4) atac vechi, în afara ferestrei de 24h
    start = now - timedelta(hours=40)
    for i in range(80):
        events.append(_event(start + timedelta(seconds=i * 45), 4625,
                             "administrator", OLD_ATTACK_IP, rng, logon_type=10))

    # 5) fals pozitiv: un utilizator real își blochează contul
    start = now - timedelta(hours=3)
    for i in range(12):
        events.append(_event(start + timedelta(seconds=i * 20), 4625,
                             LOCKOUT_USER, "192.0.2.15", rng, logon_type=2))

    events.sort(key=lambda e: e.timestamp)
    return events


def populate(session: Session, now: datetime, seed: int = 42) -> int:
    """Șterge evenimentele vechi și inserează unele noi. Întoarce numărul inserat."""
    session.query(SecurityEvent).delete()
    events = generate_events(now, seed)
    session.add_all(events)
    session.commit()
    return len(events)


if __name__ == "__main__":
    from asistent_triaj.db import make_session_factory

    Session_ = make_session_factory()
    with Session_() as s:
        n = populate(s, datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0))
    print(f"Am inserat {n} evenimente sintetice în events.db")
