"""
Tapered piece-square evaluation, in centipawns from White's point of view.

Every piece scores its material value plus a bonus for its square, once with midgame weights
and once with endgame weights. The two are blended by game phase, which counts the minor
and major pieces left (knight/bishop 1, rook 2, queen 4, 24 at the start):

    score = (mg * phase + eg * (24 - phase)) / 24

So the king hides behind its pawns while queens are on, and walks to the centre in the endgame.
The score is linear in the weights for a fixed position, which is what makes Texel tuning a regression.
"""

from ChessGame.EvalParams import mgValue, egValue, mgTable, egTable

PHASE_WEIGHTS = {"P" : 0, "N" : 1, "B" : 1, "R" : 2, "Q" : 4, "K" : 0}
MAX_PHASE = 24


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


def evaluateWhite(board):
    mg = eg = phase = 0
    for sq, code in enumerate(board.ravel().tolist()):
        if code != "--":
            pieceMg, pieceEg = squareScores[code][sq]
            mg += pieceMg
            eg += pieceEg
            phase += piecePhase[code]
    phase = min(phase, MAX_PHASE) # Early promotions can push it past the starting total
    return (mg * phase + eg * (MAX_PHASE - phase)) // MAX_PHASE
