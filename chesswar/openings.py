"""Starting openings.

Laya and Jev are deterministic (the most likely move is played), so from the initial
position they would repeat the same game. Every opening is played twice with colours
swapped, so neither side gets a colour or line advantage.
"""
from __future__ import annotations

import chess

OPENINGS = [
    ("Italian", "e4 e5 Nf3 Nc6 Bc4 Bc5"),
    ("Sicilian", "e4 c5 Nf3 d6"),
    ("Queen's Gambit", "d4 d5 c4 e6"),
    ("French", "e4 e6 d4 d5"),
    ("Caro-Kann", "e4 c6 d4 d5"),
    ("King's Indian", "d4 Nf6 c4 g6"),
    ("English", "c4 e5 Nc3 Nf6"),
    ("Ruy Lopez", "e4 e5 Nf3 Nc6 Bb5 a6"),
    ("Scandinavian", "e4 d5 exd5 Qxd5"),
    ("London", "d4 d5 Bf4 Nf6"),
]


def moves_of(line: str) -> list[chess.Move]:
    board = chess.Board()
    out = []
    for san in line.split():
        m = board.parse_san(san)
        out.append(m)
        board.push(m)
    return out


def schedule(games: int) -> list[tuple[str, str, bool]]:
    """[(name, line, p1_plays_white)] with colours alternating in pairs."""
    plan = []
    for i in range(games):
        name, line = OPENINGS[(i // 2) % len(OPENINGS)]
        plan.append((name, line, i % 2 == 0))
    return plan
