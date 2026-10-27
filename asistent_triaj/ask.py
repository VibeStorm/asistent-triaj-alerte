"""Întrebare din linia de comandă: python -m asistent_triaj.ask "întrebarea ta" [--fake]"""
import argparse
import sys
from datetime import datetime, timezone

from asistent_triaj.agent import AgentError, run_agent
from asistent_triaj.db import make_session_factory
from asistent_triaj.fake_llm import FakeLLM


def main() -> int:
    parser = argparse.ArgumentParser(description="Pune o întrebare asistentului de triaj.")
    parser.add_argument("question")
    parser.add_argument("--fake", action="store_true", help="folosește LLM-ul simulat (fără Groq)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        if args.fake:
            llm = FakeLLM()
        else:
            from asistent_triaj.groq_llm import GroqLLM
            llm = GroqLLM()
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        with make_session_factory()() as session:
            result = run_agent(args.question, session, now, llm)
    except AgentError as exc:
        print(f"Eroare: {exc}")
        return 1

    for step in result["steps"]:
        print(f"[tool] {step['tool']} {step['arguments']}")
    print()
    print(result["answer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
