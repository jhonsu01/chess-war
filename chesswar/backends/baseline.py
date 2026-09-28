"""Reference player with no model: spreads probability at random (seeded).

Useful to test the arena without a GPU or an API key, and as a floor for comparison.
"""
from __future__ import annotations

import random
import time

from .base import Backend, Verdict


class RandomBackend(Backend):
    name = "random"
    label = "RANDOM"
    colour = "#9aa0a6"
    detail = "uniform random · baseline"

    def __init__(self, seed: int = 7):
        self.rng = random.Random(seed)

    def decide(self, state: dict, questions: dict) -> Verdict:
        t0 = time.perf_counter()
        answers = {}
        for qid, spec in questions.items():
            if spec["type"] == "choice":
                keys = list(spec["criteria"])
                w = [self.rng.random() for _ in keys]
                s = sum(w)
                probs = {k: x / s for k, x in zip(keys, w)}
                answers[qid] = {"type": "choice", "choice": max(probs, key=probs.get), "probabilities": probs, "confidence": 0.0}
            elif spec["type"] == "noul":
                answers[qid] = {"type": "noul", "noul": self.rng.random(), "confidence": 0.0}
        return Verdict(answers, (time.perf_counter() - t0) * 1000.0)
