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
    searcher = Searcher(timeLimit = 1000, useQuiescence = False, usePruning = False)
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
    before = ([row[:] for row in gs.board], gs.whiteToMove, gs.enpassantPossbile, len(gs.moveLogs))
    searcher = Searcher(timeLimit = 0.3)
    move = searcher.search(gs)
    assert move in gs.getValidateMoves()
    assert ([row[:] for row in gs.board], gs.whiteToMove, gs.enpassantPossbile, len(gs.moveLogs)) == before


def test_no_legal_moves_returns_none():
    stalemate = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
    assert Searcher(timeLimit = 1).search(GameState.fromFen(stalemate)) is None


# Iterative deepening reuses table entries from shallower iterations; the final score must still be exact.
# Depth 4 is the shallowest where transpositions cause cutoffs (needs two moves by the same side to swap)
@pytest.mark.slow
@pytest.mark.parametrize("fen, depth", [
    ("4k3/8/2p5/3p4/8/8/3Q4/4K3 w - - 0 1", 4),
    ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", 4),
], ids = ["defended-pawn", "position3"])
def test_transposition_table_preserves_minimax_score(fen, depth):
    searcher = Searcher(timeLimit = 1000, maxDepth = depth, useQuiescence = False, usePruning = False)
    searcher.search(GameState.fromFen(fen))
    assert searcher.ttCutoffs > 0
    assert searcher.bestScore == minimax(GameState.fromFen(fen), depth)


def test_transposition_table_mate_score_across_searches():
    # Searching twice reuses mate scores stored relative to their node; the distance to mate must not drift
    searcher = Searcher(timeLimit = 60)
    gs = GameState.fromFen("7k/8/8/8/8/8/R7/1R4K1 w - - 0 1")
    for _ in range(2):
        searcher.search(gs)
        assert searcher.bestScore == CHECKMATE - 3


def play(gs, *ucis):
    for text in ucis:
        gs.makeMoves(next(m for m in gs.getValidateMoves() if uci(m) == text))


def test_repetition_detected_and_undone():
    gs = GameState()
    play(gs, "g1f3", "g8f6", "f3g1")
    assert not gs.isRepetition()
    play(gs, "f6g8") # Back to the starting position
    assert gs.isRepetition() and gs.halfmoveClock == 4
    gs.undoMove()
    assert not gs.isRepetition() and gs.halfmoveClock == 3


def test_pawn_move_resets_halfmove_clock():
    gs = GameState()
    play(gs, "g1f3", "e7e5")
    assert gs.halfmoveClock == 0
    play(gs, "f3g1", "b8c6", "g1f3", "c6b8") # Can't match positions from before the pawn move
    assert gs.halfmoveClock == 4 and not gs.isRepetition()


def test_fifty_move_rule():
    gs = GameState.fromFen("8/8/4k3/8/8/4K3/8/7R w - - 99 80")
    assert not gs.isDraw()
    play(gs, "h1h2")
    assert gs.isDraw()


def test_search_scores_repeated_position_as_draw():
    gs = GameState()
    play(gs, "g1f3", "g8f6", "f3g1", "f6g8")
    assert Searcher().negamax(gs, 3, -CHECKMATE - 1, CHECKMATE + 1, 1) == STALEMATE


# White is a rook down with only a king, but the fifty-move counter is at 99: any move draws
def test_losing_side_scores_fifty_move_draw():
    gs = GameState.fromFen("6k1/8/8/8/8/1r6/8/K7 w - - 99 120")
    searcher = Searcher(timeLimit = 1e9, maxDepth = 3)
    searcher.search(gs)
    assert searcher.bestScore == STALEMATE


def test_null_move_restores_state():
    from ChessGame import Zobrist
    gs = GameState.fromFen("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3")
    before = ([row[:] for row in gs.board], gs.whiteToMove, gs.enpassantPossbile, gs.zobristKey, gs.halfmoveClock)
    gs.makeNullMove()
    assert not gs.whiteToMove and gs.enpassantPossbile == () and gs.zobristKey == Zobrist.computeKey(gs)
    play(gs, "g8f6") # A real move after the null move hashes correctly too
    assert gs.zobristKey == Zobrist.computeKey(gs)
    gs.undoMove()
    gs.undoMove()
    assert ([row[:] for row in gs.board], gs.whiteToMove, gs.enpassantPossbile, gs.zobristKey, gs.halfmoveClock) == before
