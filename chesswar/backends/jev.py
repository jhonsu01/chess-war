"""Jev: TypeSafe's hosted System One model (jev-1.13)."""
from __future__ import annotations

import os
import pathlib

import httpx

from .systemone import SystemOneBackend

BASE = "https://api.typesafe.ai/v1"
PRICE_PER_INPUT_TOKEN = 0.042 / 1_000_000  # $0.042 / MTok; output tokens are free


def read_key(explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    env = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if env:
        return env
    for c in ("jev.txt", "../jev.txt"):
        p = pathlib.Path(c)
        if p.is_file() and p.read_text(encoding="utf-8").strip():
            return p.read_text(encoding="utf-8").strip()
    raise RuntimeError("Missing Jev key: set TYPESAFE_API_KEY in .env (or create jev.txt)")


class JevBackend(SystemOneBackend):
    name = "jev"
    label = "JEV"
    colour = "#ff7a3c"

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 20.0):
        model = model or os.environ.get("JEV_MODEL", "jev-latest")
        super().__init__(
            f"{BASE}/systemone",
            model=model,
            api_key=read_key(api_key),
            timeout=timeout,
            price_per_input_token=PRICE_PER_INPUT_TOKEN,
        )
        self.detail = f"{model} · TypeSafe API"

    def health(self) -> str | None:
        try:
            r = self.client.get(f"{BASE}/models")
        except httpx.HTTPError as e:
            return f"Jev unreachable: {e}"
        if r.status_code == 401:
            return "Jev rejected the key (401): check TYPESAFE_API_KEY in .env"
        if r.status_code != 200:
            return f"Jev answered HTTP {r.status_code}: {r.text[:120]}"
        return None
