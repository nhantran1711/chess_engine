"""
A/B match between two versions of this engine, to measure whether a change gains Elo.

    python match/selfplay.py NEW_DIR OLD_DIR [--games 200] [--movetime 300] [--concurrency 10]
                             [--python-a PATH] [--python-b PATH] [--option-a NAME=VALUE ...] [--option-b ...]

To test one search technique, play the same checkout against itself with it switched off on one side:
    python match/selfplay.py . . --option-b NullMove=false

To rate the engine against Stockfish at the time control its UCI_Elo is calibrated at:
    python match/selfplay.py . path/to/stockfish.exe --python-a path/to/pypy.exe --tc 120+1 --resign 1000 ^
        --option-b UCI_LimitStrength=true --option-b UCI_Elo=1800 --option-b Threads=1 --option-b Hash=16

Each engine is a checkout of this repo (e.g. a `git worktree` of an older commit), whose uci.py is
started as a UCI engine, or the path of any other UCI engine executable. Openings come from match/openings.epd, extended with a few random plies
so there are enough distinct starts, and each opening is played with both colours.
The arbiter is this checkout's GameState: it checks legality and adjudicates mate, stalemate,
threefold repetition, the fifty-move rule, bare kings and a ply cap. With --tc it keeps both clocks
and a flag fall loses; with --resign N a game ends once both engines have reported a score of at
least N centipawns for the same side on each of their last 3 moves.
"""

import argparse
import math
import os
import random
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ChessGame.ChessEngine import GameState

MAX_PLIES = 300
RESIGN_MOVES = 3 # Each engine's last this many scores must agree
MATE_SCORE = 100000


class Engine():
    # path: a checkout of this repo (run its uci.py with python) or any UCI engine executable
    def __init__(self, path, python, options = ()):
        command, cwd = ([path], None) if os.path.isfile(path) else ([python, "uci.py"], path)
        self.proc = subprocess.Popen(command, cwd = cwd, text = True,
                                     stdin = subprocess.PIPE, stdout = subprocess.PIPE, bufsize = 1)
        self.score = None # Last reported score, centipawns from the side to move's point of view
        self.send("uci")
        self.waitFor("uciok")
        for option in options:
            name, value = option.split("=", 1)
            self.send(f"setoption name {name} value {value}")

    def send(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def waitFor(self, prefix):
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("engine exited")
            if line.startswith("info") and " score " in line:
                tokens = line.split()
                i = tokens.index("score")
                if tokens[i + 1] == "cp":
                    self.score = int(tokens[i + 2])
                elif tokens[i + 1] == "mate":
                    self.score = MATE_SCORE if int(tokens[i + 2]) > 0 else -MATE_SCORE
            if line.startswith(prefix):
                return line.strip()

    def newGame(self):
        self.send("ucinewgame")
        self.send("isready")
        self.waitFor("readyok")

    # go is e.g. "movetime 300" or "wtime 119000 btime 120000 winc 1000 binc 1000"
    def bestMove(self, fen, moves, go):
        self.score = None
        self.send(f"position fen {fen}" + (" moves " + " ".join(moves) if moves else ""))
        self.send(f"go {go}")
        return self.waitFor("bestmove").split()[1]

    def close(self):
        try:
            self.send("quit")
            self.proc.wait(timeout = 5)
        except Exception:
            self.proc.kill()


def uci(move):
    return move.getChessNotation() + move.promotionSuffix()


def bareKings(gs):
    pieces = [sq[1] for row in gs.board for sq in row if sq != "--"]
    return all(p == "K" for p in pieces) or (len(pieces) == 3 and any(p in "NB" for p in pieces))


# Returns 1, 0.5 or 0 from White's point of view, why the game ended, and the moves played.
# tc is None (fixed movetime) or (base seconds, increment seconds)
def playGame(white, black, fen, movetime, tc = None, resign = None):
    gs = GameState.fromFen(fen)
    white.newGame()
    black.newGame()
    played = []
    scores = [] # White's-view score after each ply, as reported by the engine that played it
    clock = {True : tc[0], False : tc[0]} if tc else None
    while True:
        legal = gs.getValidateMoves()
        if not legal:
            if gs.checkMate:
                return (0 if gs.whiteToMove else 1), "mate", played
            return 0.5, "stalemate", played
        if gs.halfmoveClock >= 100:
            return 0.5, "fifty moves", played
        if gs.zobristLog.count(gs.zobristKey) >= 2:
            return 0.5, "repetition", played
        if bareKings(gs):
            return 0.5, "insufficient material", played
        if len(played) >= MAX_PLIES:
            return 0.5, "ply cap", played

        side = gs.whiteToMove
        engine = white if side else black
        if tc:
            go = (f"wtime {max(1, int(clock[True] * 1000))} btime {max(1, int(clock[False] * 1000))} "
                  f"winc {int(tc[1] * 1000)} binc {int(tc[1] * 1000)}")
        else:
            go = f"movetime {movetime}"
        start = time.monotonic()
        text = engine.bestMove(fen, played, go)
        if tc:
            clock[side] -= time.monotonic() - start
            if clock[side] < 0:
                return (0 if side else 1), "time forfeit", played
            clock[side] += tc[1]
        move = next((m for m in legal if uci(m) == text), None)
        if move is None:
            return (0 if side else 1), f"illegal move {text}", played
        gs.makeMoves(move)
        played.append(text)

        if resign is not None:
            scores.append(None if engine.score is None else (engine.score if side else -engine.score))
            recent = scores[-2 * RESIGN_MOVES:]
            if len(recent) == 2 * RESIGN_MOVES and None not in recent:
                if all(s >= resign for s in recent):
                    return 1, "adjudicated: Black resigns", played
                if all(s <= -resign for s in recent):
                    return 0, "adjudicated: White resigns", played


def makeOpenings(path, count, seed = 1):
    with open(path) as f:
        base = [" ".join(line.split()[:4]) + " 0 1" for line in f if line.strip()]
    # Past the file's own positions, add two random plies to a random one of them
    rng = random.Random(seed)
    openings = base[:count]
    while len(openings) < count:
        gs = GameState.fromFen(rng.choice(base))
        for _ in range(2):
            gs.makeMoves(rng.choice(gs.getValidateMoves()))
        fen = toFen(gs)
        if fen not in openings:
            openings.append(fen)
    return openings


def toFen(gs):
    rows = []
    for row in gs.board:
        text, empty = "", 0
        for sq in row:
            if sq == "--":
                empty += 1
                continue
            if empty:
                text, empty = text + str(empty), 0
            text += sq[1] if sq[0] == "w" else sq[1].lower()
        rows.append(text + (str(empty) if empty else ""))
    rights = gs.currentCastlingRight
    castling = ("K" if rights.wks else "") + ("Q" if rights.wqs else "") + ("k" if rights.bks else "") + ("q" if rights.bqs else "")
    ep = "-"
    if gs.enpassantPossbile:
        r, c = gs.enpassantPossbile
        ep = "abcdefgh"[c] + str(8 - r)
    return f"{'/'.join(rows)} {'w' if gs.whiteToMove else 'b'} {castling or '-'} {ep} {gs.halfmoveClock} 1"


def eloFromScore(score):
    score = min(max(score, 1e-6), 1 - 1e-6)
    return -400 * math.log10(1 / score - 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engineA")
    parser.add_argument("engineB")
    parser.add_argument("--games", type = int, default = 200)
    parser.add_argument("--movetime", type = int, default = 300, help = "milliseconds per move (ignored with --tc)")
    parser.add_argument("--tc", help = "clock per game as BASE+INC in seconds, e.g. 120+1")
    parser.add_argument("--resign", type = int, help = "adjudicate once both engines agree on a score this large (centipawns)")
    parser.add_argument("--games-log", help = "append each game as a line: result, reason, opening FEN, moves")
    parser.add_argument("--concurrency", type = int, default = max(1, (os.cpu_count() or 2) - 2))
    parser.add_argument("--python-a", default = sys.executable, help = "interpreter for engine A, e.g. PyPy")
    parser.add_argument("--python-b", default = sys.executable, help = "interpreter for engine B")
    parser.add_argument("--option-a", action = "append", default = [], help = "UCI option for engine A, NAME=VALUE (repeatable)")
    parser.add_argument("--option-b", action = "append", default = [], help = "UCI option for engine B")
    parser.add_argument("--openings", default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openings.epd"))
    args = parser.parse_args()

    tc = tuple(float(x) for x in args.tc.split("+")) if args.tc else None
    openings = makeOpenings(args.openings, (args.games + 1) // 2)
    jobs = [(fen, aIsWhite) for fen in openings for aIsWhite in (True, False)][:args.games]
    results = {"W" : 0, "D" : 0, "L" : 0}
    lock = threading.Lock()
    local = threading.local()

    def run(job):
        fen, aIsWhite = job
        if not hasattr(local, "engines"):
            local.engines = (Engine(args.engineA, args.python_a, args.option_a), Engine(args.engineB, args.python_b, args.option_b))
        a, b = local.engines
        result, reason, moves = playGame(a if aIsWhite else b, b if aIsWhite else a, fen, args.movetime, tc, args.resign)
        scoreA = result if aIsWhite else 1 - result
        with lock:
            if args.games_log:
                with open(args.games_log, "a") as f:
                    white, black = ("A", "B") if aIsWhite else ("B", "A")
                    f.write(f"{white}-{black} {result} [{reason}] {fen} | {' '.join(moves)}\n")
            results["W" if scoreA == 1 else "D" if scoreA == 0.5 else "L"] += 1
            n = sum(results.values())
            print(f"[{n}/{len(jobs)}] A {'white' if aIsWhite else 'black'}: {scoreA} ({reason})  "
                  f"total +{results['W']} ={results['D']} -{results['L']}", flush = True)

    pool = ThreadPoolExecutor(args.concurrency)
    try:
        list(pool.map(run, jobs))
    finally:
        pool.shutdown()

    w, d, l = results["W"], results["D"], results["L"]
    n = w + d + l
    s = (w + d / 2) / n
    var = (w * (1 - s) ** 2 + d * (0.5 - s) ** 2 + l * s ** 2) / n
    margin = 1.96 * math.sqrt(var / n)
    print(f"\nA vs B: +{w} ={d} -{l}  score {s:.3f}")
    print(f"Elo difference {eloFromScore(s):+.0f}  (95% CI {eloFromScore(s - margin):+.0f} to {eloFromScore(s + margin):+.0f})")


if __name__ == "__main__":
    main()
