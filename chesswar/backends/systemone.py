"""Client for `POST /v1/systemone`: TypeSafe's protocol, which laya-serve also speaks.

One persistent connection per player for the whole match, so the measured latency is the
steady-state round trip and not repeated TLS handshakes.
"""
from __future__ import annotations

import time

import httpx

from .base import Backend, Verdict

RETRY_STATUS = (429, 503, 529)


class SystemOneBackend(Backend):
    def __init__(
        self,
        url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 20.0,
        price_per_input_token: float = 0.0,
        retries: int = 3,
    ):
        self.url = url
        self.model = model
        self.price = price_per_input_token
        self.retries = retries
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = httpx.Client(
            timeout=timeout,
            headers=headers,
            limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=120),
        )
        self.spent = 0.0

    def decide(self, state: dict, questions: dict) -> Verdict:
        body = {"model": self.model, "state": state, "questions": questions}
        t0 = time.perf_counter()
        r = None
        for attempt in range(self.retries + 1):
            try:
                r = self.client.post(self.url, json=body)
            except httpx.HTTPError as e:
                if attempt < self.retries:
                    time.sleep(0.4 * 2**attempt)
                    continue
                return self._fail(t0, f"{type(e).__name__}: {e}")
            if r.status_code in RETRY_STATUS and attempt < self.retries:
                wait = r.headers.get("retry-after")
                time.sleep(float(wait) if wait and wait.replace(".", "", 1).isdigit() else 0.4 * 2**attempt)
                continue
            break
        if r.status_code != 200:
            return self._fail(t0, f"HTTP {r.status_code}: {r.text[:200]}")
        try:
            out = r.json()
            answers = out["answers"]
        except (ValueError, KeyError) as e:
            return self._fail(t0, f"invalid response: {e}")
        ms = (time.perf_counter() - t0) * 1000.0
        usage = out.get("usage") or {}
        tok = int(usage.get("input_tokens", 0))
        cost = tok * self.price
        self.spent += cost
        return Verdict(
            answers=answers,
            latency_ms=ms,
            model_ms=_server_ms(r) or r.elapsed.total_seconds() * 1000.0,
            input_tokens=tok,
            output_tokens=int(usage.get("output_tokens", 0)),
            cost_usd=cost,
            served_by=str(out.get("model", "")),
        )

    def _fail(self, t0: float, msg: str) -> Verdict:
        return Verdict({}, (time.perf_counter() - t0) * 1000.0, error=msg[:240])

    def close(self) -> None:
        self.client.close()


def _server_ms(r: httpx.Response) -> float | None:
    """laya-serve publishes X-Inference-Time-Ms and Server-Timing; use them when present."""
    v = r.headers.get("x-inference-time-ms")
    if v:
        try:
            return float(v)
        except ValueError:
            pass
    st = r.headers.get("server-timing", "")
    if "dur=" in st:
        try:
            return float(st.split("dur=")[1].split(",")[0].split(";")[0])
        except ValueError:
            pass
    return None
