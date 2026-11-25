"""
Search benchmark: the per-release dashboard numbers that don't need games.

    python match/bench.py [--time 1.0] [--depth 6] [--disable SEE ...] [--enable-only SEE ...]
    pypy   match/bench.py ...            # compare interpreters

Runs a fixed set of positions (the 24 openings plus every 8th tactics-suite position) twice:
  - fixed time per position: nodes/s and completed depth (what the engine gets in a real game)
  - fixed depth: nodes and time to reach it (search efficiency, independent of speed)
and reports transposition table hit/cutoff rates, the share of fail-high nodes that cut off on the
first move tried (move ordering quality), the share of quiescence nodes, and peak memory.
--enable-only switches off every feature not named, for baseline-plus-one-feature comparisons.
"""

import argparse
import os
import platform
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ChessGame.ChessEngine import GameState
from ChessGame.ChessAI import Searcher, FEATURES

HERE = os.path.dirname(os.path.abspath(__file__))


def positions():
    fens = []
    with open(os.path.join(HERE, "openings.epd")) as f:
        fens += [" ".join(line.split()[:4]) + " 0 1" for line in f if line.strip()]
    with open(os.path.join(HERE, "tactics.epd")) as f:
        fens += [line.split(" bm ")[0].strip() for line in f if " bm " in line][::8]
    return fens


def peakMemoryMB():
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 # KB on Linux
    except ImportError:
        pass
    try:
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        getProcess = ctypes.windll.kernel32.GetCurrentProcess
        getProcess.restype = wintypes.HANDLE # A pointer-sized pseudo-handle, not a 32-bit int
        getInfo = ctypes.windll.psapi.GetProcessMemoryInfo
        getInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not getInfo(getProcess(), ctypes.byref(counters), counters.cb):
            return float("nan")
        return counters.PeakWorkingSetSize / 2 ** 20
    except Exception:
        return float("nan")


def run(fens, disabled, timeLimit, maxDepth):
    totals = dict(nodes = 0, qnodes = 0, seconds = 0.0, depth = 0, probes = 0, hits = 0, ttCuts = 0, cuts = 0, firstCuts = 0)
    for i, fen in enumerate(fens):
        random.seed(i) # The search shuffles root moves; fix it so runs are repeatable
        searcher = Searcher(timeLimit = timeLimit, maxDepth = maxDepth, disabled = disabled)
        start = time.perf_counter()
        searcher.search(GameState.fromFen(fen))
        totals["seconds"] += time.perf_counter() - start
        totals["nodes"] += searcher.nodes
        totals["qnodes"] += searcher.qnodes
        totals["depth"] += searcher.depthReached
        totals["probes"] += searcher.ttProbes
        totals["hits"] += searcher.ttHits
        totals["ttCuts"] += searcher.ttCutoffs
        totals["cuts"] += searcher.betaCutoffs
        totals["firstCuts"] += searcher.firstMoveCutoffs
    return totals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--time", type = float, default = 1.0, help = "seconds per position for the fixed-time run")
    parser.add_argument("--depth", type = int, default = 6, help = "depth for the fixed-depth run")
    parser.add_argument("--disable", nargs = "*", default = [], choices = FEATURES)
    parser.add_argument("--enable-only", nargs = "*", choices = FEATURES)
    args = parser.parse_args()
    disabled = tuple(f for f in FEATURES if f not in args.enable_only) if args.enable_only is not None else tuple(args.disable)

    fens = positions()
    run(fens[:4], disabled, 1.0, 64) # Warm-up, so PyPy's JIT has compiled the search before timing
    fixedTime = run(fens, disabled, args.time, 64)
    fixedDepth = run(fens, disabled, float("inf"), args.depth)
    n = len(fens)
    on = [f for f in FEATURES if f not in disabled]

    print(f"{platform.python_implementation()} {platform.python_version()}, {n} positions, features on: {', '.join(on) or 'none'}")
    print(f"  fixed time {args.time}s: {fixedTime['nodes'] / fixedTime['seconds']:,.0f} nodes/s, average depth {fixedTime['depth'] / n:.2f}")
    print(f"  fixed depth {args.depth}: {fixedDepth['nodes'] / n:,.0f} nodes/position, {fixedDepth['seconds'] / n:.3f}s/position")
    d = fixedDepth
    print(f"  TT hit rate {d['hits'] / max(1, d['probes']):.1%}, TT cutoff rate {d['ttCuts'] / max(1, d['probes']):.1%}")
    print(f"  first-move cutoffs {d['firstCuts'] / max(1, d['cuts']):.1%} of {d['cuts']:,} fail-highs, quiescence {d['qnodes'] / max(1, d['nodes']):.1%} of nodes")
    print(f"  peak memory {peakMemoryMB():.0f} MB")


if __name__ == "__main__":
    main()
