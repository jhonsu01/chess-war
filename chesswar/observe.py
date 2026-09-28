"""Board -> tactical facts. Every calculation lives here, in code.

Neither Laya nor Jev calculates variations: they are System One models that pick among
options described in natural language. This module turns the position into those
descriptions ("good, wins a rook", "terrible, rival can checkmate you") with a static
exchange evaluation (SEE) two plies deep. Both models receive exactly the same text.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import chess

VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}
# The king as an attacker: it can never be recaptured (that would be illegal), so it
# goes last in an exchange.
_KING_ATTACKER = 100

NAME = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


def _attacker_value(piece_type: int) -> int:
    return _KING_ATTACKER if piece_type == chess.KING else VALUE[piece_type]


def _exchange(board: chess.Board, square: int, target: int, depth: int = 0) -> int:
    """Material the side to move wins by capturing on `square` (0 if it should not)."""
    if depth > 12:
        return 0
    best = None
    for m in board.generate_legal_moves(to_mask=chess.BB_SQUARES[square]):
        if m.promotion not in (None, chess.QUEEN):
            continue
        key = _attacker_value(board.piece_type_at(m.from_square))
        if best is None or key < best[0]:
            best = (key, m)
    if best is None:
        return 0
    attacker, m = best
    promo = VALUE[m.promotion] - 1 if m.promotion else 0
    board.push(m)
    gain = target + promo - _exchange(board, square, attacker + promo, depth + 1)
    board.pop()
    return max(0, gain)


def see(board: chess.Board, move: chess.Move) -> int:
    """Net material of `move` for the side playing it, assuming best recaptures."""
    if board.is_en_passant(move):
        captured = 1
    else:
        pt = board.piece_type_at(move.to_square)
        captured = VALUE[pt] if pt else 0
    promo = VALUE[move.promotion] - 1 if move.promotion else 0
    mover = _attacker_value(board.piece_type_at(move.from_square)) + promo
    board.push(move)
    loss = _exchange(board, move.to_square, mover)
    board.pop()
    return captured + promo - loss


def best_capture(board: chess.Board, exclude: int | None = None) -> tuple[int, chess.Move | None]:
    """The most profitable capture for the side to move: (gain >= 0, move).

    `exclude` skips a square whose exchange was already counted elsewhere.
    """
    best, best_move = 0, None
    for m in board.generate_legal_captures():
        if m.promotion not in (None, chess.QUEEN) or m.to_square == exclude:
            continue
        g = see(board, m)
        if g > best:
            best, best_move = g, m
    return best, best_move


def _mate_in_one(board: chess.Board) -> bool:
    """The side to move has mate in one."""
    for m in board.legal_moves:
        if board.gives_check(m):
            board.push(m)
            mate = board.is_checkmate()
            board.pop()
            if mate:
                return True
    return False


def mate_threat(board: chess.Board) -> bool:
    """If the side to move passed, would the rival have mate in one?"""
    if board.is_check():
        return False
    b = board.copy(stack=False)
    b.push(chess.Move.null())
    return _mate_in_one(b)


def en_prise(board: chess.Board, color: chess.Color) -> dict[int, int]:
    """Pieces of `color` the rival could win if it were its move: {square: gain}."""
    if board.is_check():
        return {}
    b = board.copy(stack=False)
    b.turn = not color
    b.ep_square = None
    out: dict[int, int] = {}
    for m in b.generate_legal_captures():
        if m.promotion not in (None, chess.QUEEN):
            continue
        target = b.piece_at(m.to_square)
        if target is None or target.color != color:
            continue
        g = see(b, m)
        if g > 0 and g > out.get(m.to_square, 0):
            out[m.to_square] = g
    return out


@dataclass
class MoveInfo:
    move: chess.Move
    uci: str
    san: str
    piece: int
    captured: int | None
    gain: int            # immediate SEE
    risk: int            # what the rival wins by capturing right after
    check: bool
    mate: bool
    allows_mate: bool
    stalemate: bool
    castle: bool
    develops: bool
    escapes: bool
    repetition: bool
    loses_castling: bool = False
    stops_mate: bool = False   # the rival threatened mate in one and this move stops it

    @property
    def outcome(self) -> int:
        """Estimated material balance two plies deep."""
        return self.gain - self.risk

    @property
    def dest(self) -> str:
        return chess.square_name(self.move.to_square)

    @property
    def unsound(self) -> bool:
        return self.allows_mate or self.outcome <= -2


@dataclass
class Observation:
    color: chess.Color
    fullmove: int
    phase: str
    material: tuple[int, int]
    in_check: bool
    king: str
    last_move: str | None
    threats: list[str]
    chances: list[str]
    moves: list[MoveInfo]
    by_piece: dict[str, list[MoveInfo]] = field(default_factory=dict)
    piece_tags: dict[str, str] = field(default_factory=dict)
    piece_types: dict[str, int] = field(default_factory=dict)

    @property
    def side(self) -> str:
        return "white" if self.color == chess.WHITE else "black"

    def info(self, uci: str) -> MoveInfo | None:
        for m in self.moves:
            if m.uci == uci:
                return m
        return None


def material(board: chess.Board, color: chess.Color) -> int:
    return sum(VALUE[p.piece_type] for p in board.piece_map().values() if p.color == color)


def _phase(board: chess.Board) -> str:
    heavy = sum(
        VALUE[p.piece_type]
        for p in board.piece_map().values()
        if p.piece_type not in (chess.PAWN, chess.KING)
    )
    if heavy <= 26 or (not board.pieces(chess.QUEEN, True) and not board.pieces(chess.QUEEN, False) and heavy <= 30):
        return "endgame"
    if board.fullmove_number <= 10:
        return "opening"
    return "middlegame"


def amount(n: int) -> str:
    """Material amount in words (both models read words better than numbers)."""
    n = abs(n)
    if n <= 1:
        return "a pawn"
    if n == 2:
        return "two pawns"
    if n <= 4:
        return "a piece"
    if n <= 7:
        return "a rook"
    return "the queen"


def _material_text(diff: int) -> str:
    if diff == 0:
        return "material is equal"
    side = "ahead" if diff > 0 else "behind"
    return f"you are {side} by {amount(diff)}"


def _king_text(board: chess.Board, color: chess.Color) -> str:
    if board.is_check():
        return "your king is in check"
    k = board.king(color)
    home = chess.BB_RANK_1 if color == chess.WHITE else chess.BB_RANK_8
    if k is not None and chess.BB_SQUARES[k] & home and chess.square_file(k) in (0, 1, 2, 6, 7):
        return "your king is sheltered on the wing"
    if board.has_castling_rights(color):
        return "your king has not castled yet"
    return "your king is exposed"


def _last_move_text(board: chess.Board) -> str | None:
    if not board.move_stack:
        return None
    b = board.copy()
    m = b.pop()
    p = b.piece_at(m.from_square)
    text = f"the rival moved a {NAME[p.piece_type]} from {chess.square_name(m.from_square)} to {chess.square_name(m.to_square)}"
    if b.is_capture(m):
        cap = chess.PAWN if b.is_en_passant(m) else b.piece_type_at(m.to_square)
        text += f", taking your {NAME[cap]}"
    if b.gives_check(m):
        text += ", giving check"
    return text


def _tag(moves: list[MoveInfo], hanging: bool, piece: int) -> str:
    """Summary of the best thing a piece can do, with an explicit label.

    The labels (best/urgent/good/ok/bad) paraphrase the material calculation: small
    encoders misread negations ("should stay home") but read a direct label well.
    Both models receive the same text.
    """
    if any(m.mate for m in moves):
        return "best: can checkmate now"
    safe = [m for m in moves if not m.unsound]
    if any(m.stops_mate for m in safe):
        return "urgent: can stop the mate threat"
    if any(m.move.promotion for m in safe):
        return "good: can promote to a queen"
    wins = [m for m in safe if m.outcome >= 1]
    if wins:
        return f"good: can win {amount(max(m.outcome for m in wins))}"
    if hanging and any(m.escapes for m in safe):
        return "urgent: under attack, can escape"
    if not safe:
        return "bad: every move loses material" if not any(m.allows_mate for m in moves) else "bad: every move is a blunder"
    if piece == chess.KING and all(m.loses_castling for m in safe):
        return "bad: moving it gives up castling"
    if any(m.castle for m in safe):
        return "ok: can castle"
    if any(m.check for m in safe):
        return "ok: can give check safely"
    if any(m.develops for m in safe):
        return "ok: can develop"
    return "ok: can step aside" if piece == chess.KING else "ok: has safe moves"


def observe(board: chess.Board) -> Observation:
    color = board.turn
    work = board.copy()
    hanging = en_prise(board, color)
    threatened = mate_threat(board)
    opening = board.fullmove_number <= 15
    back_rank = chess.BB_RANK_1 if color == chess.WHITE else chess.BB_RANK_8

    moves: list[MoveInfo] = []
    for m in board.legal_moves:
        if m.promotion not in (None, chess.QUEEN):
            continue  # underpromotions: noise for a decision model
        piece = board.piece_type_at(m.from_square)
        captured = None
        if board.is_capture(m):
            captured = chess.PAWN if board.is_en_passant(m) else board.piece_type_at(m.to_square)
        gain = see(board, m)
        check = board.gives_check(m)
        castle = board.is_castling(m)

        work.push(m)
        mate = work.is_checkmate()
        stalemate = work.is_stalemate()
        if mate or stalemate:
            risk, allows_mate = 0, False
        else:
            # the exchange on the destination square is already inside `gain`
            risk, _ = best_capture(work, exclude=m.to_square)
            allows_mate = _mate_in_one(work)
        repetition = work.is_repetition(3)
        work.pop()

        moves.append(
            MoveInfo(
                move=m,
                uci=m.uci(),
                san=board.san(m),
                piece=piece,
                captured=captured,
                gain=gain,
                risk=risk,
                check=check,
                mate=mate,
                allows_mate=allows_mate,
                stalemate=stalemate,
                castle=castle,
                develops=opening
                and piece in (chess.KNIGHT, chess.BISHOP)
                and bool(chess.BB_SQUARES[m.from_square] & back_rank),
                escapes=m.from_square in hanging,
                repetition=repetition,
                loses_castling=piece == chess.KING and not castle and board.has_castling_rights(color),
                stops_mate=threatened and not allows_mate and not mate,
            )
        )

    by_piece: dict[str, list[MoveInfo]] = {}
    types: dict[str, int] = {}
    for mi in sorted(moves, key=lambda x: (x.move.from_square, x.move.to_square)):
        sq = chess.square_name(mi.move.from_square)
        by_piece.setdefault(sq, []).append(mi)
        types[sq] = mi.piece
    tags = {
        sq: _tag(ms, chess.parse_square(sq) in hanging, types[sq]) for sq, ms in by_piece.items()
    }

    threats = [
        f"your {NAME[board.piece_type_at(sq)]} on {chess.square_name(sq)} can be won by the rival"
        for sq, _ in sorted(hanging.items(), key=lambda kv: -kv[1])
    ][:3]
    chances = []
    for mi in sorted(moves, key=lambda x: -x.outcome):
        if mi.mate:
            chances.insert(0, "you can checkmate the rival king now")
        elif mi.captured and mi.outcome >= 1 and len(chances) < 3:
            txt = f"the rival {NAME[mi.captured]} on {mi.dest} can be won"
            if txt not in chances:
                chances.append(txt)
    if threatened:
        threats.insert(0, "the rival threatens checkmate next move")
    if board.is_check():
        threats.insert(0, "your king is in check and must be saved")

    me, rival = material(board, color), material(board, not color)
    return Observation(
        color=color,
        fullmove=board.fullmove_number,
        phase=_phase(board),
        material=(me, rival),
        in_check=board.is_check(),
        king=_king_text(board, color),
        last_move=_last_move_text(board),
        threats=threats,
        chances=chances[:3],
        moves=moves,
        by_piece=by_piece,
        piece_tags=tags,
        piece_types=types,
    )


def state_of(obs: Observation) -> dict:
    """The `state` both models receive: short, and only what matters."""
    state = {
        "you_play": obs.side,
        "move_number": obs.fullmove,
        "phase": obs.phase,
        "material": _material_text(obs.material[0] - obs.material[1]),
        "king": obs.king,
        "threats_to_you": obs.threats or ["none"],
        "chances_for_you": obs.chances or ["none"],
    }
    if obs.last_move:
        state["rival_last_move"] = obs.last_move
    return state
