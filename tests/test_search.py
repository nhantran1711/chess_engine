"""
Search tests: alpha-beta must agree with plain minimax, find forced mates,
use quiescence to avoid horizon blunders, and leave the game state untouched.
"""

import pytest
from ChessGame.ChessEngine import GameState
from ChessGame.ChessAI import Searcher, evaluate, CHECKMATE, STALEMATE

KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"


def uci(move):
    return move.getChessNotation() + move.promotionSuffix()


def bestMove(fen, **kwargs):
    gs = GameState.fromFen(fen)
    return uci(Searcher(**kwargs).search(gs))


# Plain negamax with no pruning, the reference alpha-beta must match exactly
def minimax(gs, depth, ply = 0):
    moves = gs.getValidateMoves()
    if not moves:
        return -(CHECKMATE - ply) if gs.checkMate else STALEMATE
    if depth == 0:
        return evaluate(gs)
    best = -CHECKMATE - 1
    for move in moves:
        gs.makeMoves(move)
        best = max(best, -minimax(gs, depth - 1, ply + 1))
        gs.undoMove()
    return best


@pytest.mark.parametrize("fen, depth", [
    ("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 0 1", 2), # Scholar's mate threat
    ("4k3/8/2p5/3p4/8/8/3Q4/4K3 w - - 0 1", 3),
    ("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", 3),
], ids = ["scholars", "defended-pawn", "back-rank"])
def test_alphabeta_matches_minimax(fen, depth):
    searcher = Searcher(timeLimit = 1000, useQuiescence = False)
    gs = GameState.fromFen(fen)
    expected = minimax(gs, depth)
    assert searcher.negamax(gs, depth, -CHECKMATE - 1, CHECKMATE + 1, 0) == expected


def test_mate_in_one_white():
    assert bestMove("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", timeLimit = 30) == "a1a8"


def test_mate_in_one_black():
    assert bestMove("r5k1/8/8/8/8/8/5PPP/6K1 b - - 0 1", timeLimit = 30) == "a8a1"


def test_mate_in_two():
    searcher = Searcher(timeLimit = 60)
    move = searcher.search(GameState.fromFen("7k/8/8/8/8/8/R7/1R4K1 w - - 0 1"))
    assert uci(move) in ("a2a7", "b1b7")
    assert searcher.bestScore == CHECKMATE - 3 # Mate delivered on ply 3


def test_captures_hanging_queen():
    assert bestMove("4k3/8/8/3q4/8/8/3R4/4K3 w - - 0 1", maxDepth = 2, timeLimit = 30) == "d2d5"


def test_quiescence_avoids_defended_pawn():
    fen = "4k3/8/2p5/3p4/8/8/3Q4/4K3 w - - 0 1"
    # At depth 1 without quiescence, Qxd5 looks like winning a pawn (horizon effect)
    assert bestMove(fen, maxDepth = 1, useQuiescence = False, timeLimit = 30) == "d2d5"
    # Quiescence sees ...cxd5 recapturing the queen
    assert bestMove(fen, maxDepth = 1, timeLimit = 30) != "d2d5"


def test_timeout_restores_game_state():
    gs = GameState.fromFen(KIWIPETE)
    before = (gs.board.tobytes(), gs.whiteToMove, gs.enpassantPossbile, len(gs.moveLogs))
    searcher = Searcher(timeLimit = 0.3)
    move = searcher.search(gs)
    assert move in gs.getValidateMoves()
    assert (gs.board.tobytes(), gs.whiteToMove, gs.enpassantPossbile, len(gs.moveLogs)) == before


def test_no_legal_moves_returns_none():
    stalemate = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
    assert Searcher(timeLimit = 1).search(GameState.fromFen(stalemate)) is None
