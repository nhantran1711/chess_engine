"""
Perft (performance test): counts leaf nodes of the legal move tree to a given depth.
Comparing against published counts is the standard way to validate move generation.

Usage:
    python -m ChessGame.Perft "<fen>" <depth>     # prints per-move divide + total
"""

import sys
from ChessGame.ChessEngine import GameState


def perft(gs, depth):
    if depth == 0:
        return 1
    
    moves = gs.getValidateMoves()

    if depth == 1:
        return len(moves)
    
    nodes = 0
    for move in moves:
        gs.makeMoves(move)

        nodes += perft(gs, depth - 1)

        gs.undoMove()
    return nodes


# Per-root-move node counts, for diffing against a reference engine (e.g. Stockfish "go perft")
def divide(gs, depth):
    res = {}

    for move in gs.getValidateMoves():
        gs.makeMoves(move)
        
        res[move.getChessNotation() + move.promotionSuffix()] = perft(gs, depth - 1)
        
        gs.undoMove()
    return res


if __name__ == "__main__":
    fen, depth = sys.argv[1], int(sys.argv[2])

    counts = divide(GameState.fromFen(fen), depth)

    for notation in sorted(counts):
        print(f"{notation}: {counts[notation]}")
    
    print(f"\nNodes searched: {sum(counts.values())}")
