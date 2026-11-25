"""
Tapered evaluation, in centipawns from White's point of view.

Two parts, each scored once with midgame weights and once with endgame weights:
  - piece-square: every piece scores its material value plus a bonus for its square
  - positional terms (evalTerms): passed, doubled and isolated pawns, the pawn shield and open
    files around the king, the bishop pair, and rooks on open or half-open files

The two are blended by game phase, which counts the minor and major pieces left
(knight/bishop 1, rook 2, queen 4, 24 at the start):

    score = (mg * phase + eg * (24 - phase)) / 24

So the king hides behind its pawns while queens are on, and walks to the centre in the endgame.
The score is linear in the weights for a fixed position, which is what makes Texel tuning a regression.
tuning/texel.py calls evalTerms too, so the tuner and the engine always count the same things.
"""

from itertools import chain

from ChessGame.EvalParams import mgValue, egValue, mgTable, egTable, termNames, termMg, termEg

PHASE_WEIGHTS = {"P" : 0, "N" : 1, "B" : 1, "R" : 2, "Q" : 4, "K" : 0}
MAX_PHASE = 24
PASSED = 0 # termNames index of "passed2"; passed pawn on own rank k uses PASSED + k - 2
DOUBLED, ISOLATED, SHIELD1, SHIELD2, KING_OPEN_FILE, BISHOP_PAIR, ROOK_OPEN, ROOK_HALF_OPEN = range(6, 14)
NUM_TERMS = len(termNames)


# Black's pieces use the table flipped top to bottom, and count against White
def buildSquareScores():
    scores = {}
    for piece in "PNBRQK":
        white, black = [], []
        for sq in range(64):
            row, col = divmod(sq, 8)
            mirror = (7 - row) * 8 + col
            white.append((mgValue[piece] + mgTable[piece][sq], egValue[piece] + egTable[piece][sq]))
            black.append((-(mgValue[piece] + mgTable[piece][mirror]), -(egValue[piece] + egTable[piece][mirror])))
        scores["w" + piece] = white
        scores["b" + piece] = black
    return scores

squareScores = buildSquareScores()
piecePhase = {colour + piece : weight for piece, weight in PHASE_WEIGHTS.items() for colour in "wb"}
termWeights = [(termMg[name], termEg[name]) for name in termNames]


def evaluateWhite(board):
    mg = eg = phase = 0
    for sq, code in enumerate(chain.from_iterable(board)):
        if code != "--":
            pieceMg, pieceEg = squareScores[code][sq]
            mg += pieceMg
            eg += pieceEg
            phase += piecePhase[code]
    for count, (weightMg, weightEg) in zip(evalTerms(board), termWeights):
        if count:
            mg += count * weightMg
            eg += count * weightEg
    phase = min(phase, MAX_PHASE) # Early promotions can push it past the starting total
    total = mg * phase + eg * (MAX_PHASE - phase)
    # Round towards zero, not down, so a position and its colour-mirror score exactly opposite
    return total // MAX_PHASE if total >= 0 else -(-total // MAX_PHASE)


# Counts for each positional term, White's minus Black's, in termNames order
def evalTerms(board):
    counts = [0] * NUM_TERMS
    # Pawn rows per file for each side, plus where the kings, bishops and rooks are
    pawns = {"w" : [[] for _ in range(8)], "b" : [[] for _ in range(8)]}
    kings, rooks = {}, {"w" : [], "b" : []}
    bishops = {"w" : 0, "b" : 0}
    for r, row in enumerate(board):
        for c, code in enumerate(row):
            if code == "--":
                continue
            colour, piece = code[0], code[1]
            if piece == "P":
                pawns[colour][c].append(r)
            elif piece == "K":
                kings[colour] = (r, c)
            elif piece == "R":
                rooks[colour].append(c)
            elif piece == "B":
                bishops[colour] += 1

    for colour, sign, enemy in (("w", 1, "b"), ("b", -1, "w")):
        own, opp = pawns[colour], pawns[enemy]
        for c in range(8):
            rows = own[c]
            if not rows:
                continue
            if len(rows) > 1:
                counts[DOUBLED] += sign * (len(rows) - 1)
            if (c == 0 or not own[c - 1]) and (c == 7 or not own[c + 1]):
                counts[ISOLATED] += sign * len(rows)
            for r in rows:
                # Passed: no enemy pawn ahead of it on its own or an adjacent file. White moves towards row 0
                blocked = False
                for f in (c - 1, c, c + 1):
                    if 0 <= f < 8:
                        for er in opp[f]:
                            if (er < r) if colour == "w" else (er > r):
                                blocked = True
                                break
                    if blocked:
                        break
                if not blocked:
                    rank = 8 - r if colour == "w" else r + 1 # The pawn's rank from its own side, 2..7
                    counts[PASSED + rank - 2] += sign

        if colour in kings:
            kr, kc = kings[colour]
            ahead = -1 if colour == "w" else 1
            for f in (kc - 1, kc, kc + 1):
                if 0 <= f < 8:
                    if kr + ahead in own[f]:
                        counts[SHIELD1] += sign
                    elif kr + 2 * ahead in own[f]:
                        counts[SHIELD2] += sign
                    if not own[f]:
                        counts[KING_OPEN_FILE] += sign

        if bishops[colour] >= 2:
            counts[BISHOP_PAIR] += sign
        for c in rooks[colour]:
            if not own[c]:
                counts[ROOK_OPEN if not opp[c] else ROOK_HALF_OPEN] += sign
    return counts
