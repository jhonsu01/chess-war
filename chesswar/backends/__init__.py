from __future__ import annotations

from .base import Backend, Verdict

PLAYERS = ("laya", "jev", "lmstudio", "random")


def make(name: str, seed: int = 7, laya_checkpoint: str | None = None) -> Backend:
    if name == "laya":
        from .laya import LayaBackend

        return LayaBackend(checkpoint=laya_checkpoint)
    if name == "jev":
        from .jev import JevBackend

        return JevBackend()
    if name == "lmstudio":
        from .lmstudio import LMStudioBackend

        return LMStudioBackend()
    if name == "random":
        from .baseline import RandomBackend

        return RandomBackend(seed)
    raise ValueError(f"unknown player: {name} (use {', '.join(PLAYERS)})")


__all__ = ["Backend", "Verdict", "PLAYERS", "make"]
