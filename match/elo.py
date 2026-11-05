"""
Elo estimate with a 95% confidence interval from a cutechess PGN.

    python match/elo.py match/<file>.pgn [EngineName] [OpponentElo]

Elo difference from score s:  -400 * log10(1/s - 1)
The interval comes from the per-game score variance (wins/draws/losses as a trinomial),
mapped through the same formula, the same method cutechess-cli uses.
"""

import math
import re
import sys


def results(pgnPath, engine):
    wins = draws = losses = 0
    with open(pgnPath) as f:
        text = f.read()
    for game in re.split(r'\n\n(?=\[Event )', text):
        white = re.search(r'\[White "([^"]*)"\]', game)
        result = re.search(r'\[Result "([^"]*)"\]', game)
        if not white or not result or result.group(1) == "*":
            continue
        engineIsWhite = white.group(1) == engine
        if result.group(1) == "1/2-1/2":
            draws += 1
        elif (result.group(1) == "1-0") == engineIsWhite:
            wins += 1
        else:
            losses += 1
    return wins, draws, losses


def eloDiff(score):
    return -400 * math.log10(1 / score - 1)


def estimate(wins, draws, losses):
    n = wins + draws + losses
    score = (wins + draws / 2) / n
    if score in (0, 1):
        return score, None, None, None # Unbounded: a clean sweep says only "much weaker/stronger"
    variance = (wins * (1 - score) ** 2 + draws * (0.5 - score) ** 2 + losses * score ** 2) / n
    margin = 1.959964 * math.sqrt(variance / n)
    low, high = max(score - margin, 1e-9), min(score + margin, 1 - 1e-9)
    return score, eloDiff(score), eloDiff(low), eloDiff(high)


if __name__ == "__main__":
    pgn = sys.argv[1]
    engine = sys.argv[2] if len(sys.argv) > 2 else "ChessGame"
    anchor = float(sys.argv[3]) if len(sys.argv) > 3 else None

    w, d, l = results(pgn, engine)
    score, diff, low, high = estimate(w, d, l)
    print(f"Games {w + d + l}: +{w} ={d} -{l}, score {100 * score:.1f}%")
    if diff is None:
        print("Score is 0% or 100%: Elo difference is unbounded, play a closer opponent")
    else:
        print(f"Elo difference: {diff:+.0f}  (95% CI {low:+.0f} to {high:+.0f})")
        if anchor is not None:
            print(f"Estimated Elo:  {anchor + diff:.0f}  (95% CI {anchor + low:.0f} to {anchor + high:.0f})")
