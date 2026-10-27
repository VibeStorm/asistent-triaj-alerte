from datetime import datetime

import pytest

from asistent_triaj import generate_data as gd
from asistent_triaj.db import SecurityEvent, make_session_factory
from asistent_triaj.tools import ToolError, count_failures, search_events, top_ips

NOW = datetime(2026, 1, 15, 12, 0, 0)


@pytest.fixture()
def session():
    factory = make_session_factory("sqlite://")  # bază în memorie, dispare după test
    with factory() as s:
        gd.populate(s, NOW, seed=1)
        yield s


def test_data_is_reproducible_and_synthetic():
    a = [(e.timestamp, e.username, e.source_ip) for e in gd.generate_events(NOW, seed=7)]
    b = [(e.timestamp, e.username, e.source_ip) for e in gd.generate_events(NOW, seed=7)]
    assert a == b
    assert all(e.source_ip.startswith(("192.0.2.", "198.51.100.", "203.0.113."))
               for e in gd.generate_events(NOW, seed=7))


def test_top_ips_finds_bruteforce_first(session):
    res = top_ips(session, NOW, hours=24)["results"]
    assert res[0]["source_ip"] == gd.BRUTE_FORCE_IP
    assert res[0]["events"] == 300
    assert res[0]["distinct_users"] == 1


def test_old_attack_excluded_from_24h_but_visible_in_72h(session):
    ips_24 = {r["source_ip"] for r in top_ips(session, NOW, hours=24, limit=50)["results"]}
    ips_72 = {r["source_ip"] for r in top_ips(session, NOW, hours=72, limit=50)["results"]}
    assert gd.OLD_ATTACK_IP not in ips_24
    assert gd.OLD_ATTACK_IP in ips_72


def test_spraying_ip_hits_many_users(session):
    res = top_ips(session, NOW, hours=24, limit=50)["results"]
    spray = next(r for r in res if r["source_ip"] == gd.SPRAY_IP)
    assert spray["events"] == 30 and spray["distinct_users"] == 10


def test_count_failures_by_user(session):
    res = count_failures(session, NOW, group_by="user", hours=24)["results"]
    assert res[0] == {"user": "administrator", "failures": 300}


def test_search_events_filters_and_limit(session):
    res = search_events(session, NOW, hours=24, event_id=4624, source_ip=gd.BRUTE_FORCE_IP)
    assert res["total_matching"] == 1  # login-ul reușit după atac
    res = search_events(session, NOW, hours=24, event_id=4625, source_ip=gd.BRUTE_FORCE_IP, limit=5)
    assert res["total_matching"] == 300 and res["returned"] == 5
    stamps = [e["timestamp"] for e in res["events"]]
    assert stamps == sorted(stamps, reverse=True)


def test_future_events_ignored(session):
    session.add(SecurityEvent(timestamp=datetime(2026, 1, 16), event_id=4625, username="x",
                              source_ip="192.0.2.99", workstation="WS", logon_type=3))
    session.commit()
    ips = {r["source_ip"] for r in top_ips(session, NOW, hours=24, limit=50)["results"]}
    assert "192.0.2.99" not in ips


@pytest.mark.parametrize("call", [
    lambda s: top_ips(s, NOW, hours=0),
    lambda s: top_ips(s, NOW, hours=24, limit=1000),
    lambda s: top_ips(s, NOW, event_id=4688),
    lambda s: count_failures(s, NOW, group_by="password"),
    lambda s: search_events(s, NOW, hours="24"),
])
def test_invalid_parameters_raise_toolerror(session, call):
    with pytest.raises(ToolError):
        call(session)


def test_sql_injection_attempt_is_just_a_value(session):
    res = search_events(session, NOW, username="x' OR '1'='1")
    assert res["total_matching"] == 0
