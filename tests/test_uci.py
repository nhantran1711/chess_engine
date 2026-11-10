"""
UCI protocol tests: command handling, move parsing, time management, and a full session
against the real process to make sure nothing but protocol output reaches stdout.
"""

import io
import os
import subprocess
import sys
import time
from ChessGame.UCI import UCIEngine, scoreToUci, allocateTime
from ChessGame.ChessAI import CHECKMATE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(engine, *commands):
    for command in commands:
        engine.handle(command)
    if engine.searchThread is not None:
        engine.searchThread.join()
    return engine.out.getvalue().splitlines()


def newEngine():
    return UCIEngine(out = io.StringIO())


def bestmove(lines):
    return [line for line in lines if line.startswith("bestmove")][-1].split()[1]


def test_handshake():
    lines = run(newEngine(), "uci", "isready")
    assert lines[0].startswith("id name")
    assert lines[1].startswith("id author")
    assert lines[2:] == ["uciok", "readyok"]


def test_position_with_castling_en_passant_and_underpromotion():
    engine = newEngine()
    run(engine, "position startpos moves e2e4 g8f6 e4e5 d7d5 e5d6 e7e6 g1f3 f8e7 f1c4 e8g8 e1g1")
    board = engine.gamestate.board
    assert board[3][3] == "--" # d5 pawn taken en passant
    assert board[0][6] == "bK" and board[0][5] == "bR" # Black castled short
    assert board[7][6] == "wK" and board[7][5] == "wR" # White castled short

    run(engine, "position fen 8/P7/8/8/8/8/8/k6K w - - 0 1 moves a7a8n")
    assert engine.gamestate.board[0][0] == "wN"


def test_illegal_move_is_reported_not_played():
    engine = newEngine()
    lines = run(engine, "position startpos moves e2e5")
    assert lines == ["info string illegal move e2e5, ignoring the rest"]
    assert engine.gamestate.board[6][4] == "wP"


def test_go_depth_reports_info_and_legal_bestmove():
    lines = run(newEngine(), "position startpos moves e2e4", "go depth 2")
    infos = [line for line in lines if line.startswith("info depth")]
    assert [line.split()[2] for line in infos] == ["1", "2"]
    assert all(" score " in line and " pv " in line for line in infos)
    assert bestmove(lines) in {"a7a6", "a7a5", "b7b6", "b7b5", "c7c6", "c7c5", "d7d6", "d7d5", "e7e6", "e7e5",
                               "f7f6", "f7f5", "g7g6", "g7g5", "h7h6", "h7h5", "b8a6", "b8c6", "g8f6", "g8h6"}


def test_mate_reported_in_moves():
    lines = run(newEngine(), "position fen 7k/8/8/8/8/8/R7/1R4K1 w - - 0 1", "go depth 5")
    assert "score mate 2" in lines[-2]
    assert bestmove(lines) in ("a2a7", "b1b7")


def test_no_legal_moves_gives_null_move():
    lines = run(newEngine(), "position fen 7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", "go depth 3")
    assert lines == ["bestmove 0000"]


def test_infinite_waits_for_stop():
    engine = newEngine()
    run(engine, "position startpos")
    engine.handle("go infinite")
    time.sleep(0.5)
    assert "bestmove" not in engine.out.getvalue()
    engine.handle("isready") # Must be answered mid-search
    assert "readyok" in engine.out.getvalue()
    engine.handle("stop")
    assert engine.out.getvalue().splitlines()[-1].startswith("bestmove")


def test_movetime_is_respected():
    engine = newEngine()
    start = time.time()
    run(engine, "position startpos", "go movetime 300")
    assert time.time() - start < 0.6


def test_score_conversion():
    assert scoreToUci(300) == "cp 300"
    assert scoreToUci(-15) == "cp -15"
    assert scoreToUci(CHECKMATE - 1) == "mate 1" # We mate on ply 1
    assert scoreToUci(CHECKMATE - 3) == "mate 2"
    assert scoreToUci(-(CHECKMATE - 2)) == "mate -1" # We get mated on ply 2
    assert scoreToUci(-(CHECKMATE - 4)) == "mate -2"


def test_time_allocation():
    assert abs(allocateTime({"movetime" : 1000}, True) - 0.95) < 1e-9
    assert allocateTime({"wtime" : 60000, "btime" : 1000}, True) > allocateTime({"wtime" : 60000, "btime" : 1000}, False)
    assert allocateTime({"wtime" : 300}, True) <= 0.15 # Never more than half the remaining clock
    assert allocateTime({"depth" : 3}, True) is None


def test_real_process_session():
    session = "uci\nisready\nposition startpos moves d2d4\ngo depth 2\nisready\nquit\n"
    result = subprocess.run([sys.executable, "uci.py"], input = session, capture_output = True, text = True, cwd = ROOT, timeout = 60)
    lines = result.stdout.splitlines()
    assert result.returncode == 0
    assert "uciok" in lines and lines.count("readyok") == 2
    # quit still lets bestmove out. The second isready may be answered before or after the search ends
    assert sum(line.startswith("bestmove") for line in lines) == 1
    # Every line must be a UCI message so GUIs can parse the stream
    assert all(line.split()[0] in ("id", "uciok", "readyok", "info", "bestmove") for line in lines)
