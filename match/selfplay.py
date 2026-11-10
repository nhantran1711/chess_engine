"""
A/B match between two versions of this engine, to measure whether a change gains Elo.

    python match/selfplay.py NEW_DIR OLD_DIR [--games 200] [--movetime 300] [--concurrency 10]
                             [--python-a PATH] [--python-b PATH]

Each DIR is a checkout of this repo (e.g. a `git worktree` of an older commit); its uci.py is
started as a UCI engine. Openings come from match/openings.epd, extended with a few random plies
so there are enough distinct starts, and each opening is played with both colours.
The arbiter is this checkout's GameState: it checks legality and adjudicates mate, stalemate,
threefold repetition, the fifty-move rule, bare kings and a ply cap.
"""

import argparse
import math
import os
import random
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ChessGame.ChessEngine import GameState

MAX_PLIES = 300


class Engine():
    def __init__(self, directory, python):
        self.proc = subprocess.Popen([python, "uci.py"], cwd = directory, text = True,
                                     stdin = subprocess.PIPE, stdout = subprocess.PIPE, bufsize = 1)
        self.send("uci")
        self.waitFor("uciok")

    def send(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def waitFor(self, prefix):
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("engine exited")
            if line.startswith(prefix):
                return line.strip()

    def newGame(self):
        self.send("ucinewgame")
        self.send("isready")
        self.waitFor("readyok")

    def bestMove(self, fen, moves, movetime):
        self.send(f"position fen {fen}" + (" moves " + " ".join(moves) if moves else ""))
        self.send(f"go movetime {movetime}")
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


# Returns 1, 0.5 or 0 from White's point of view, and why the game ended
def playGame(white, black, fen, movetime):
    gs = GameState.fromFen(fen)
    white.newGame()
    black.newGame()
    played = []
    while True:
        legal = gs.getValidateMoves()
        if not legal:
            if gs.checkMate:
                return (0 if gs.whiteToMove else 1), "mate"
            return 0.5, "stalemate"
        if gs.halfmoveClock >= 100:
            return 0.5, "fifty moves"
        if gs.zobristLog.count(gs.zobristKey) >= 2:
            return 0.5, "repetition"
        if bareKings(gs):
            return 0.5, "insufficient material"
        if len(played) >= MAX_PLIES:
            return 0.5, "ply cap"

        engine = white if gs.whiteToMove else black
        text = engine.bestMove(fen, played, movetime)
        move = next((m for m in legal if uci(m) == text), None)
        if move is None:
            return (0 if gs.whiteToMove else 1), f"illegal move {text}"
        gs.makeMoves(move)
        played.append(text)


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
    parser.add_argument("--movetime", type = int, default = 300, help = "milliseconds per move")
    parser.add_argument("--concurrency", type = int, default = max(1, (os.cpu_count() or 2) - 2))
    parser.add_argument("--python-a", default = sys.executable, help = "interpreter for engine A, e.g. PyPy")
    parser.add_argument("--python-b", default = sys.executable, help = "interpreter for engine B")
    parser.add_argument("--openings", default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openings.epd"))
    args = parser.parse_args()

    openings = makeOpenings(args.openings, (args.games + 1) // 2)
    jobs = [(fen, aIsWhite) for fen in openings for aIsWhite in (True, False)][:args.games]
    results = {"W" : 0, "D" : 0, "L" : 0}
    lock = threading.Lock()
    local = threading.local()

    def run(job):
        fen, aIsWhite = job
        if not hasattr(local, "engines"):
            local.engines = (Engine(args.engineA, args.python_a), Engine(args.engineB, args.python_b))
        a, b = local.engines
        result, reason = playGame(a if aIsWhite else b, b if aIsWhite else a, fen, args.movetime)
        scoreA = result if aIsWhite else 1 - result
        with lock:
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
