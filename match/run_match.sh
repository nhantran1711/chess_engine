#!/usr/bin/env bash
# Gauntlet vs Stockfish with limited strength, using cutechess-cli.
#
#   CUTECHESS=/path/to/cutechess-cli STOCKFISH=/path/to/stockfish PYTHON=/path/to/python \
#       match/run_match.sh [UCI_Elo] [rounds]
#
# UCI_Elo is calibrated by Stockfish at 120s+1s against CCRL 40/4, so that's the time control used.
# Each round plays one opening from openings.epd with both colours.

set -euo pipefail
cd "$(dirname "$0")/.."

ELO="${1:-1320}"
ROUNDS="${2:-24}"
NAME="sf${ELO}_120+1"

"${CUTECHESS:?set CUTECHESS}" \
    -engine name=ChessGame cmd="${PYTHON:-python3}" arg=uci.py dir="$PWD" proto=uci \
    -engine name="Stockfish-Elo${ELO}" cmd="${STOCKFISH:?set STOCKFISH}" proto=uci \
        option.UCI_LimitStrength=true option.UCI_Elo="$ELO" option.Threads=1 option.Hash=16 \
    -each tc=120+1 \
    -openings file=match/openings.epd format=epd order=sequential -repeat \
    -rounds "$ROUNDS" -games 2 -concurrency 3 \
    -resign movecount=3 score=1000 twosided=true \
    -pgnout "match/${NAME}.pgn" -recover -ratinginterval 6 \
    | tee "match/${NAME}.log"

"${PYTHON:-python3}" match/elo.py "match/${NAME}.pgn" ChessGame "$ELO"
