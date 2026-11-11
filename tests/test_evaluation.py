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


from ChessGame.Evaluation import evalTerms
from ChessGame.EvalParams import termNames


def terms(fen):
    counts = evalTerms(GameState.fromFen(fen).board)
    return {name : count for name, count in zip(termNames, counts) if count}


def test_start_position_terms():
    # Both kings have their full pawn shield, nothing else applies
    assert terms("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1") == {}


def test_passed_pawn_ranks():
    # White d6 is passed on its 6th rank; Black's a3 is passed on its 6th rank too, so they cancel.
    # The h-pawns face each other on one file, so neither is passed
    t = terms("4k3/7p/3P4/8/8/p7/7P/4K3 w - - 0 1")
    assert "passed6" not in t
    t = terms("4k3/7p/3P4/8/8/8/7P/4K3 w - - 0 1")
    assert t["passed6"] == 1


def test_passed_pawn_blocked_by_adjacent_file():
    # Black e7 is ahead of White d5 on an adjacent file, so d5 isn't passed. d5 is ahead of e7 for Black too
    t = terms("4k3/4p3/8/3P4/8/8/8/4K3 w - - 0 1")
    assert "passed5" not in t and "passed2" not in t
    # Black e4 is behind White d5, and d5 is behind e4 from Black's side: both are passed (White 5th, Black 5th)
    t = terms("4k3/8/8/3P4/4p3/8/8/4K3 w - - 0 1")
    assert "passed5" not in t # +1 and -1 cancel


def test_doubled_and_isolated():
    t = terms("4k3/8/8/8/8/3P4/3P4/4K3 w - - 0 1")
    assert t["doubled"] == 1 and t["isolated"] == 2


def test_bishop_pair_and_rook_files():
    t = terms("4k3/p7/8/8/8/8/1P6/R1B1KB1R w - - 0 1")
    assert t["bishopPair"] == 1
    assert t["rookHalfOpenFile"] == 1 # a-file: Black pawn only
    assert t["rookOpenFile"] == 1 # h-file: no pawns at all


def test_king_shield_and_open_files():
    # White king g1 with f2, g2 and h3: f2/g2 directly in front, h3 two ranks ahead. Black king e8, no pawns near
    t = terms("4k3/8/8/8/8/7P/5PP1/6K1 w - - 0 1")
    assert t["shield1"] == 2 and t["shield2"] == 1
    assert t["kingOpenFile"] == -3 # Black's d, e and f files have no Black pawns; White's are all covered
