import json

import chess

from chesswar import motor
from chesswar.arena import Arena, MatchConfig
from chesswar.backends.baseline import RandomBackend
from chesswar.observe import observe, see
from chesswar.schema import OPTION_BUDGET, build, option_chars


def info(fen, san):
    b = chess.Board(fen)
    o = observe(b)
    return o, o.info(b.parse_san(san).uci())


def test_see_free_queen():
    b = chess.Board("4k3/8/8/3q4/8/8/3R4/4K3 w - - 0 1")
    assert see(b, b.parse_san("Rxd5")) == 9


def test_see_defended_pawn_loses_knight():
    # 1.e4 e5 2.Nf3 Nc6: Nxe5 Nxe5 loses the knight for a pawn
    _, mi = info("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", "Nxe5")
    assert mi.gain == 1 - 3 and mi.unsound


def test_mate_and_allows_mate():
    _, mi = info("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "Ra8#")
    assert mi.mate
    o, kh1 = info("3r2k1/5ppp/8/8/3q4/8/2R2PPP/6K1 w - - 0 1", "Kh1")
    assert kh1.allows_mate
    assert o.threats[0] == "the rival threatens checkmate next move"
    assert o.info("h2h3").stops_mate


def test_leaving_queen_hanging_is_unsound():
    o, mi = info("rnb1kbnr/pppp1ppp/8/4p3/3Q4/8/PPPPPPPP/RNB1KBNR w KQkq - 0 1", "Nf3")
    assert mi.risk == 8 and mi.unsound  # exd4 Nxd4: queen for a pawn


def test_shield_replaces_blunder_with_models_next_choice():
    b = chess.Board("3r2k1/5ppp/8/8/3q4/8/2R2PPP/6K1 w - - 0 1")
    o = observe(b)
    # the model prefers the king (Kh1 allows mate); its own next choice is h3
    answers = {
        "piece": {"choice": "g1", "probabilities": {"g1": 0.6, "h2": 0.3, "c2": 0.1, "g2": 0.0}},
        "move_g1": {"choice": "g1h1", "probabilities": {"g1h1": 0.9, "g1f1": 0.1}},
        "move_h2": {"choice": "h2h3", "probabilities": {"h2h3": 0.8, "h2h4": 0.2}},
    }
    d = motor.resolve(o, answers, shield=True)
    assert d.raw_uci == "g1h1" and d.overridden and d.uci == "h2h3"
    d2 = motor.resolve(o, answers, shield=False)
    assert d2.uci == "g1h1" and not d2.overridden


def test_questions_fit_laya_budget():
    for fen in (
        chess.STARTING_FEN,
        "k7/8/8/8/3Q4/8/8/3K4 w - - 0 1",
        "r3k2r/pppq1ppp/2npbn2/2b1p3/2B1P3/2NPBN2/PPPQ1PPP/R3K2R w KQkq - 0 8",
    ):
        state, q = build(observe(chess.Board(fen)))
        assert all(v <= OPTION_BUDGET for v in option_chars(q).values())
        assert all(len(s["criteria"]) >= 2 for s in q.values() if s["type"] == "choice")


def test_random_match_end_to_end(tmp_path):
    cfg = MatchConfig(p1="random", p2="random2", games=2, clock_s=0, max_plies=60, delay_s=0, analyze=False, out=str(tmp_path))
    a, b = RandomBackend(1), RandomBackend(2)
    b.name = "random2"
    arena = Arena(cfg, {"random": a, "random2": b}, log=lambda *_: None)
    out = arena.run()
    rep = json.loads((out / "replay.json").read_text(encoding="utf-8"))
    assert rep["status"] == "finished" and len(rep["games"]) == 2
    assert rep["games"][0]["white"] == "random" and rep["games"][1]["white"] == "random2"
    assert all(g["result"] in ("1-0", "0-1", "1/2-1/2") for g in rep["games"])
    assert (out / "games.pgn").read_text(encoding="utf-8").count("[Event ") == 2
