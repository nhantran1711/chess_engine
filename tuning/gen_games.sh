#!/usr/bin/env bash
# Training games for Texel tuning: Stockfish at three limited strengths in a round robin,
# starting from random 8-ply openings. Mixed strengths give decisive results across many kinds of positions.
#
#   CUTECHESS=/path/to/cutechess-cli STOCKFISH=/path/to/stockfish tuning/gen_games.sh [rounds] [out.pgn]

set -euo pipefail
cd "$(dirname "$0")/.."

ROUNDS="${1:-1000}"
OUT="${2:-tuning/games.pgn}"

engine() {
    echo -engine name="SF$1" cmd="${STOCKFISH:?set STOCKFISH}" proto=uci \
        option.UCI_LimitStrength=true option.UCI_Elo="$1" option.Threads=1 option.Hash=16
}

"${CUTECHESS:?set CUTECHESS}" \
    $(engine 1400) $(engine 1800) $(engine 2200) \
    -tournament round-robin -each tc=inf nodes=10000 \
    -openings file=tuning/openings_random8.epd format=epd order=sequential \
    -rounds "$ROUNDS" -games 2 -repeat -concurrency 6 \
    -draw movenumber=40 movecount=8 score=10 \
    -resign movecount=4 score=1000 twosided=true \
    -pgnout "$OUT" min -recover
