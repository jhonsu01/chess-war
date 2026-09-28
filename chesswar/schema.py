"""Observation -> typed questions. Laya and Jev receive exactly the same request body.

TypeSafe's "speculative fan-out" pattern: ONE request asks which piece to move and, for
every movable piece, where it would go. The questions are answered in parallel without
seeing each other; the code (motor.py) combines them into a single move.

The constraint that drives the design: Laya fits the texts of all options of a question
into a fixed window (`head_max_len`, 192-256 tokens depending on the checkpoint). So each
option is short, and there are three levels of detail that degrade when they do not fit.
"""
from __future__ import annotations

from .observe import NAME, MoveInfo, Observation, amount, state_of

# Character cap for the summed option texts of ONE question.
# ~3.5 characters per token -> ~170 tokens, under the English checkpoint's 192.
# `chess-war probe` checks it against the real server.
OPTION_BUDGET = 600

# Playing criteria. The rules of chess are already enforced by code (only legal moves are
# offered); TypeSafe recommends putting domain rules in `instructions`.
RULES = [
    "Every option is a legal chess move, already checked by the program.",
    "Each option is labeled best, urgent, good, ok, bad or terrible by an exact calculation.",
    "Pick the highest label available: best, then urgent, then good, then ok.",
    "Never pick bad or terrible when an ok or better option exists.",
    "Keep the king home until it castles, unless it is in check.",
]

PLANS = {
    "attack": "go after the rival king or win rival pieces",
    "defend": "protect threatened pieces or the king",
    "develop": "bring pieces into play and castle",
    "simplify": "trade pieces to reach a safe ending",
    "promote": "push a pawn toward promotion",
}


def move_verdict(mi: MoveInfo) -> str:
    """Material verdict of a move: explicit label + consequence, in words.

    Jev reads literally and does not calculate (see "Jev 1.13 jaggedness"); Laya is a
    small encoder that misreads negations. Both get the calculation done, in words.
    """
    if mi.mate:
        return "best, checkmate wins the game"
    if mi.allows_mate:
        return "terrible, rival can checkmate you"
    if mi.stalemate:
        return "bad, stalemate is only a draw"
    o = mi.outcome
    if mi.move.promotion and o >= 0:
        return "good, promotes to a queen"
    if o >= 1:
        return f"good, wins {amount(o)}"
    if mi.stops_mate:
        return "good, stops the mate threat"
    if mi.escapes and o >= 0:
        return "good, saves the attacked piece"
    if o == 0:
        if mi.loses_castling:
            return "bad, king gives up castling"
        return "ok, even trade" if mi.captured else "ok, safe"
    return f"bad, loses {amount(o)}"


def move_text(mi: MoveInfo, level: int) -> str:
    """Text of one destination option. level 0 = full, 2 = minimal."""
    head = "castle" if mi.castle else f"to {mi.dest}"
    if mi.captured and level < 2:
        head += f" taking {NAME[mi.captured]}"
    text = f"{head}: {move_verdict(mi)}"
    if level == 0 and not (mi.mate or mi.allows_mate):
        extras = []
        if mi.check:
            extras.append("check")
        if mi.castle:
            extras.append("king to safety")
        if mi.develops and mi.outcome >= 0:
            extras.append("develops")
        if mi.repetition:
            extras.append("repeats position")
        if extras:
            text += ", " + ", ".join(extras)
    elif level == 1 and mi.check and not mi.mate:
        text += ", check"
    return text


def _fit(build, keys: list) -> dict[str, str]:
    """Use the richest level of detail whose texts fit in OPTION_BUDGET."""
    for level in (0, 1, 2):
        opts = {k: build(k, level) for k in keys}
        if sum(len(v) for v in opts.values()) <= OPTION_BUDGET:
            break
    return opts


def piece_text(obs: Observation, sq: str, level: int) -> str:
    # No piece name: measured with `probe`, the word "king" pulls Laya towards the king
    # (P=0.56 -> 0.09 once removed) whatever its label says. The label already sums it up.
    return f"{sq}: {obs.piece_tags[sq]}"


def build(obs: Observation) -> tuple[dict, dict]:
    """Return (state, questions). Only called when there is more than one legal move."""
    q: dict = {}
    squares = list(obs.by_piece)

    if len(squares) >= 2:
        q["piece"] = {
            "type": "choice",
            "instructions": {
                "task": f"You play {obs.side} in a chess game. Choose which of your pieces to move now; each option is the square it stands on.",
                "rules": RULES,
            },
            "criteria": _fit(lambda sq, lv: piece_text(obs, sq, lv), squares),
        }

    for sq, moves in obs.by_piece.items():
        if len(moves) < 2:
            continue
        by_uci = {m.uci: m for m in moves}
        q[f"move_{sq}"] = {
            "type": "choice",
            "instructions": {
                "task": f"Choose where your {NAME[obs.piece_types[sq]]} on {sq} should move.",
                "rules": RULES,
            },
            "criteria": _fit(lambda u, lv, by_uci=by_uci: move_text(by_uci[u], lv), list(by_uci)),
        }

    q["plan"] = {
        "type": "choice",
        "instructions": "What should your side focus on right now?",
        "criteria": PLANS,
    }
    q["danger"] = {
        "type": "noul",
        "instructions": "Is your king or one of your valuable pieces in danger right now?",
    }
    return state_of(obs), q


def option_chars(questions: dict) -> dict[str, int]:
    """Option characters per question (diagnostics for `probe`)."""
    out = {}
    for qid, spec in questions.items():
        crit = spec.get("criteria")
        if isinstance(crit, dict):
            out[qid] = sum(len(v) for v in crit.values())
    return out
