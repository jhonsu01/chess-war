"""chess-war: Laya vs Jev playing pixel-art chess through identical typed questions."""
from __future__ import annotations

import argparse
import os
import sys
import time
import webbrowser
from pathlib import Path

import chess

from . import motor
from .backends import PLAYERS, make
from .observe import observe
from .schema import OPTION_BUDGET, build, option_chars

ROOT = Path.cwd()


def load_env(path: Path = Path(".env")) -> None:
    """Load .env with no dependencies. Never overrides variables already set."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v and k.strip() not in os.environ:
            os.environ[k.strip()] = v


# Test positions: (name, FEN, correct moves). None = any sound move:
# no material lost, no mate in one allowed, castling rights kept.
PROBES = [
    ("free queen", "4k3/8/8/3q4/8/8/3R4/4K3 w - - 0 1", {"d2d5"}),
    ("mate in one", "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", {"a1a8"}),
    ("free knight", "rnbqkb1r/pppp1ppp/8/4p3/4n3/2N5/PPPP1PPP/R1BQKBNR w KQkq - 0 3", {"c3e4"}),
    ("free pawn", "rnbqkbnr/ppp2ppp/8/3pp3/8/4PN2/PPPP1PPP/RNBQKB1R w KQkq - 0 3", {"f3e5"}),
    ("promote", "8/4P3/8/8/8/8/k7/4K3 w - - 0 1", {"e7e8q"}),
    ("save the queen", "rnb1kbnr/pppp1ppp/8/4p3/3Q4/8/PPPPPPPP/RNB1KBNR w KQkq - 0 1", None),
    ("stop the mate", "3r2k1/5ppp/8/8/3q4/8/2R2PPP/6K1 w - - 0 1", None),
    ("quiet opening", "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", None),
    ("castle", "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4", None),
    ("open queen (budget)", "k7/8/8/8/3Q4/8/8/3K4 w - - 0 1", None),
]


def sound(mi) -> bool:
    return mi is not None and mi.outcome >= 0 and not mi.allows_mate and not mi.loses_castling


def cmd_check(args) -> int:
    ok = True
    for name in args.players:
        try:
            be = make(name, laya_checkpoint=args.laya_checkpoint)
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {name}: {e}")
            ok = False
            continue
        err = be.health()
        if err:
            print(f"[FAIL] {name}: {err}")
            ok = False
            be.close()
            continue
        state, questions = build(observe(chess.Board(PROBES[0][1])))
        v = be.decide(state, questions)
        if v.error:
            print(f"[FAIL] {name}: test decision -> {v.error}")
            ok = False
        else:
            print(
                f"[OK] {name:<8} {be.detail} · {v.latency_ms:.0f} ms"
                + (f" · served by {v.served_by}" if v.served_by else "")
                + (f" · {v.input_tokens} tokens" if v.input_tokens else "")
            )
        be.close()
    return 0 if ok else 1


def cmd_probe(args) -> int:
    be = make(args.player, laya_checkpoint=args.laya_checkpoint)
    err = be.health()
    if err:
        print(err)
        return 1
    print(f"{be.label} · {be.detail}\n")
    hits = 0
    for label, fen, good in PROBES:
        obs = observe(chess.Board(fen))
        state, questions = build(obs)
        chars = option_chars(questions)
        v = be.decide(state, questions)
        if v.error:
            print(f"  {label:<22} ERROR {v.error}")
            continue
        d = motor.resolve(obs, v.answers, shield=False)
        right = (d.uci in good) if good else sound(obs.info(d.uci))
        hits += right
        top = ", ".join(f"{s} {p:.2f}" for s, p in motor.top_moves(obs, d.joint))
        print(
            f"  {label:<22} {'OK ' if right else 'BAD'} {d.san:<7} {v.latency_ms:6.0f} ms"
            f" · max options {max(chars.values())}/{OPTION_BUDGET} chars · top: {top}"
        )
    print(f"\n  score {hits}/{len(PROBES)}")
    be.close()
    return 0


def cmd_match(args) -> int:
    from .arena import Arena, MatchConfig
    from .live import LiveState, serve

    cfg = MatchConfig(
        p1=args.p1,
        p2=args.p2,
        games=args.games,
        clock_s=args.clock,
        max_plies=args.max_plies,
        shield=not args.no_shield,
        seed=args.seed,
        delay_s=args.delay,
        analyze=not args.no_analyze,
        stockfish=args.stockfish,
        depth=args.depth,
        laya_checkpoint=args.laya_checkpoint,
        out=args.out,
    )
    players = {}
    for name in (cfg.p1, cfg.p2):
        be = make(name, seed=cfg.seed, laya_checkpoint=cfg.laya_checkpoint)
        err = be.health()
        if err:
            print(f"Cannot start: {err}")
            return 1
        players[name] = be
    live = None
    if not args.no_live:
        live = LiveState()
        serve(ROOT / "docs", live, os.environ.get("CHESSWAR_HOST", "127.0.0.1"), args.port)
        url = f"http://localhost:{args.port}/?live"
        print(f"Live viewer: {url}")
        if args.open:
            webbrowser.open(url)
        time.sleep(0.5)
    arena = Arena(cfg, players, live)
    out = arena.run()
    for be in players.values():
        be.close()
    print(f"\nResults in {out}")
    for name, s in arena.report()["summary"].items():
        print(
            f"  {name:<8} {s['points']:g} pts · p50 {s['latency_ms_p50']} ms · shield {s['overridden_pct']}%"
            f" · raw ACPL {s['acpl_raw']} · ${s['cost_usd']:.5f}"
        )
    if args.publish:
        from .publish import publish

        print(f"Published to docs/: {publish(out, ROOT)}")
    if live and not args.exit:
        print("The viewer stays open; Ctrl+C to quit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    return 0


def cmd_publish(args) -> int:
    from .publish import publish

    print(publish(Path(args.result), ROOT))
    return 0


def cmd_view(args) -> int:
    from .live import LiveState, serve

    serve(ROOT / "docs", LiveState(), "127.0.0.1", args.port)
    url = f"http://localhost:{args.port}/"
    print(f"Replay viewer: {url}  (Ctrl+C to quit)")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0


def main(argv: list[str] | None = None) -> int:
    load_env()
    p = argparse.ArgumentParser(prog="chess-war", description=__doc__)
    p.add_argument("--laya-checkpoint", default=None, help="english | multilingual | typed-decisions")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="check the connection and key of each player")
    c.add_argument("players", nargs="*", default=["laya", "jev"], choices=PLAYERS)
    c.set_defaults(fn=cmd_check)

    c = sub.add_parser("probe", help="test positions with a known answer")
    c.add_argument("player", choices=PLAYERS)
    c.set_defaults(fn=cmd_probe)

    c = sub.add_parser("match", help="play a match")
    c.add_argument("--p1", default="laya", choices=PLAYERS)
    c.add_argument("--p2", default="jev", choices=PLAYERS)
    c.add_argument("--games", type=int, default=10, help="games (pairs with colours swapped)")
    c.add_argument("--clock", type=float, default=180.0, help="seconds per player; 0 = no clock")
    c.add_argument("--max-plies", type=int, default=240, help="ply cap; after it the game is adjudicated on material")
    c.add_argument("--no-shield", action="store_true", help="disable the deterministic shield")
    c.add_argument("--seed", type=int, default=7)
    c.add_argument("--delay", type=float, default=0.4, help="pause between moves for the viewer (not charged to the clock)")
    c.add_argument("--no-analyze", action="store_true", help="skip Stockfish ACPL")
    c.add_argument("--stockfish", default=None, help="path to stockfish (or STOCKFISH_PATH)")
    c.add_argument("--depth", type=int, default=12)
    c.add_argument("--out", default="results")
    c.add_argument("--port", type=int, default=8080)
    c.add_argument("--no-live", action="store_true", help="no live viewer")
    c.add_argument("--open", action="store_true", help="open the viewer in the browser")
    c.add_argument("--exit", action="store_true", help="exit when the match ends instead of keeping the viewer up")
    c.add_argument("--publish", action="store_true", help="copy the result to docs/ when done")
    c.set_defaults(fn=cmd_match)

    c = sub.add_parser("publish", help="copy a result to docs/ and update the READMEs")
    c.add_argument("result", help="folder inside results/")
    c.set_defaults(fn=cmd_publish)

    c = sub.add_parser("view", help="serve docs/ to watch replays")
    c.add_argument("--port", type=int, default=8090)
    c.set_defaults(fn=cmd_view)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
