"""
Evaluation tests: colour symmetry, phase tapering, and the side-to-move sign.
"""

import pytest
from ChessGame.ChessEngine import GameState
from ChessGame.ChessAI import evaluate
from ChessGame.Evaluation import evaluateWhite, squareScores, MAX_PHASE
from ChessGame.EvalParams import mgValue, egValue, mgTable, egTable

KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"


# Flip the board top to bottom and swap colours: the same position with the roles reversed
def mirrorFen(fen):
    placement, side = fen.split()[:2]
    ranks = placement.split("/")[::-1]
    return "/".join(rank.swapcase() for rank in ranks) + (" b" if side == "w" else " w") + " - - 0 1"


def score(fen):
    return evaluateWhite(GameState.fromFen(fen).board)


def test_start_position_is_level():
    assert evaluateWhite(GameState().board) == 0


@pytest.mark.parametrize("fen", [
    KIWIPETE,
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 0 1",
    "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1",
], ids = ["kiwipete", "position3", "italian", "kp-endgame"])
def test_colour_symmetry(fen):
    assert score(mirrorFen(fen)) == -score(fen)


def test_side_to_move_sign():
    gs = GameState.fromFen(KIWIPETE)
    white = evaluate(gs)
    gs.whiteToMove = False
    assert evaluate(gs) == -white


def test_extra_queen_is_worth_about_a_queen():
    assert 700 < score("4k3/8/8/8/8/8/8/3QK3 w - - 0 1") < 1300


def test_bare_kings_use_endgame_table():
    # No pieces besides kings: phase 0, so only the endgame weights count
    fen = "8/8/8/3k4/8/8/8/K7 w - - 0 1"
    expected = (egValue["K"] + egTable["K"][7 * 8 + 0]) - (egValue["K"] + egTable["K"][(7 - 3) * 8 + 3])
    assert score(fen) == expected


def test_full_material_uses_midgame_table():
    # Starting material is phase 24, so swapping the king and g1 knight changes the score by midgame table differences only
    gs = GameState()
    gs.board[7][4], gs.board[7][6] = "wN", "wK"
    e1, g1 = 7 * 8 + 4, 7 * 8 + 6
    assert evaluateWhite(gs.board) == mgTable["K"][g1] - mgTable["K"][e1] + mgTable["N"][e1] - mgTable["N"][g1]


def test_tables_are_complete():
    for table in (mgTable, egTable):
        assert set(table) == set("PNBRQK")
        assert all(len(values) == 64 for values in table.values())
    assert set(mgValue) == set(egValue) == set("PNBRQK")
    assert len(squareScores) == 12 and MAX_PHASE == 24
