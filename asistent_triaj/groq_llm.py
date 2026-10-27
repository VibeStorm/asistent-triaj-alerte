"""Clientul Groq real. Cheia și modelul vin din .env (niciodată din cod)."""
import os

from dotenv import load_dotenv
from groq import Groq, GroqError

from asistent_triaj.agent import AgentError

DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        load_dotenv()
        api_key = api_key or os.getenv("GROQ_API_KEY")
        if not api_key or api_key.startswith("pune_aici"):
            raise AgentError("Lipsește GROQ_API_KEY. Completeaz-o în fișierul .env.")
        self.model = model or os.getenv("GROQ_MODEL") or DEFAULT_MODEL
        self._client = Groq(api_key=api_key, timeout=30.0)

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        try:
            response = self._client.chat.completions.create(
                model=self.model, messages=messages, tools=tools,
                tool_choice="auto", temperature=0,
            )
        except GroqError as exc:
            # mesajul excepției nu conține cheia; îl afișăm ca să se vadă cauza (limită, rețea etc.)
            raise AgentError(f"Apelul către Groq a eșuat: {exc}") from exc
        message = response.choices[0].message
        tool_calls = [
            {"id": c.id, "type": "function",
             "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in (message.tool_calls or [])
        ]
        return {"content": message.content, "tool_calls": tool_calls or None}
