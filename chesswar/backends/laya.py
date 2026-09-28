"""Laya: open-weights System One model (Apache 2.0), served locally by laya-serve.

laya-serve speaks the same protocol as Jev, so Laya receives the same body byte for byte.
The `model` field picks the checkpoint (english | multilingual | typed-decisions).
"""
from __future__ import annotations

import os

import httpx

from .systemone import SystemOneBackend

CHECKPOINTS = {
    "english": "laya · ModernBERT-large 421M",
    "multilingual": "laya-multilingual · mmBERT 322M",
    "typed-decisions": "laya-typed-decisions · 421M",
}


class LayaBackend(SystemOneBackend):
    name = "laya"
    label = "LAYA"
    colour = "#36c5f0"

    def __init__(self, url: str | None = None, checkpoint: str | None = None, timeout: float = 30.0):
        self.base = (url or os.environ.get("LAYA_URL", "http://localhost:8000")).rstrip("/")
        self.checkpoint = checkpoint or os.environ.get("LAYA_CHECKPOINT", "typed-decisions")
        if self.checkpoint not in CHECKPOINTS:
            raise ValueError(f"unknown Laya checkpoint: {self.checkpoint} (use {', '.join(CHECKPOINTS)})")
        super().__init__(f"{self.base}/v1/systemone", model=self.checkpoint, timeout=timeout)
        self.detail = f"{CHECKPOINTS[self.checkpoint]} · local"

    def health(self) -> str | None:
        try:
            r = self.client.get(f"{self.base}/health")
        except httpx.HTTPError as e:
            return f"Laya is not answering at {self.base} ({type(e).__name__}). Did you run `docker compose up -d --wait laya`?"
        if r.status_code != 200:
            return f"Laya /health answered HTTP {r.status_code}"
        info = r.json()
        loaded = info.get("loaded", [])
        if loaded and self.checkpoint not in loaded:
            return f"Laya has not loaded '{self.checkpoint}' (loaded: {loaded}). Set LAYA_MODELS."
        self.detail = f"{CHECKPOINTS[self.checkpoint]} · local {info.get('device', '?')}"
        return None
