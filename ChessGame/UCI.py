"""
UCI (Universal Chess Interface) front end, so the engine can run in standard chess GUIs
(Arena, Cute Chess, En Croissant, ...) and testing tools (cutechess-cli, fastchess).

Run:
    python uci.py

Supported commands: uci, isready, ucinewgame, position [startpos | fen <fen>] [moves ...],
go [wtime btime winc binc movestogo movetime depth nodes infinite], stop, quit.
The search runs on a background thread so "stop" and "isready" are answered while it thinks.
"""

import sys
import threading
import time
from ChessGame.ChessEngine import GameState
from ChessGame.ChessAI import Searcher, MAX_DEPTH, MATE_BOUND, CHECKMATE

ENGINE_NAME = "ChessGame"
ENGINE_AUTHOR = "nhantran1711"
MOVE_OVERHEAD = 0.05 # Seconds kept back per move for Python/GUI latency
DEFAULT_MOVES_TO_GO = 30


def moveToUci(move):
    return move.getChessNotation() + move.promotionSuffix()


# Material units -> centipawns, mate scores -> "mate N" in moves (negative when getting mated)
def scoreToUci(score):
    if score >= MATE_BOUND:
        return f"mate {(CHECKMATE - score + 1) // 2}"
    if score <= -MATE_BOUND:
        return f"mate -{(CHECKMATE + score) // 2}"
    return f"cp {score * 100}"


# Seconds to spend on this move, or None for no time limit
def allocateTime(params, whiteToMove):
    if "movetime" in params:
        return max(0.01, params["movetime"] / 1000 - MOVE_OVERHEAD)
    remaining = params.get("wtime" if whiteToMove else "btime")
    if remaining is None:
        return None
    increment = params.get("winc" if whiteToMove else "binc", 0)
    movesToGo = params.get("movestogo", DEFAULT_MOVES_TO_GO)
    budget = min(remaining / movesToGo + increment * 0.75, remaining * 0.5)
    return max(0.01, budget / 1000 - MOVE_OVERHEAD)


class UCIEngine():
    def __init__(self, out = sys.stdout):
        self.out = out
        self.searcher = Searcher()
        self.gamestate = GameState()
        self.searchThread = None
        self.stopEvent = threading.Event()
        self.outputLock = threading.Lock()

    def send(self, line):
        with self.outputLock:
            self.out.write(line + "\n")
            self.out.flush()

    # Returns False when the engine should exit
    def handle(self, line):
        tokens = line.split()
        if not tokens:
            return True
        command = tokens[0]

        if command == "uci":
            self.send(f"id name {ENGINE_NAME}")
            self.send(f"id author {ENGINE_AUTHOR}")
            self.send("uciok")
        elif command == "isready":
            self.send("readyok")
        elif command == "ucinewgame":
            self.stopSearch()
            self.searcher = Searcher() # Fresh transposition table
        elif command == "position":
            self.stopSearch()
            self.setPosition(tokens[1:])
        elif command == "go":
            self.stopSearch()
            self.startSearch(tokens[1:])
        elif command == "stop":
            self.stopSearch()
        elif command == "quit":
            self.stopSearch()
            return False
        # debug, setoption, register, ponderhit: accepted and ignored
        return True

    def setPosition(self, tokens):
        if "moves" in tokens:
            split = tokens.index("moves")
            setup, moves = tokens[:split], tokens[split + 1:]
        else:
            setup, moves = tokens, []

        if setup and setup[0] == "fen":
            self.gamestate = GameState.fromFen(" ".join(setup[1:]))
        else:
            self.gamestate = GameState()

        for notation in moves:
            move = next((m for m in self.gamestate.getValidateMoves() if moveToUci(m) == notation), None)
            if move is None:
                self.send(f"info string illegal move {notation}, ignoring the rest")
                break
            self.gamestate.makeMoves(move)

    def startSearch(self, tokens):
        params = {}
        infinite = False
        i = 0
        while i < len(tokens):
            if tokens[i] == "infinite":
                infinite = True
            elif tokens[i] in ("wtime", "btime", "winc", "binc", "movestogo", "movetime", "depth", "nodes") and i + 1 < len(tokens):
                params[tokens[i]] = int(tokens[i + 1])
                i += 1
            i += 1

        timeLimit = None if infinite else allocateTime(params, self.gamestate.whiteToMove)
        self.searcher.timeLimit = timeLimit if timeLimit is not None else float("inf")
        self.searcher.maxDepth = params.get("depth", MAX_DEPTH)
        self.searcher.maxNodes = params.get("nodes")
        self.searcher.infoCallback = self.sendInfo
        self.searcher.stopRequested = False
        self.stopEvent.clear()

        self.searchThread = threading.Thread(target = self.runSearch, args = (infinite,), daemon = True)
        self.searchThread.start()

    def runSearch(self, infinite):
        move = self.searcher.search(self.gamestate)
        # "go infinite" must not report a move until the GUI sends stop
        if infinite:
            self.stopEvent.wait()
        self.send(f"bestmove {moveToUci(move) if move is not None else '0000'}")

    def sendInfo(self, depth, score, nodes, seconds, pv):
        ms = int(seconds * 1000)
        nps = int(nodes / seconds) if seconds > 0 else 0
        self.send(f"info depth {depth} score {scoreToUci(score)} nodes {nodes} nps {nps} time {ms} pv {' '.join(moveToUci(m) for m in pv)}")

    def stopSearch(self):
        if self.searchThread is not None:
            self.searcher.stopRequested = True
            self.stopEvent.set()
            self.searchThread.join()
            self.searchThread = None


def main():
    engine = UCIEngine()
    for line in sys.stdin:
        if not engine.handle(line.strip()):
            break
    engine.stopSearch()


if __name__ == "__main__":
    main()
