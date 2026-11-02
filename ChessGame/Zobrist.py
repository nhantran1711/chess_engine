"""
Zobrist hashing: every (piece, square), side to move, castling rights state and en passant file
gets a random 64-bit key. A position's hash is the XOR of the keys of everything in it, so a move
updates the hash with a few XORs instead of rehashing the whole board.
"""

import random

# Fixed seed so hashes are reproducible between runs
_rng = random.Random(2026)

def _key():
    return _rng.getrandbits(64)

pieceKeys = {colour + piece : [_key() for _ in range(64)] for colour in "wb" for piece in "PNBRQK"}
blackToMoveKey = _key()
castlingKeys = [_key() for _ in range(16)] # One per combination of the 4 rights
enpassantKeys = [_key() for _ in range(8)] # One per file


def castlingKey(rights):
    return castlingKeys[rights.wks | rights.bks << 1 | rights.wqs << 2 | rights.bqs << 3]

def enpassantKey(enpassantSquare):
    return enpassantKeys[enpassantSquare[1]] if enpassantSquare else 0

def pieceKey(piece, r, c):
    return pieceKeys[piece][r * 8 + c]


# Hash a position from scratch, used at setup and to test the incremental updates
def computeKey(gamestate):
    key = 0
    for r in range(8):
        for c in range(8):
            sq = gamestate.board[r][c]
            if sq != "--":
                key ^= pieceKey(sq, r, c)
    if not gamestate.whiteToMove:
        key ^= blackToMoveKey
    key ^= castlingKey(gamestate.currentCastlingRight)
    key ^= enpassantKey(gamestate.enpassantPossbile)
    return key
