from datetime import datetime

import pytest

from asistent_triaj import generate_data as gd
from asistent_triaj.agent import AgentError
from asistent_triaj.app import MAX_QUESTION_CHARS, create_app
from asistent_triaj.fake_llm import FakeLLM

NOW = datetime(2026, 1, 15, 12, 0, 0)
QUESTION = "Ce IP-uri au încercat cele mai multe autentificări eșuate în ultimele 24h?"


class EvilLLM:
    """Un „model" care răspunde cu HTML periculos: pagina trebuie să-l afișeze ca text."""

    def chat(self, messages, tools):
        return {"content": "<script>alert(1)</script>", "tool_calls": None}


@pytest.fixture()
def client(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'test.db'}"  # fișier temporar, nu events.db
    app = create_app(db_url, llm_factory=lambda simulated: FakeLLM(), now_fn=lambda: NOW)
    from asistent_triaj.db import make_session_factory

    with make_session_factory(db_url)() as s:
        gd.populate(s, NOW, seed=1)
    return app.test_client()


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_index_page_shows_examples(client):
    html = client.get("/").get_data(as_text=True)
    assert "Asistent de triaj" in html and "sintetice" in html and "203.0.113.50" in html


def test_api_ask_returns_answer_and_steps(client):
    res = client.post("/api/ask", json={"question": QUESTION})
    body = res.get_json()
    assert res.status_code == 200
    assert body["steps"][0]["tool"] == "top_ips"
    assert gd.BRUTE_FORCE_IP in body["answer"]


def test_form_post_renders_answer_and_steps(client):
    html = client.post("/", data={"question": QUESTION, "simulated": "on"}).get_data(as_text=True)
    assert gd.BRUTE_FORCE_IP in html and "top_ips" in html


@pytest.mark.parametrize("payload", [
    {}, {"question": ""}, {"question": "   "}, {"question": 123},
    {"question": "x" * (MAX_QUESTION_CHARS + 1)},
])
def test_api_rejects_bad_questions(client, payload):
    res = client.post("/api/ask", json=payload)
    assert res.status_code == 400 and "error" in res.get_json()


def test_api_rejects_non_json(client):
    assert client.post("/api/ask", data="salut").status_code == 400


def test_llm_html_is_escaped_in_page(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 't.db'}", llm_factory=lambda s: EvilLLM(), now_fn=lambda: NOW)
    html = app.test_client().post("/", data={"question": "orice"}).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_llm_failure_gives_502_in_api_and_message_in_page(tmp_path):
    def broken(simulated):
        raise AgentError("Lipsește GROQ_API_KEY.")

    app = create_app(f"sqlite:///{tmp_path / 't.db'}", llm_factory=broken, now_fn=lambda: NOW)
    c = app.test_client()
    assert c.post("/api/ask", json={"question": "q"}).status_code == 502
    assert "Lipsește GROQ_API_KEY" in c.post("/", data={"question": "q"}).get_data(as_text=True)
