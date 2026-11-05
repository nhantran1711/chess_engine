"""
Random openings for generating tuning games: a few random legal plies from the start position,
so games cover many different structures instead of repeating the same book lines.

    python tuning/gen_openings.py <count> <plies> <out.epd>
"""

import random
import sys
import chess

count, plies, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
random.seed(2026)
seen = set()
with open(out, "w") as f:
    while len(seen) < count:
        board = chess.Board()
        for _ in range(plies):
            if board.is_game_over():
                break
            board.push(random.choice(list(board.legal_moves)))
        if board.is_game_over():
            continue
        epd = board.epd()
        if epd not in seen:
            seen.add(epd)
            f.write(epd + "\n")
