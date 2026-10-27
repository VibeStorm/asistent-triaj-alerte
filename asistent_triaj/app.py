"""Aplicația Flask: pagina HTML (Jinja) + API REST.

  GET  /            pagina cu formularul
  POST /            trimiterea formularului (răspunsul apare pe aceeași pagină)
  POST /api/ask     API JSON: {"question": "...", "simulated": false}
  GET  /api/health  verificare că serverul rulează

Pornire (doar local): python -m asistent_triaj.app
"""
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

from asistent_triaj.agent import AgentError, LLMClient, run_agent
from asistent_triaj.db import DEFAULT_DB_URL, make_session_factory
from asistent_triaj.fake_llm import FakeLLM

MAX_QUESTION_CHARS = 500

EXAMPLE_QUESTIONS = [
    "Ce IP-uri au încercat cele mai multe autentificări eșuate în ultimele 24h?",
    "Analizează activitatea de la IP-ul 203.0.113.50 și spune-mi dacă e un incident.",
    "Ce utilizatori au cele mai multe autentificări eșuate?",
    "Ce a făcut IP-ul 198.51.100.23 în ultimele 24 de ore?",
]


def default_llm_factory(simulated: bool) -> LLMClient:
    if simulated:
        return FakeLLM()
    from asistent_triaj.groq_llm import GroqLLM  # importat aici: testele nu au nevoie de cheie

    return GroqLLM()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def create_app(db_url: str = DEFAULT_DB_URL, llm_factory=default_llm_factory, now_fn=utc_now) -> Flask:
    """`llm_factory` și `now_fn` se pot înlocui în teste (LLM simulat, oră fixă)."""
    app = Flask(__name__)
    sessions = make_session_factory(db_url)

    def answer(question: str, simulated: bool) -> dict:
        with sessions() as session:
            return run_agent(question, session, now_fn(), llm_factory(simulated))

    def check_question(value) -> tuple[str | None, str | None]:
        """Întoarce (întrebare curățată, mesaj de eroare)."""
        if not isinstance(value, str) or not value.strip():
            return None, "Scrie o întrebare."
        value = value.strip()
        if len(value) > MAX_QUESTION_CHARS:
            return None, f"Întrebarea e prea lungă (maxim {MAX_QUESTION_CHARS} de caractere)."
        return value, None

    @app.get("/")
    def index():
        return render_template("index.html", examples=EXAMPLE_QUESTIONS, question="",
                               simulated=False, result=None, error=None)

    @app.post("/")
    def index_post():
        question, error = check_question(request.form.get("question"))
        simulated = request.form.get("simulated") == "on"
        result = None
        if error is None:
            try:
                result = answer(question, simulated)
            except AgentError as exc:
                error = str(exc)
        return render_template("index.html", examples=EXAMPLE_QUESTIONS, question=question or "",
                               simulated=simulated, result=result, error=error)

    @app.post("/api/ask")
    def api_ask():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error="Trimite un obiect JSON cu cheia 'question'."), 400
        question, error = check_question(body.get("question"))
        if error:
            return jsonify(error=error), 400
        try:
            result = answer(question, body.get("simulated") is True)
        except AgentError as exc:
            return jsonify(error=str(exc)), 502
        return jsonify(result)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    return app


if __name__ == "__main__":
    # implicit doar local (127.0.0.1 nu e accesibil din rețea); debug oprit intenționat.
    # ASISTENT_HOST=0.0.0.0 se setează doar în Dockerfile.
    create_app().run(host=os.getenv("ASISTENT_HOST", "127.0.0.1"), port=5000, debug=False)
