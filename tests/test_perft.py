"""
Perft validation of move generation against published node counts.
Reference: https://www.chessprogramming.org/Perft_Results

    pytest                  # fast depths only
    pytest --runslow        # also the deeper (slow) depths
"""

import pytest
from ChessGame.ChessEngine import GameState
from ChessGame.Perft import perft

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
POSITION_3 = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
POSITION_4 = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"
POSITION_4_MIRRORED = "r2q1rk1/pP1p2pp/Q4n2/bbp1p3/Np6/1B3NBn/pPPP1PPP/R3K2R b KQ - 0 1"
POSITION_5 = "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8"
POSITION_6 = "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10"

# (name, fen, depth, expected nodes)
FAST = [
    ("start", START, 1, 20),
    ("start", START, 2, 400),
    ("start", START, 3, 8902),
    ("kiwipete", KIWIPETE, 1, 48),
    ("kiwipete", KIWIPETE, 2, 2039),
    ("position3", POSITION_3, 1, 14),
    ("position3", POSITION_3, 2, 191),
    ("position3", POSITION_3, 3, 2812),
    ("position4", POSITION_4, 1, 6),
    ("position4", POSITION_4, 2, 264),
    ("position4", POSITION_4, 3, 9467),
    ("position4_mirrored", POSITION_4_MIRRORED, 1, 6),
    ("position4_mirrored", POSITION_4_MIRRORED, 2, 264),
    ("position4_mirrored", POSITION_4_MIRRORED, 3, 9467),
    ("position5", POSITION_5, 1, 44),
    ("position5", POSITION_5, 2, 1486),
    ("position6", POSITION_6, 1, 46),
    ("position6", POSITION_6, 2, 2079),
]

SLOW = [
    ("start", START, 4, 197281),
    ("kiwipete", KIWIPETE, 3, 97862),
    ("position3", POSITION_3, 4, 43238),
    ("position3", POSITION_3, 5, 674624),
    ("position4", POSITION_4, 4, 422333),
    ("position5", POSITION_5, 3, 62379),
    ("position6", POSITION_6, 3, 89890),
]


def ids(cases):
    return [f"{name}-d{depth}" for name, _, depth, _ in cases]


@pytest.mark.parametrize("name, fen, depth, expected", FAST, ids = ids(FAST))
def test_perft(name, fen, depth, expected):
    assert perft(GameState.fromFen(fen), depth) == expected


@pytest.mark.slow
@pytest.mark.parametrize("name, fen, depth, expected", SLOW, ids = ids(SLOW))
def test_perft_deep(name, fen, depth, expected):
    assert perft(GameState.fromFen(fen), depth) == expected


def snapshot(gs):
    rights = gs.currentCastlingRight
    return (
        gs.board.tobytes(), gs.whiteToMove, gs.whiteKingLocation, gs.blackKingLocation,
        gs.enpassantPossbile, (rights.wks, rights.bks, rights.wqs, rights.bqs),
    )


# Every makeMoves/undoMove pair must restore the exact prior state
@pytest.mark.parametrize("fen", [START, KIWIPETE, POSITION_3, POSITION_4, POSITION_5], ids = ["start", "kiwipete", "position3", "position4", "position5"])
def test_make_undo_restores_state(fen):
    gs = GameState.fromFen(fen)

    def walk(depth):
        if depth == 0:
            return
        before = snapshot(gs)
        for move in gs.getValidateMoves():
            gs.makeMoves(move)
            walk(depth - 1)
            gs.undoMove()
            assert snapshot(gs) == before, f"state not restored after {move.getChessNotation()}{move.promotionSuffix()}"

    walk(2)


def test_fen_start_matches_default_constructor():
    assert snapshot(GameState.fromFen(START)) == snapshot(GameState())
