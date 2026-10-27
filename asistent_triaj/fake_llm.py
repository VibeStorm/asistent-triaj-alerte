"""LLM SIMULAT pentru teste: rulează fără cheie și fără internet.

Nu „înțelege" nimic: alege tool-ul după cuvinte-cheie, apoi formulează răspunsul din rezultat.
Scopul e să testăm bucla agentului (apel de tool, validare, erori), nu calitatea unui model real.
"""
import json
import re
from itertools import count


class FakeLLM:
    def __init__(self):
        self._ids = count(1)

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        last = messages[-1]
        if last["role"] == "tool":
            return {"content": self._summarize(messages), "tool_calls": None}
        name, args = self._choose(last["content"].lower())
        return {"content": None, "tool_calls": [{
            "id": f"fake_{next(self._ids)}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}]}

    @staticmethod
    def _choose(question: str) -> tuple[str, dict]:
        match = re.search(r"(\d+)\s*(h|ore|ora)\b", question)
        hours = int(match.group(1)) if match else 24
        ip = re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", question)
        if ip:
            return "search_events", {"hours": hours, "source_ip": ip.group(), "limit": 5}
        if "utilizator" in question or "cont" in question:
            return "count_failures", {"group_by": "user", "hours": hours}
        return "top_ips", {"hours": hours, "event_id": 4625}

    @staticmethod
    def _summarize(messages: list[dict]) -> str:
        result = json.loads(messages[-1]["content"])
        if "error" in result:
            return f"Nu am putut obține datele: {result['error']}"
        rows = result.get("results")
        if rows is not None:
            if not rows:
                return "Nu am găsit rezultate în intervalul cerut."
            top = rows[0]
            label = top.get("source_ip") or top.get("ip") or top.get("user")
            count_ = top.get("events") or top.get("failures")
            return f"Primul loc: {label} cu {count_} evenimente (rezumat simulat)."
        return f"Am găsit {result.get('total_matching', 0)} evenimente potrivite (rezumat simulat)."
