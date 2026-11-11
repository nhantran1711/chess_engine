"""
Static exchange evaluation tests: known exchanges, x-ray recaptures through the used squares,
the king only recapturing on an undefended square, promotions and en passant.
"""

import pytest
from ChessGame.ChessEngine import GameState
from ChessGame.SEE import see, SEE_VALUE

P, N, B, R, Q = (SEE_VALUE[x] for x in "PNBRQ")


def seeOf(fen, uci):
    gs = GameState.fromFen(fen)
    move = next(m for m in gs.getValidateMoves() if m.getChessNotation() + m.promotionSuffix() == uci)
    return see(gs, move)


@pytest.mark.parametrize("fen, move, expected", [
    # Chess programming wiki examples: an undefended pawn, and a pawn defended twice with x-rays behind
    ("1k1r4/1pp4p/p7/4p3/8/P5P1/1PP4P/2K1R3 w - - 0 1", "e1e5", P),
    ("1k1r3q/1ppn3p/p4b2/4p3/8/P2N2P1/1PP1R1BP/2K1Q3 w - - 0 1", "d3e5", P - N),
    # Queen takes a pawn defended by a pawn
    ("4k3/8/2p5/3p4/8/8/3Q4/4K3 w - - 0 1", "d2d5", P - Q),
    # Equal trade: rook takes rook, recaptured by rook
    ("3rk3/3r4/8/8/8/8/8/3RK3 w - - 0 1", "d1d7", R - R),
    # X-ray: the second rook behind the first wins the knight back (-80 instead of -400)
    ("4k3/4n3/8/3p4/8/8/3R4/3RK3 w - - 0 1", "d2d5", P - R + N),
    ("4k3/4n3/8/3p4/8/8/8/3RK3 w - - 0 1", "d1d5", P - R), # Same without the second rook
    # The king may recapture only when the square is no longer defended
    ("8/8/8/3k4/4p3/8/8/4RK2 w - - 0 1", "e1e4", P - R),
    ("8/8/8/3k4/4p3/8/8/4RK1Q w - - 0 1", "e1e4", P), # Queen h1 defends e4, so Kxe4 is illegal
])
def test_known_exchanges(fen, move, expected):
    assert seeOf(fen, move) == expected


def test_promotion_counts_the_new_piece():
    assert seeOf("8/4P3/8/8/8/8/k7/4K3 w - - 0 1", "e7e8q") == Q - P


def test_en_passant_wins_a_pawn():
    assert seeOf("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "e5d6") == P


def test_capture_of_bigger_piece_never_negative():
    # Pawn takes a defended queen: wins at least queen minus pawn
    assert seeOf("4k3/2p5/3q4/4P3/8/8/8/4K3 w - - 0 1", "e5d6") == Q - P
