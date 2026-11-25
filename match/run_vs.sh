#!/usr/bin/env bash
# Head-to-head between two versions of this engine, e.g. a change against the previous commit.
#
#   CUTECHESS=/path/to/cutechess-cli PYTHON=/path/to/python \
#       match/run_vs.sh <new_dir> <old_dir> [rounds=100] [tc=10+0.1] [name=vs]
#
# Each side is either a checkout containing uci.py (e.g. made with `git worktree add`) or a UCI
# executable such as engine/target/release/chessgame.
# Each round plays one opening from openings.epd with both colours; openings repeat after 24 rounds.

set -euo pipefail
cd "$(dirname "$0")/.."

# cutechess-cli arguments for one engine: a directory runs its uci.py, a file runs as is
engine_args() {
    if [ -d "$2" ]; then
        echo "-engine name=$1 cmd=${PYTHON:-python3} arg=uci.py dir=$(cd "$2" && pwd) proto=uci"
    else
        echo "-engine name=$1 cmd=$(cd "$(dirname "$2")" && pwd)/$(basename "$2") proto=uci"
    fi
}
ROUNDS="${3:-100}"
TC="${4:-10+0.1}"
NAME="${5:-vs}"

"${CUTECHESS:?set CUTECHESS}" \
    $(engine_args New "$1") \
    $(engine_args Old "$2") \
    -each tc="$TC" \
    -openings file=match/openings.epd format=epd order=sequential -repeat \
    -rounds "$ROUNDS" -games 2 -concurrency 3 \
    -resign movecount=3 score=1000 twosided=true \
    -draw movenumber=40 movecount=8 score=10 \
    -pgnout "match/${NAME}.pgn" -recover -ratinginterval 10 \
    | tee "match/${NAME}.log"

"${PYTHON:-python3}" match/elo.py "match/${NAME}.pgn" New
