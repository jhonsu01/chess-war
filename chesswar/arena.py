"""Match orchestration: games, clock, telemetry, analysis and the record for the viewer."""
from __future__ import annotations

import datetime as dt
import json
import random
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import chess
import chess.pgn

from . import motor
from .analysis import Analyzer, find_stockfish
from .backends import Backend
from .live import LiveState
from .observe import material, observe
from .openings import moves_of, schedule
from .schema import build


@dataclass
class MatchConfig:
    p1: str = "laya"
    p2: str = "jev"
    games: int = 10
    clock_s: float = 180.0
    max_plies: int = 240
    shield: bool = True
    seed: int = 7
    delay_s: float = 0.4
    analyze: bool = True
    stockfish: str | None = None
    depth: int = 12
    laya_checkpoint: str | None = None
    out: str = "results"


class MatchAborted(RuntimeError):
    pass


@dataclass
class Tally:
    """Per-player accumulator."""

    wins: int = 0
    draws: int = 0
    losses: int = 0
    decisions: int = 0
    forced: int = 0
    overrides: int = 0
    fallbacks: int = 0
    errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    time_used_ms: float = 0.0
    latency: list = field(default_factory=list)
    model_ms: list = field(default_factory=list)
    conf: list = field(default_factory=list)
    cpl_raw: list = field(default_factory=list)
    cpl: list = field(default_factory=list)
    served_by: str = ""
    streak_errors: int = 0

    def summary(self) -> dict:
        def mean(xs):
            return round(statistics.fmean(xs), 1) if xs else None

        def pct(xs, q):
            if not xs:
                return None
            s = sorted(xs)
            return round(s[min(len(s) - 1, int(q * len(s)))], 1)

        return {
            "points": self.wins + 0.5 * self.draws,
            "wins": self.wins,
            "draws": self.draws,
            "losses": self.losses,
            "decisions": self.decisions,
            "forced": self.forced,
            "latency_ms_mean": mean(self.latency),
            "latency_ms_p50": pct(self.latency, 0.5),
            "latency_ms_p95": pct(self.latency, 0.95),
            "model_ms_mean": mean(self.model_ms),
            "overridden_pct": round(100 * self.overrides / self.decisions, 1) if self.decisions else 0.0,
            "overrides": self.overrides,
            "fallbacks": self.fallbacks,
            "errors": self.errors,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "time_used_s": round(self.time_used_ms / 1000, 1),
            "confidence_mean": round(statistics.fmean(self.conf), 3) if self.conf else None,
            "acpl_raw": mean(self.cpl_raw),
            "acpl": mean(self.cpl),
            "blunders_raw": sum(1 for c in self.cpl_raw if c >= 300),
            "served_by": self.served_by,
        }


def _adjudicate(board: chess.Board) -> tuple[str, str]:
    diff = material(board, chess.WHITE) - material(board, chess.BLACK)
    if diff >= 3:
        return "1-0", "adjudicated"
    if diff <= -3:
        return "0-1", "adjudicated"
    return "1/2-1/2", "adjudicated"


class Arena:
    def __init__(self, cfg: MatchConfig, players: dict[str, Backend], live: LiveState | None = None, log=print):
        self.cfg = cfg
        self.players = players
        self.live = live
        self.log = log
        self.rng = random.Random(cfg.seed)
        self.tally = {cfg.p1: Tally(), cfg.p2: Tally()}
        self.games: list[dict] = []
        self.started = dt.datetime.now()
        stamp = self.started.strftime("%Y%m%d-%H%M%S")
        self.id = f"{stamp}-{cfg.p1}-vs-{cfg.p2}"
        self.dir = Path(cfg.out) / self.id
        self.analyzer: Analyzer | None = None
        self.status = "playing"

    # ------------------------------------------------------------------ match
    def run(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        if self.cfg.analyze:
            path = find_stockfish(self.cfg.stockfish)
            if path:
                self.analyzer = Analyzer(path, self.cfg.depth)
                self.log(f"Quality analysis with {self.analyzer.name} (depth {self.cfg.depth})")
            else:
                self.log("Stockfish not found: skipping ACPL (the match runs the same)")
        self._tele = open(self.dir / "telemetry.jsonl", "w", encoding="utf-8")
        try:
            for i, (name, line, p1_white) in enumerate(schedule(self.cfg.games), start=1):
                white = self.cfg.p1 if p1_white else self.cfg.p2
                black = self.cfg.p2 if p1_white else self.cfg.p1
                self._play(i, name, line, white, black)
            self.status = "finished"
        except (MatchAborted, KeyboardInterrupt) as e:
            self.status = "aborted"
            self.log(f"Match stopped: {e or 'interrupted'}")
        finally:
            self._tele.close()
            if self.analyzer:
                self.analyzer.close()
            self._write()
            self._publish_live()
        return self.dir

    # ------------------------------------------------------------------ game
    def _play(self, n: int, opening: str, line: str, white: str, black: str) -> None:
        cfg = self.cfg
        board = chess.Board()
        game = {
            "n": n,
            "white": white,
            "black": black,
            "opening": opening,
            "result": "*",
            "termination": None,
            "plies": [],
        }
        self.games.append(game)
        for m in moves_of(line):
            san = board.san(m)
            board.push(m)
            game["plies"].append({"san": san, "uci": m.uci(), "fen": board.fen(), "by": "book"})
        clock = {chess.WHITE: cfg.clock_s * 1000.0, chess.BLACK: cfg.clock_s * 1000.0}
        self.log(f"\nGame {n}/{cfg.games} · {opening} · white {white.upper()} vs black {black.upper()}")
        self._publish_live()

        result = termination = None
        while True:
            outcome = board.outcome(claim_draw=True)
            if outcome:
                result, termination = outcome.result(), outcome.termination.name.lower()
                break
            if len(board.move_stack) >= cfg.max_plies:
                result, termination = _adjudicate(board)
                break

            turn = board.turn
            name = white if turn == chess.WHITE else black
            t = self.tally[name]
            obs = observe(board)
            fen_before = board.fen()
            verdict = None
            if len(obs.moves) == 1:
                d = motor.forced(obs)
                t.forced += 1
            else:
                state, questions = build(obs)
                verdict = self.players[name].decide(state, questions)
                if verdict.error:
                    t.errors += 1
                    t.streak_errors += 1
                    self.log(f"  ! {name}: {verdict.error}")
                    if t.streak_errors >= 5:
                        raise MatchAborted(f"{name} failed 5 times in a row: {verdict.error}")
                else:
                    t.streak_errors = 0
                d = motor.resolve(obs, verdict.answers if not verdict.error else {}, cfg.shield, self.rng)
                t.decisions += 1
                t.latency.append(verdict.latency_ms)
                if verdict.model_ms:
                    t.model_ms.append(verdict.model_ms)
                t.input_tokens += verdict.input_tokens
                t.output_tokens += verdict.output_tokens
                t.cost_usd += verdict.cost_usd
                t.time_used_ms += verdict.latency_ms
                t.overrides += d.overridden
                t.fallbacks += d.fallback
                if d.move_conf is not None:
                    t.conf.append(d.move_conf)
                if verdict.served_by:
                    t.served_by = verdict.served_by
                if cfg.clock_s:
                    clock[turn] -= verdict.latency_ms
                self._telemetry(game, board, name, obs, state, questions, verdict, d)
                if cfg.clock_s and clock[turn] <= 0:
                    if board.has_insufficient_material(not turn):
                        result = "1/2-1/2"
                    else:
                        result = "0-1" if turn == chess.WHITE else "1-0"
                    termination = "time"
                    break

            ply = {
                "san": d.san,
                "uci": d.uci,
                "by": name,
                "fen_before": fen_before,
                "ms": round(verdict.latency_ms, 1) if verdict else 0,
                "p": round(d.p_move, 4) if d.p_move is not None else None,
                "conf": round(d.move_conf, 3) if d.move_conf is not None else None,
                "top": motor.top_moves(obs, d.joint),
                "plan": d.plan,
                "danger": round(d.danger, 3) if d.danger is not None else None,
            }
            if d.forced:
                ply["forced"] = True
            if d.overridden:
                ply["raw"], ply["raw_uci"], ply["ovr"] = d.raw_san, d.raw_uci, d.reason
            if d.fallback:
                ply["fb"] = True
            board.push(d.move)
            ply["fen"] = board.fen()
            ply["clock"] = [round(clock[chess.WHITE]), round(clock[chess.BLACK])] if cfg.clock_s else None
            game["plies"].append(ply)
            tag = f"  [SHIELD: {d.raw_san} {d.reason}]" if d.overridden else ""
            self.log(f"  {len(board.move_stack):3d}. {name:>8} {d.san:<8} {ply['ms']:7.1f} ms{tag}")
            self._publish_live()
            if cfg.delay_s:
                time.sleep(cfg.delay_s)

        game["result"], game["termination"] = result, termination
        if result == "1-0":
            self.tally[white].wins += 1
            self.tally[black].losses += 1
        elif result == "0-1":
            self.tally[black].wins += 1
            self.tally[white].losses += 1
        else:
            self.tally[white].draws += 1
            self.tally[black].draws += 1
        self.log(f"  => {result} ({termination}) · score {self._score()}")
        if self.analyzer:
            self._analyze(game)
        self._publish_live()
        self._write()

    # ------------------------------------------------------------------ helpers
    def _analyze(self, game: dict) -> None:
        for ply in game["plies"]:
            if ply.get("by") in (None, "book") or ply.get("forced"):
                continue
            ucis = [ply["uci"]] + ([ply["raw_uci"]] if ply.get("raw_uci") else [])
            losses = self.analyzer.cpl(ply["fen_before"], ucis)
            ply["cpl"] = losses[ply["uci"]]
            ply["cpl_raw"] = losses.get(ply.get("raw_uci") or ply["uci"])
            t = self.tally[ply["by"]]
            t.cpl.append(ply["cpl"])
            t.cpl_raw.append(ply["cpl_raw"])

    def _telemetry(self, game, board, name, obs, state, questions, verdict, d) -> None:
        rec = {
            "game": game["n"],
            "ply": len(board.move_stack) + 1,
            "player": name,
            "fen": board.fen(),
            "state": state,
            "questions": questions,
            "answers": verdict.answers,
            "move": d.uci,
            "san": d.san,
            "raw": d.raw_uci,
            "overridden": d.overridden,
            "reason": d.reason,
            "fallback": d.fallback,
            "latency_ms": round(verdict.latency_ms, 2),
            "model_ms": round(verdict.model_ms, 2),
            "input_tokens": verdict.input_tokens,
            "output_tokens": verdict.output_tokens,
            "cost_usd": verdict.cost_usd,
            "error": verdict.error,
            "served_by": verdict.served_by,
        }
        self._tele.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._tele.flush()

    def _score(self) -> str:
        a, b = self.cfg.p1, self.cfg.p2
        pa = self.tally[a].wins + 0.5 * self.tally[a].draws
        pb = self.tally[b].wins + 0.5 * self.tally[b].draws
        return f"{a.upper()} {pa:g} - {pb:g} {b.upper()}"

    def report(self, live: bool = False) -> dict:
        """Match record. When live, only the game in progress carries its moves."""
        cfg = asdict(self.cfg)
        games = []
        for i, g in enumerate(self.games):
            if live and i < len(self.games) - 1:
                games.append({k: v for k, v in g.items() if k != "plies"} | {"plies": []})
            else:
                games.append(g | {"plies": [{k: v for k, v in p.items() if k != "fen_before"} for p in g["plies"]]})
        return {
            "id": self.id,
            "date": self.started.astimezone().isoformat(timespec="seconds"),
            "status": self.status,
            "p1": self.cfg.p1,
            "p2": self.cfg.p2,
            "players": {k: b.meta() for k, b in self.players.items()},
            "config": cfg,
            "engine": self.analyzer.name if self.analyzer else None,
            "summary": {k: t.summary() for k, t in self.tally.items()},
            "games": games,
        }

    def _publish_live(self) -> None:
        if self.live:
            self.live.set(self.report(live=True))

    def _write(self) -> None:
        rep = self.report()
        (self.dir / "replay.json").write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
        match = {k: v for k, v in rep.items() if k != "games"}
        match["games"] = [
            {k: g[k] for k in ("n", "white", "black", "opening", "result", "termination")} | {"plies": len(g["plies"])}
            for g in self.games
        ]
        (self.dir / "match.json").write_text(json.dumps(match, ensure_ascii=False, indent=2), encoding="utf-8")
        with open(self.dir / "games.pgn", "w", encoding="utf-8") as f:
            for g in self.games:
                f.write(str(self._pgn(g)) + "\n\n")

    def _pgn(self, g: dict) -> chess.pgn.Game:
        game = chess.pgn.Game()
        h = game.headers
        h["Event"] = "chess-war"
        h["Site"] = "local"
        h["Date"] = self.started.strftime("%Y.%m.%d")
        h["Round"] = str(g["n"])
        h["White"] = g["white"]
        h["Black"] = g["black"]
        h["Result"] = g["result"] or "*"
        h["Opening"] = g["opening"]
        if g["termination"]:
            h["Termination"] = g["termination"]
        node = game
        for ply in g["plies"]:
            node = node.add_variation(chess.Move.from_uci(ply["uci"]))
            notes = []
            if ply.get("ovr"):
                notes.append(f"shield: {ply['raw']} ({ply['ovr']})")
            if ply.get("cpl") is not None:
                notes.append(f"cpl {ply['cpl']}")
            if ply.get("ms"):
                notes.append(f"{ply['ms']:.0f} ms")
            if notes:
                node.comment = "; ".join(notes)
        return game
