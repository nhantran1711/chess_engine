"""
Texel tuning: fit the evaluation weights to game results.

Each position is labelled with its game's result y (1 White win, 0.5 draw, 0 loss).
The evaluation e (centipawns, White's view) is mapped to an expected score with the Elo-style logistic

    p = 1 / (1 + 10^(-K * e / 400))

and the weights are chosen to minimise the mean squared error between p and y. K only rescales the
evaluation, so it is fitted once with the starting weights and then held fixed.

For a fixed position the evaluation is linear in the weights. Two kinds of feature:
  - piece type t on square s: weight mg[t, s] * phase/24 + eg[t, s] * (24 - phase)/24, sign +1 White / -1 Black.
    Stored sparsely as up to 32 (feature, sign) pairs per position
  - the positional terms of Evaluation.evalTerms (passed pawns, king shield, ...): a dense count per term,
    White's minus Black's, times the same tapered mg/eg weights
Features come from the engine's own Evaluation code, so the tuner and the engine can't disagree.

    python tuning/texel.py tuning/data/quiet-labeled.v7.epd.gz   # labelled positions: FEN ... c9 "1-0";
    python tuning/texel.py tuning/games.pgn                       # or games (needs python-chess)

Fits, reports train/test MSE, and writes ChessGame/EvalParams.py.
"""

import gzip
import math
import os
import re
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ChessGame import EvalParams
from ChessGame.ChessEngine import GameState
from ChessGame.Evaluation import evalTerms, PHASE_WEIGHTS, MAX_PHASE, NUM_TERMS

PIECES = "PNBRQK"
NUM_PST = 6 * 64
NUM_WEIGHTS = NUM_PST + NUM_TERMS
MAX_PIECES = 32
SKIP_PLIES = 4 # PGN only: the first moves after a random opening are still unsettled
TEST_FRACTION = 0.1
SEED = 2026
RESULTS = {"1-0" : 1.0, "1/2-1/2" : 0.5, "0-1" : 0.0}
PARAMS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ChessGame", "EvalParams.py")


# (FEN, label, group) for every position. The group keeps one game's positions on the same side of the
# train/test split; EPD positions have no game, so each is its own group
def readEpd(path):
    opener = gzip.open if path.endswith(".gz") else open
    pattern = re.compile(r'c9 "([^"]+)"')
    with opener(path, "rt") as f:
        for i, line in enumerate(f):
            fields = line.split()
            match = pattern.search(line)
            if len(fields) >= 4 and match and match.group(1) in RESULTS:
                yield " ".join(fields[:4]) + " 0 1", RESULTS[match.group(1)], i


# Quiet positions from games: not in check, the move played from it isn't a capture or promotion,
# and the move into it wasn't either, so the static evaluation isn't taken mid-exchange
def readPgn(path):
    import chess.pgn
    with open(path) as f:
        gameNumber = 0
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            label = RESULTS.get(game.headers.get("Result"))
            if label is not None:
                board = game.board()
                lastWasCapture = False
                for ply, move in enumerate(game.mainline_moves()):
                    if (ply >= SKIP_PLIES and not lastWasCapture and not board.is_check()
                            and not board.is_capture(move) and move.promotion is None):
                        yield board.fen(), label, gameNumber
                    lastWasCapture = board.is_capture(move) or move.promotion is not None
                    board.push(move)
            gameNumber += 1


def extract(path):
    reader = readEpd if path.endswith((".epd", ".epd.gz")) else readPgn
    pst, signs, terms, phases, labels, groups = [], [], [], [], [], []
    for n, (fen, label, group) in enumerate(reader(path)):
        board = GameState.fromFen(fen).board
        row, phase = [], 0
        for sq in range(64):
            code = board[sq // 8][sq % 8]
            if code != "--":
                white = code[0] == "w"
                square = sq if white else (7 - sq // 8) * 8 + sq % 8 # Black reads the table mirrored
                row.append((PIECES.index(code[1]) * 64 + square, 1 if white else -1))
                phase += PHASE_WEIGHTS[code[1]]
        row += [(0, 0)] * (MAX_PIECES - len(row))
        pst.append([index for index, _ in row[:MAX_PIECES]])
        signs.append([sign for _, sign in row[:MAX_PIECES]])
        terms.append(evalTerms(board))
        phases.append(min(phase, MAX_PHASE))
        labels.append(label)
        groups.append(group)
        if n % 200000 == 0 and n:
            print(f"  {n} positions read", flush = True)
    return (np.array(pst, dtype = np.int16), np.array(signs, dtype = np.int8), np.array(terms, dtype = np.int8),
            np.array(phases, dtype = np.int8), np.array(labels, dtype = np.float32), np.array(groups, dtype = np.int64))


class Dataset():
    def __init__(self, pst, signs, terms, phases, labels):
        self.pst = pst.astype(np.int32)
        self.flat = self.pst.ravel()
        self.labels = labels.astype(np.float64)
        mgShare = (phases / MAX_PHASE).astype(np.float32)
        self.mgWeight = signs * mgShare[:, None] # Coefficient of each piece feature's mg weight
        self.egWeight = signs * (1 - mgShare)[:, None]
        self.termsMg = terms * mgShare[:, None] # Coefficient of each term's mg weight
        self.termsEg = terms * (1 - mgShare)[:, None]

    def evaluate(self, mg, eg):
        return ((mg[self.pst] * self.mgWeight).sum(axis = 1) + (eg[self.pst] * self.egWeight).sum(axis = 1)
                + self.termsMg @ mg[NUM_PST:] + self.termsEg @ eg[NUM_PST:])

    def mse(self, mg, eg, K):
        return float(np.mean((sigmoid(self.evaluate(mg, eg), K) - self.labels) ** 2))

    # d(MSE)/d(weights), via the chain rule through the sigmoid
    def gradient(self, mg, eg, K):
        p = sigmoid(self.evaluate(mg, eg), K)
        r = 2 * (p - self.labels) * p * (1 - p) * K * math.log(10) / 400 / len(self.labels)
        gradMg = np.concatenate([np.bincount(self.flat, weights = (self.mgWeight * r[:, None]).ravel(), minlength = NUM_PST),
                                 self.termsMg.T @ r])
        gradEg = np.concatenate([np.bincount(self.flat, weights = (self.egWeight * r[:, None]).ravel(), minlength = NUM_PST),
                                 self.termsEg.T @ r])
        return gradMg, gradEg


def sigmoid(e, K):
    return 1 / (1 + 10 ** (-K * e / 400))


# Golden-section search: the MSE is unimodal in K
def fitK(data, mg, eg, low = 0.1, high = 3.0):
    ratio = (math.sqrt(5) - 1) / 2
    for _ in range(60):
        a, b = high - ratio * (high - low), low + ratio * (high - low)
        if data.mse(mg, eg, a) < data.mse(mg, eg, b):
            high = b
        else:
            low = a
    return (low + high) / 2


def currentWeights():
    mg = [EvalParams.mgValue[p] + EvalParams.mgTable[p][sq] for p in PIECES for sq in range(64)]
    eg = [EvalParams.egValue[p] + EvalParams.egTable[p][sq] for p in PIECES for sq in range(64)]
    mg += [EvalParams.termMg[name] for name in EvalParams.termNames]
    eg += [EvalParams.termEg[name] for name in EvalParams.termNames]
    return np.array(mg, dtype = np.float64), np.array(eg, dtype = np.float64)


# The piece-square tables alone, positional terms switched off: what the engine evaluated before them
def pstOnly(mg, eg):
    mg, eg = mg.copy(), eg.copy()
    mg[NUM_PST:] = 0
    eg[NUM_PST:] = 0
    return mg, eg


# Full-batch Adam; keeps the weights with the best held-out MSE (early stopping)
def tune(train, test, mg, eg, K, iterations = 2000, rate = 1.0, beta1 = 0.9, beta2 = 0.999):
    params = np.concatenate([mg, eg])
    m, v = np.zeros_like(params), np.zeros_like(params)
    best = (test.mse(mg, eg, K), params.copy(), 0)
    for step in range(1, iterations + 1):
        gradMg, gradEg = train.gradient(params[:NUM_WEIGHTS], params[NUM_WEIGHTS:], K)
        grad = np.concatenate([gradMg, gradEg])
        m = beta1 * m + (1 - beta1) * grad
        v = beta2 * v + (1 - beta2) * grad ** 2
        params -= rate * (m / (1 - beta1 ** step)) / (np.sqrt(v / (1 - beta2 ** step)) + 1e-12)
        if step % 50 == 0:
            testMse = test.mse(params[:NUM_WEIGHTS], params[NUM_WEIGHTS:], K)
            if testMse < best[0]:
                best = (testMse, params.copy(), step)
            print(f"  step {step:5d}  train {train.mse(params[:NUM_WEIGHTS], params[NUM_WEIGHTS:], K):.6f}  test {testMse:.6f}", flush = True)
    return best[1][:NUM_WEIGHTS], best[1][NUM_WEIGHTS:], best[2]


# Split each piece's combined weights back into a material value plus a table that averages zero.
# Pawns never stand on the first or last rank, so those squares are left at zero
def decompose(weights):
    values, tables = {}, {}
    for t, piece in enumerate(PIECES):
        combined = weights[t * 64 : (t + 1) * 64]
        squares = range(8, 56) if piece == "P" else range(64)
        value = 0 if piece == "K" else round(float(np.mean([combined[sq] for sq in squares])))
        tables[piece] = [round(float(combined[sq])) - value if sq in squares else 0 for sq in range(64)]
        values[piece] = value
    return values, tables


def rounded(weights):
    values, tables = decompose(weights)
    pst = [values[p] + tables[p][sq] for p in PIECES for sq in range(64)]
    return np.array(pst + [round(float(w)) for w in weights[NUM_PST:]], dtype = np.float64)


def formatTable(values):
    rows = ["        " + " ".join(f"{x:4d}," for x in values[r * 8 : r * 8 + 8]) for r in range(8)]
    return "[\n" + "\n".join(rows) + "\n    ]"


def writeParams(mg, eg, header):
    mgValue, mgTable = decompose(mg)
    egValue, egTable = decompose(eg)
    lines = ['"""', header.strip(), '"""', ""]
    lines.append("mgValue = {" + ", ".join(f'"{p}" : {mgValue[p]}' for p in PIECES) + "}")
    lines.append("egValue = {" + ", ".join(f'"{p}" : {egValue[p]}' for p in PIECES) + "}")
    for name, tables in (("mgTable", mgTable), ("egTable", egTable)):
        lines.append("")
        lines.append(name + " = {")
        for p in PIECES:
            lines.append(f'    "{p}" : ' + formatTable(tables[p]) + ",")
        lines.append("}")
    lines.append("")
    lines.append("# Positional terms, (midgame, endgame) per unit of each count in Evaluation.evalTerms")
    lines.append("termNames = [" + ", ".join(f'"{n}"' for n in EvalParams.termNames) + "]")
    for name, weights in (("termMg", mg), ("termEg", eg)):
        lines.append(name + " = {" + ", ".join(f'"{n}" : {round(float(weights[NUM_PST + i]))}' for i, n in enumerate(EvalParams.termNames)) + "}")
    with open(PARAMS_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    path = sys.argv[1]
    cache = re.sub(r"(\.epd)?(\.gz)?$|\.pgn$", "", path) + ".features.npz"
    if os.path.exists(cache) and os.path.getmtime(cache) > os.path.getmtime(path):
        saved = np.load(cache)
        pst, signs, terms, phases, labels, groups = (saved[k] for k in ("pst", "signs", "terms", "phases", "labels", "groups"))
    else:
        print(f"Reading {path}")
        pst, signs, terms, phases, labels, groups = extract(path)
        np.savez_compressed(cache, pst = pst, signs = signs, terms = terms, phases = phases, labels = labels, groups = groups)

    rng = np.random.default_rng(SEED)
    uniqueGroups, groupIndex = np.unique(groups, return_inverse = True)
    isTest = (rng.random(len(uniqueGroups)) < TEST_FRACTION)[groupIndex]
    train = Dataset(pst[~isTest], signs[~isTest], terms[~isTest], phases[~isTest], labels[~isTest])
    test = Dataset(pst[isTest], signs[isTest], terms[isTest], phases[isTest], labels[isTest])
    print(f"{len(labels)} positions: {len(train.labels)} train, {len(test.labels)} test")
    print(f"Results: {np.mean(labels == 1):.1%} White wins, {np.mean(labels == 0.5):.1%} draws, {np.mean(labels == 0):.1%} Black wins")

    mg, eg = currentWeights()
    K = fitK(train, *pstOnly(mg, eg))
    print(f"K = {K:.4f}")
    rows = [("Piece-square tables only (current weights)", *[d.mse(*pstOnly(mg, eg), K) for d in (train, test)]),
            ("PST + positional terms (starting weights)", *[d.mse(mg, eg, K) for d in (train, test)])]

    mg, eg, bestStep = tune(train, test, mg, eg, K)
    mg, eg = rounded(mg), rounded(eg)
    rows.append((f"Texel-tuned, all weights (best step {bestStep})", *[d.mse(mg, eg, K) for d in (train, test)]))

    print(f"\n{'Evaluation':52s} {'Train MSE':>10s} {'Test MSE':>10s}")
    for name, trainMse, testMse in rows:
        print(f"{name:52s} {trainMse:10.6f} {testMse:10.6f}")
    print("\nPositional terms (mg, eg):")
    for i, name in enumerate(EvalParams.termNames):
        print(f"  {name:18s} {mg[NUM_PST + i]:5.0f} {eg[NUM_PST + i]:5.0f}")

    header = f"""
Evaluation weights in centipawns. Tables are from White's point of view, rank 8 first,
so index = row * 8 + col matches GameState.board; Black's pieces read them mirrored.

Generated by tuning/texel.py: Texel-tuned from {len(labels)} positions ({os.path.basename(path)}).
K = {K:.4f}, held-out MSE {rows[0][2]:.6f} (previous tables, no positional terms) -> {rows[-1][2]:.6f} (tuned).
"""
    writeParams(mg, eg, header)
    print(f"\nWrote {PARAMS_PATH}")


if __name__ == "__main__":
    main()
