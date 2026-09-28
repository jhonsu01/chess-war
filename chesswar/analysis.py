"""Objective quality of every decision with Stockfish (optional, after each game).

Measures the centipawn loss (CPL) of the move the model chose (raw, before the shield)
and of the move actually played, so each model's judgment is not hidden by the shield's
corrections. Without Stockfish this step is skipped and the match runs the same.
"""
from __future__ import annotations

import os
import shutil

import chess
import chess.engine

MATE = 10_000
CAP = 1_000  # losing more than 10 pawns already means "lost game": clip it


def find_stockfish(explicit: str | None = None) -> str | None:
    for c in (explicit, os.environ.get("STOCKFISH_PATH"), shutil.which("stockfish"), "/usr/games/stockfish"):
        if c and os.path.isfile(c):
            return c
    return None


class Analyzer:
    def __init__(self, path: str, depth: int = 12):
        self.engine = chess.engine.SimpleEngine.popen_uci(path)
        self.limit = chess.engine.Limit(depth=depth)
        self.name = self.engine.id.get("name", "stockfish")

    def _eval(self, board: chess.Board, pov: chess.Color) -> int:
        info = self.engine.analyse(board, self.limit)
        return info["score"].pov(pov).score(mate_score=MATE)

    def cpl(self, fen: str, ucis: list[str]) -> dict[str, int]:
        """Loss (>= 0) of each move against the best one, from the side to move."""
        board = chess.Board(fen)
        pov = board.turn
        best = self._eval(board, pov)
        out = {}
        for u in dict.fromkeys(ucis):
            b = board.copy(stack=False)
            b.push(chess.Move.from_uci(u))
            if b.is_checkmate():
                val = MATE
            elif b.is_game_over():
                val = 0
            else:
                val = self._eval(b, pov)
            out[u] = min(CAP, max(0, best - val))
        return out

    def close(self) -> None:
        try:
            self.engine.quit()
        except Exception:
            pass
