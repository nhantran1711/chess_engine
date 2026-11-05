"""
Texel tuning: fit the evaluation weights to game results.

Each quiet position from a game is labelled with that game's result y (1 White win, 0.5 draw, 0 loss).
The evaluation e (centipawns, White's view) is mapped to an expected score with the Elo-style logistic

    p = 1 / (1 + 10^(-K * e / 400))

and the weights are chosen to minimise the mean squared error between p and y. K only rescales the
evaluation, so it is fitted once with the starting weights and then held fixed.

For a fixed position the evaluation is linear in the weights: piece type t on square s adds
mg[t, s] * phase/24 + eg[t, s] * (24 - phase)/24, with sign +1 for White and -1 for Black. So each position
is stored once as a list of (feature, sign) pairs and the gradient is a weighted bincount over them.

    python tuning/texel.py tuning/games.pgn            # extract, fit, report, write ChessGame/EvalParams.py
"""

import math
import os
import sys
import numpy as np
import chess
import chess.pgn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ChessGame import EvalParams

PIECES = "PNBRQK"
PHASE_WEIGHTS = [0, 1, 1, 2, 4, 0]
MAX_PHASE = 24
MAX_PIECES = 32
SKIP_PLIES = 4 # The first moves after the random opening are still unsettled
TEST_FRACTION = 0.1
SEED = 2026
PARAMS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ChessGame", "EvalParams.py")


# Feature index for piece type t on our board square (row 0 = rank 8); Black's squares are mirrored
def featureIndex(pieceType, square, white):
    rank, file = chess.square_rank(square), chess.square_file(square)
    row = 7 - rank if white else rank
    return PIECES.index(pieceType) * 64 + row * 8 + file


# Quiet positions as padded (feature, sign) arrays, with phase, label and game number.
# Quiet: not in check, the move played from it isn't a capture or promotion, and the move into it wasn't either,
# so the static evaluation isn't taken in the middle of an exchange
def extract(pgnPath):
    features, signs, phases, labels, gameIDs = [], [], [], [], []
    results = {"1-0" : 1.0, "1/2-1/2" : 0.5, "0-1" : 0.0}
    with open(pgnPath) as f:
        gameNumber = 0
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            label = results.get(game.headers.get("Result"))
            if label is None:
                continue
            board = game.board()
            moves = list(game.mainline_moves())
            lastWasCapture = False
            for ply, move in enumerate(moves):
                quiet = (ply >= SKIP_PLIES and not lastWasCapture and not board.is_check()
                         and not board.is_capture(move) and move.promotion is None)
                if quiet:
                    row = [(featureIndex(chess.piece_symbol(piece.piece_type).upper(), sq, piece.color), 1 if piece.color else -1)
                           for sq, piece in board.piece_map().items()]
                    row += [(0, 0)] * (MAX_PIECES - len(row))
                    features.append([index for index, _ in row])
                    signs.append([sign for _, sign in row])
                    phases.append(min(MAX_PHASE, sum(PHASE_WEIGHTS[piece.piece_type - 1] for piece in board.piece_map().values())))
                    labels.append(label)
                    gameIDs.append(gameNumber)
                lastWasCapture = board.is_capture(move) or move.promotion is not None
                board.push(move)
            gameNumber += 1
    return (np.array(features, dtype = np.int16), np.array(signs, dtype = np.int8), np.array(phases, dtype = np.float64),
            np.array(labels, dtype = np.float64), np.array(gameIDs, dtype = np.int32), gameNumber)


class Dataset():
    def __init__(self, features, signs, phases, labels):
        self.features = features.astype(np.int64)
        self.labels = labels
        self.mgWeight = signs * (phases / MAX_PHASE)[:, None] # Coefficient of each feature's mg weight
        self.egWeight = signs * (1 - phases / MAX_PHASE)[:, None]
        self.flat = self.features.ravel()

    def evaluate(self, mg, eg):
        return (mg[self.features] * self.mgWeight + eg[self.features] * self.egWeight).sum(axis = 1)

    def mse(self, mg, eg, K):
        return float(np.mean((sigmoid(self.evaluate(mg, eg), K) - self.labels) ** 2))

    # d(MSE)/d(weights), via the chain rule through the sigmoid
    def gradient(self, mg, eg, K):
        p = sigmoid(self.evaluate(mg, eg), K)
        r = 2 * (p - self.labels) * p * (1 - p) * K * math.log(10) / 400 / len(self.labels)
        gradMg = np.bincount(self.flat, weights = (self.mgWeight * r[:, None]).ravel(), minlength = 384)
        gradEg = np.bincount(self.flat, weights = (self.egWeight * r[:, None]).ravel(), minlength = 384)
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


def initialWeights():
    mg = np.array([EvalParams.mgValue[p] + EvalParams.mgTable[p][sq] for p in PIECES for sq in range(64)], dtype = np.float64)
    eg = np.array([EvalParams.egValue[p] + EvalParams.egTable[p][sq] for p in PIECES for sq in range(64)], dtype = np.float64)
    return mg, eg


def materialWeights():
    mg = np.array([EvalParams.mgValue[p] for p in PIECES for _ in range(64)], dtype = np.float64)
    return mg, mg.copy()


# Full-batch Adam; keeps the weights with the best held-out MSE (early stopping)
def tune(train, test, mg, eg, K, iterations = 3000, rate = 1.0, beta1 = 0.9, beta2 = 0.999):
    params = np.concatenate([mg, eg])
    m, v = np.zeros_like(params), np.zeros_like(params)
    best = (test.mse(mg, eg, K), params.copy(), 0)
    for step in range(1, iterations + 1):
        gradMg, gradEg = train.gradient(params[:384], params[384:], K)
        grad = np.concatenate([gradMg, gradEg])
        m = beta1 * m + (1 - beta1) * grad
        v = beta2 * v + (1 - beta2) * grad ** 2
        params -= rate * (m / (1 - beta1 ** step)) / (np.sqrt(v / (1 - beta2 ** step)) + 1e-12)
        if step % 50 == 0:
            testMse = test.mse(params[:384], params[384:], K)
            if testMse < best[0]:
                best = (testMse, params.copy(), step)
            print(f"  step {step:5d}  train {train.mse(params[:384], params[384:], K):.6f}  test {testMse:.6f}", flush = True)
    return best[1][:384], best[1][384:], best[2]


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
    with open(PARAMS_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    pgnPath = sys.argv[1]
    cache = os.path.splitext(pgnPath)[0] + ".npz"
    if os.path.exists(cache) and os.path.getmtime(cache) > os.path.getmtime(pgnPath):
        saved = np.load(cache)
        features, signs, phases, labels, gameIDs, games = (saved[k] for k in ("features", "signs", "phases", "labels", "gameIDs", "games"))
        games = int(games)
    else:
        features, signs, phases, labels, gameIDs, games = extract(pgnPath)
        np.savez_compressed(cache, features = features, signs = signs, phases = phases, labels = labels, gameIDs = gameIDs, games = games)

    # Split by game, not by position: positions from one game share a label and would leak across the split
    rng = np.random.default_rng(SEED)
    testGames = rng.random(games) < TEST_FRACTION
    isTest = testGames[gameIDs]
    train = Dataset(features[~isTest], signs[~isTest], phases[~isTest], labels[~isTest])
    test = Dataset(features[isTest], signs[isTest], phases[isTest], labels[isTest])
    print(f"{games} games, {len(labels)} quiet positions: {len(train.labels)} train, {len(test.labels)} test")
    print(f"Results: {np.mean(labels == 1):.1%} White wins, {np.mean(labels == 0.5):.1%} draws, {np.mean(labels == 0):.1%} Black wins")

    mg, eg = initialWeights()
    K = fitK(train, mg, eg)
    constant = float(np.mean(train.labels))
    rows = [("Constant (predict the average result)", float(np.mean((constant - train.labels) ** 2)), float(np.mean((constant - test.labels) ** 2)))]
    materialMg, materialEg = materialWeights()
    rows.append(("Material only (P=100 N=320 B=330 R=500 Q=900)", train.mse(materialMg, materialEg, K), test.mse(materialMg, materialEg, K)))
    rows.append(("Hand-written PST (Simplified Evaluation Function)", train.mse(mg, eg, K), test.mse(mg, eg, K)))
    print(f"K = {K:.4f}")

    mg, eg, bestStep = tune(train, test, mg, eg, K)
    # Report the weights as they are written (rounded to whole centipawns)
    mgValue, mgTable = decompose(mg)
    egValue, egTable = decompose(eg)
    mg = np.array([mgValue[p] + mgTable[p][sq] for p in PIECES for sq in range(64)], dtype = np.float64)
    eg = np.array([egValue[p] + egTable[p][sq] for p in PIECES for sq in range(64)], dtype = np.float64)
    rows.append((f"Texel-tuned PST (best step {bestStep})", train.mse(mg, eg, K), test.mse(mg, eg, K)))

    print(f"\n{'Evaluation':52s} {'Train MSE':>10s} {'Test MSE':>10s}")
    for name, trainMse, testMse in rows:
        print(f"{name:52s} {trainMse:10.6f} {testMse:10.6f}")

    header = f"""
Evaluation weights in centipawns. Tables are from White's point of view, rank 8 first,
so index = row * 8 + col matches GameState.board; Black's pieces read them mirrored.

Generated by tuning/texel.py: Texel-tuned from {len(labels)} quiet positions in {games} games,
starting from Tomasz Michniewski's "Simplified Evaluation Function". K = {K:.4f},
held-out MSE {rows[2][2]:.6f} (hand-written) -> {rows[-1][2]:.6f} (tuned).
"""
    writeParams(mg, eg, header)
    print(f"\nWrote {PARAMS_PATH}")


if __name__ == "__main__":
    main()
