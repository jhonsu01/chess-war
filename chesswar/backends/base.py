from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Verdict:
    """A model's answer for one turn, with its measured cost."""

    answers: dict
    latency_ms: float          # full round trip: what the chess clock is charged
    model_ms: float = 0.0      # inference time reported by the server, when it reports it
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    served_by: str = ""        # model id that answered (e.g. jev-1.13.0)


class Backend:
    name = "base"
    label = "base"
    colour = "#ffffff"
    detail = ""

    def decide(self, state: dict, questions: dict) -> Verdict:
        raise NotImplementedError

    def health(self) -> str | None:
        """None when ready; otherwise a human-readable error."""
        return None

    def meta(self) -> dict:
        return {"name": self.name, "label": self.label, "colour": self.colour, "detail": self.detail}

    def close(self) -> None:
        pass
