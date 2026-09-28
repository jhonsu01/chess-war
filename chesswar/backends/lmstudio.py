"""LM Studio (optional): a generative LLM answering the SAME typed questions.

A "System Two" third player: the same state and questions are sent as JSON and the output
is constrained with a JSON Schema (one key per question, an enum of its options). It gives
no probabilities, so every answer counts as probability 1.
"""
from __future__ import annotations

import json
import os
import time

import httpx

from .base import Backend, Verdict

SYSTEM = (
    "You make fast decisions for a chess-playing program. You receive a game state and a set "
    "of questions. Answer every question by picking exactly one of its option keys "
    "(or true/false for yes/no questions). Reply with JSON only."
)


def _schema(questions: dict) -> dict:
    props, required = {}, []
    for qid, spec in questions.items():
        kind = spec["type"]
        if kind == "choice":
            props[qid] = {"type": "string", "enum": list(spec["criteria"])}
        elif kind == "noul":
            props[qid] = {"type": "boolean"}
        else:
            props[qid] = {"type": "integer", "minimum": 0, "maximum": len(spec["criteria"]) - 1}
        required.append(qid)
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


class LMStudioBackend(Backend):
    name = "lmstudio"
    label = "LM STUDIO"
    colour = "#b48cff"

    def __init__(self, url: str | None = None, model: str | None = None, api_key: str | None = None, timeout: float = 120.0):
        self.base = (url or os.environ.get("LMSTUDIO_URL", "http://localhost:1234/v1")).rstrip("/")
        self.model = model or os.environ.get("LMSTUDIO_MODEL", "")
        key = api_key or os.environ.get("LMSTUDIO_API_KEY", "")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        self.client = httpx.Client(timeout=timeout, headers=headers)
        self.detail = f"{self.model or '?'} · LM Studio"

    def health(self) -> str | None:
        if not self.model:
            return "Missing LMSTUDIO_MODEL in .env"
        try:
            r = self.client.get(f"{self.base}/models")
        except httpx.HTTPError as e:
            return f"LM Studio unreachable at {self.base}: {e}"
        if r.status_code == 401:
            return "LM Studio requires authentication (401): set LMSTUDIO_API_KEY in .env"
        if r.status_code != 200:
            return f"LM Studio answered HTTP {r.status_code}"
        ids = [m.get("id") for m in r.json().get("data", [])]
        if self.model not in ids:
            return f"LM Studio does not serve '{self.model}'. Available: {', '.join(ids[:8])}"
        return None

    def decide(self, state: dict, questions: dict) -> Verdict:
        prompt = {
            "state": state,
            "questions": {
                qid: {"instructions": s["instructions"], **({"options": s["criteria"]} if "criteria" in s else {})}
                for qid, s in questions.items()
            },
        }
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "decisions", "strict": True, "schema": _schema(questions)},
            },
        }
        t0 = time.perf_counter()
        try:
            r = self.client.post(f"{self.base}/chat/completions", json=body)
            r.raise_for_status()
            out = r.json()
            raw = json.loads(out["choices"][0]["message"]["content"])
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as e:
            return Verdict({}, (time.perf_counter() - t0) * 1000.0, error=f"{type(e).__name__}: {e}"[:240])
        ms = (time.perf_counter() - t0) * 1000.0
        answers = {}
        for qid, spec in questions.items():
            if qid not in raw:
                continue
            v = raw[qid]
            if spec["type"] == "choice" and v in spec["criteria"]:
                answers[qid] = {"type": "choice", "choice": v, "probabilities": {v: 1.0}, "confidence": None}
            elif spec["type"] == "noul":
                answers[qid] = {"type": "noul", "noul": 1.0 if v else 0.0, "confidence": None}
        usage = out.get("usage") or {}
        return Verdict(
            answers=answers,
            latency_ms=ms,
            model_ms=ms,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            served_by=self.model,
        )

    def close(self) -> None:
        self.client.close()
