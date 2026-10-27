import json
from datetime import datetime

import pytest

from asistent_triaj import generate_data as gd
from asistent_triaj.agent import AgentError, TOOL_SCHEMAS, run_agent, run_tool
from asistent_triaj.db import make_session_factory
from asistent_triaj.fake_llm import FakeLLM
from asistent_triaj.tools import TOOLS

NOW = datetime(2026, 1, 15, 12, 0, 0)


@pytest.fixture()
def session():
    factory = make_session_factory("sqlite://")
    with factory() as s:
        gd.populate(s, NOW, seed=1)
        yield s


class ScriptedLLM:
    """Întoarce pe rând răspunsurile primite; reține mesajele văzute (ca să le verificăm)."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def chat(self, messages, tools):
        self.seen.append(list(messages))
        return self.replies.pop(0)


def tool_call(name, arguments, call_id="c1"):
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {"content": None, "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": raw}}]}


def test_schemas_match_the_real_tools():
    assert {s["function"]["name"] for s in TOOL_SCHEMAS} == set(TOOLS)


def test_fake_llm_top_ips_question(session):
    out = run_agent("Ce IP-uri au încercat cele mai multe autentificări eșuate în ultimele 24h?",
                    session, NOW, FakeLLM())
    assert [s["tool"] for s in out["steps"]] == ["top_ips"]
    assert gd.BRUTE_FORCE_IP in out["answer"] and "300" in out["answer"]


def test_fake_llm_user_question_uses_count_failures(session):
    out = run_agent("Ce utilizatori au cele mai multe eșecuri?", session, NOW, FakeLLM())
    assert out["steps"][0]["tool"] == "count_failures"
    assert "administrator" in out["answer"]


def test_fake_llm_ip_question_uses_search_events(session):
    out = run_agent(f"Ce a făcut {gd.BRUTE_FORCE_IP} în ultimele 24 ore?", session, NOW, FakeLLM())
    assert out["steps"][0]["tool"] == "search_events"
    assert out["steps"][0]["result"]["total_matching"] == 301  # 300 eșecuri + 1 login reușit


def test_answer_without_tool_is_returned_directly(session):
    llm = ScriptedLLM([{"content": "  Salut!  ", "tool_calls": None}])
    assert run_agent("Bună", session, NOW, llm) == {"answer": "Salut!", "steps": []}


def test_tool_result_is_sent_back_to_llm(session):
    llm = ScriptedLLM([tool_call("top_ips", {"hours": 24, "event_id": 4625}),
                       {"content": "gata", "tool_calls": None}])
    run_agent("q", session, NOW, llm)
    last = llm.seen[1][-1]
    assert last["role"] == "tool" and last["tool_call_id"] == "c1"
    assert gd.BRUTE_FORCE_IP in last["content"]


@pytest.mark.parametrize("name,args", [
    ("drop_tables", "{}"),                          # tool inexistent
    ("top_ips", "nu e json"),                       # JSON stricat
    ("top_ips", "[1, 2]"),                          # nu e obiect
    ("top_ips", '{"hours": 100000}'),               # valoare în afara limitelor
    ("top_ips", '{"sql": "DROP TABLE security_events"}'),  # parametru inexistent
    ("count_failures", '{"group_by": "password"}'), # valoare nepermisă
])
def test_bad_tool_calls_become_errors_not_crashes(session, name, args):
    assert "error" in run_tool(session, NOW, name, args)


def test_llm_can_recover_after_a_tool_error(session):
    llm = ScriptedLLM([tool_call("top_ips", {"hours": 99999}),
                       tool_call("top_ips", {"hours": 24}, call_id="c2"),
                       {"content": "ok", "tool_calls": None}])
    out = run_agent("q", session, NOW, llm)
    assert "error" in out["steps"][0]["result"] and "results" in out["steps"][1]["result"]
    assert out["answer"] == "ok"


def test_agent_stops_after_max_steps(session):
    llm = ScriptedLLM([tool_call("top_ips", {}) for _ in range(10)])
    with pytest.raises(AgentError):
        run_agent("q", session, NOW, llm, max_steps=3)


def test_agent_cannot_override_session_or_time(session):
    # `now` și `session` sunt ale noastre: LLM-ul nu le poate trimite ca argumente
    assert "error" in run_tool(session, NOW, "top_ips", '{"now": "2020-01-01T00:00:00"}')


def test_groq_client_requires_key(monkeypatch):
    from asistent_triaj import groq_llm

    monkeypatch.setattr(groq_llm, "load_dotenv", lambda: None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(AgentError):
        groq_llm.GroqLLM()
