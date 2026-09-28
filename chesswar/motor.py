"""Typed answers -> a move, with a deterministic shield that blocks unsound moves.

As in doom-war, the shield does not play for the model: it only vetoes what code knows is
a mistake (allowing mate in one, giving away material, throwing a won position into a
draw) and replaces it with the next move the model ITSELF found most likely.
Every correction is counted and published as OVERRIDDEN %.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

import chess

from .observe import MoveInfo, Observation


@dataclass
class Decision:
    move: chess.Move
    uci: str
    san: str
    raw_uci: str | None = None
    raw_san: str | None = None
    overridden: bool = False
    reason: str | None = None
    fallback: bool = False
    forced: bool = False
    joint: dict[str, float] = field(default_factory=dict)
    p_move: float | None = None
    piece_conf: float | None = None
    move_conf: float | None = None
    plan: str | None = None
    danger: float | None = None


def _probs(answer: dict | None) -> dict[str, float] | None:
    if not answer:
        return None
    p = answer.get("probabilities")
    if isinstance(p, dict) and p:
        return {str(k): float(v) for k, v in p.items()}
    c = answer.get("choice")
    return {str(c): 1.0} if c is not None else None


def joint_probs(obs: Observation, answers: dict) -> dict[str, float]:
    """P(move) = P(piece) * P(destination | piece), over every legal move."""
    squares = list(obs.by_piece)
    piece_p = {squares[0]: 1.0} if len(squares) == 1 else _probs(answers.get("piece"))
    if not piece_p:
        return {}
    joint: dict[str, float] = {}
    for sq, moves in obs.by_piece.items():
        pp = piece_p.get(sq, 0.0)
        if len(moves) == 1:
            mp = {moves[0].uci: 1.0}
        else:
            mp = _probs(answers.get(f"move_{sq}")) or {m.uci: 1.0 / len(moves) for m in moves}
        for m in moves:
            joint[m.uci] = pp * mp.get(m.uci, 0.0)
    return joint


def raw_choice(obs: Observation, answers: dict, joint: dict[str, float] | None = None) -> str | None:
    """The move the model finds most likely: argmax of P(piece) * P(destination | piece).

    Picking the piece first and then its destination (greedy decoding) favours pieces
    whose probability is spread over many moves; measured with `probe`, joint decoding
    is right more often for both models.
    """
    joint = joint if joint is not None else joint_probs(obs, answers)
    if not joint or max(joint.values()) <= 0:
        return None
    return max(joint, key=joint.get)


def unsound(mi: MoveInfo, obs: Observation) -> str | None:
    if mi.allows_mate:
        return "allows mate in one"
    if mi.outcome <= -2:
        return "gives away material"
    ahead = obs.material[0] - obs.material[1]
    if ahead >= 2 and (mi.repetition or mi.stalemate):
        return "throws a won position into a draw"
    return None


def resolve(obs: Observation, answers: dict, shield: bool = True, rng: random.Random | None = None) -> Decision:
    rng = rng or random.Random(0)
    joint = joint_probs(obs, answers)
    raw = raw_choice(obs, answers, joint)
    by_uci = {m.uci: m for m in obs.moves}

    fallback = raw is None
    if fallback:
        # no usable answer (network error, missing question): a random sound move
        sound = [m for m in obs.moves if unsound(m, obs) is None] or obs.moves
        chosen = rng.choice(sound)
    else:
        chosen = by_uci[raw]

    reason = None
    if shield and not fallback:
        reason = unsound(chosen, obs)
        if reason:
            alts = [m for m in obs.moves if unsound(m, obs) is None]
            if alts:
                chosen = max(alts, key=lambda m: (joint.get(m.uci, 0.0), m.outcome))
            else:
                reason = None  # every move is bad: keep the model's own choice

    raw_mi = by_uci.get(raw) if raw else None
    piece_sq = chess.square_name(chosen.move.from_square)
    plan = answers.get("plan") or {}
    danger = answers.get("danger") or {}
    return Decision(
        move=chosen.move,
        uci=chosen.uci,
        san=chosen.san,
        raw_uci=raw,
        raw_san=raw_mi.san if raw_mi else None,
        overridden=reason is not None,
        reason=reason,
        fallback=fallback,
        joint=joint,
        p_move=joint.get(chosen.uci),
        piece_conf=_conf(answers.get("piece")),
        move_conf=_conf(answers.get(f"move_{piece_sq}")),
        plan=plan.get("choice"),
        danger=danger.get("noul"),
    )


def forced(obs: Observation) -> Decision:
    """A single legal move: nobody is asked (same for both players)."""
    m = obs.moves[0]
    return Decision(move=m.move, uci=m.uci, san=m.san, raw_uci=m.uci, raw_san=m.san, forced=True, joint={m.uci: 1.0}, p_move=1.0)


def _conf(answer: dict | None) -> float | None:
    if not answer:
        return None
    c = answer.get("confidence")
    return float(c) if isinstance(c, (int, float)) else None


def top_moves(obs: Observation, joint: dict[str, float], n: int = 3) -> list[list]:
    """The model's n most likely moves, for the viewer."""
    san = {m.uci: m.san for m in obs.moves}
    best = sorted(joint.items(), key=lambda kv: -kv[1])[:n]
    return [[san[u], round(p, 4)] for u, p in best if u in san]
