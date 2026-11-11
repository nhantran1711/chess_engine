# Chess Engine

**Chess Engine** is my project about algorithms and chess combine into my own in-house AI player.
Prioritising algorithms such as **Greedy**, **Min Max** to help the AI opponents to pick the best possible move that will lead to the victory. 

Tech Stack:
Python (runs under CPython or PyPy),
PyGame for the GUI,
NumPy for the evaluation tuner


AI Level **Difficulty**:

1. **≈1970** on Stockfish's `UCI_Elo` scale ([Measured Strength](#measured-strength))
2. Still lower than full-strength **Stockfish**
3. Better than Martin

## Installation

Clone the repository:

```bash
git clone https://github.com/nhantran1711/chess_engine.git
```

Create environment (optional but useful):
```bash
python -m venv venv
```

Activate the environment:

macOS/Linux:
```bash

source venv/bin/activate
```

Windows:
```bash
venv\Scripts\activate
```

Install Dependencies:
```bash
pip install -r requirements.txt
```


Run the chess program
```bash
python main.py

```

## AI Search

The AI (`Searcher` in `ChessGame/ChessAI.py`) is a negamax **alpha-beta** search:

- **Iterative deepening** under a time limit (2s per move in the GUI, or the UCI clock): searches depth 1, 2, 3, ... and plays the deepest result, carrying each iteration's best move into the next.
- **Principal variation search**: the first move gets the full window, the rest a zero window, re-searched only if they beat alpha.
- **Quiescence search** at the horizon: keeps resolving captures and promotions so it never evaluates mid-exchange (e.g. it won't take a pawn defended by a pawn with its queen).
- **Transposition table** with **Zobrist hashing**: each position has a 64-bit hash updated incrementally on every move, so positions reached by different move orders are recognised and their stored result (depth, score, exact/lower/upper bound, best move) is reused. Mate scores are stored relative to the node so they stay correct at any ply. The table persists between moves.
- **Move ordering**: hash move first, then captures by **MVV-LVA**, then **killer moves**, then quiet moves by **history heuristic**.
- **Draw detection**: repeated positions and the fifty-move rule score 0, so the engine heads for a draw when losing and avoids one when winning.

Selective techniques, each with its own switch (`Searcher(disabled = (...))`, or the UCI options below):

| Technique | What it does | Elo when switched on* |
| --- | --- | --- |
| `LMR` | Late move reductions: quiet moves late in the ordering are searched 1–2 plies shallower first | **+54** (+12 to +99) |
| `Futility` | One or two plies from the horizon, skip quiet moves when static eval + 200/450 can't reach alpha | **+53** (+8 to +99) |
| `NullMove` | Pass the turn; if a reduced search still reaches beta, prune. Off without minor/major pieces (zugzwang) | +33 (−11 to +78) |
| `CheckExtension` | Search one ply deeper when in check | +3 (−40 to +47) |
| `Aspiration` | From depth 4, search a ±50 window around the last score, widening on a miss | −12 (−57 to +32) |

\* 200 self-play games each: the full engine against the same engine with that one technique off, under PyPy at 300 ms/move (95% intervals). Check extensions and aspiration windows are within noise at this speed and are kept on as standard practice.

None of them hides tactics. On the 195-position suite in [`match/tactics.epd`](match/tactics.epd) (mates and material wins with a unique best move, found by full-width search), every position missed with all techniques on at 1s was either solved with more time, or a full-width search confirmed the engine's move was as good or better.

### Speed

Legal move generation finds pins and checkers once per position instead of playing every move and testing for check, the board is plain Python lists, and quiescence generates captures only. Searching four test positions to depth 4 went from 10.05s to 1.22s on CPython (~6,800 → ~40,000 nodes/s).

The engine is pure Python with no dependencies, so it also runs under [PyPy](https://pypy.org/), which is **~3.7× faster again** once warmed up (~140,000 nodes/s) and worth about **+300 Elo** in self-play:

```bash
pypy uci.py
```

## Evaluation

`ChessGame/Evaluation.py` scores a position in centipawns from two parts, each with separate midgame and endgame weights:

- **Piece-square tables**: every piece is worth its material value plus a bonus for its square.
- **Positional terms** (`evalTerms`): passed pawns by rank, doubled and isolated pawns, the pawn shield and open files around the king, the bishop pair, and rooks on open or half-open files.

The midgame and endgame scores are blended by game phase (knight/bishop 1, rook 2, queen 4; 24 with all pieces on):

$$\text{score} = \frac{mg \cdot \text{phase} + eg \cdot (24 - \text{phase})}{24}$$

so the king stays sheltered while queens are on the board and centralises in the endgame. All weights live in `ChessGame/EvalParams.py` and are **Texel-tuned** (below). Some tuned values, in centipawns as midgame / endgame: passed pawn on the 6th rank −3 / +118, bishop pair +38 / +48, rook on an open file +59 / 0, each file near the king without an own pawn −19 / −7.

### Texel tuning

`tuning/texel.py` fits the weights to game results ([Texel's tuning method](https://www.chessprogramming.org/Texel%27s_Tuning_Method)). Each position is labelled with its game's result $y \in \{1, \tfrac12, 0\}$ from White's view, and the evaluation $e$ is turned into a predicted score

$$p = \frac{1}{1 + 10^{-K e / 400}}$$

The weights minimise the mean squared error $\frac1N \sum (p_i - y_i)^2$. $K$ is fitted once with the starting weights (golden-section search) and then held fixed. For a fixed position the evaluation is linear in the weights: piece-square features are stored sparsely and the positional terms as dense counts, both computed by the engine's own `Evaluation` code so the tuner and the engine always agree. Optimisation is full-batch Adam, keeping the weights with the lowest held-out error.

The current weights were fitted to the 1.43M labelled quiet positions of the [Zurichess `quiet-labeled.v7`](https://bitbucket.org/zurichess/tuner/downloads/) set, with 10% held out:

| Evaluation | Held-out MSE |
| --- | --- |
| Previous piece-square tables, no positional terms | 0.07159 |
| Plus positional terms, textbook weights | 0.06950 |
| **Everything Texel-tuned** | **0.06398** |

In a 200-game self-play match the tuned evaluation scored **+60 Elo** (+14 to +107) over the previous tables.

```bash
mkdir -p tuning/data
curl -L -o tuning/data/quiet-labeled.v7.epd.gz https://bitbucket.org/zurichess/tuner/downloads/quiet-labeled.v7.epd.gz
python tuning/texel.py tuning/data/quiet-labeled.v7.epd.gz   # ~35 min; prints MSE, rewrites ChessGame/EvalParams.py
```

It also accepts a PGN of games (`python tuning/texel.py games.pgn`, needs `chess`), using only their quiet positions.

## Self-play testing

[`match/selfplay.py`](match/selfplay.py) plays two engines against each other from [`match/openings.epd`](match/openings.epd) (extended with random plies), each opening with both colours, and reports the Elo difference with a 95% interval. Each engine is either a checkout of this repo or any UCI executable; this checkout's move generator is the arbiter.

```bash
git worktree add ../chess-old HEAD~1
python match/selfplay.py . ../chess-old --games 200 --movetime 300 --python-a pypy --python-b pypy   # did a change help?
python match/selfplay.py . . --option-b LMR=false                                                    # is one technique worth it?
python match/tactics.py solve --time 1.0                                                             # tactical solve rate per technique
```

## UCI Engine

The engine speaks the [UCI protocol](https://www.wbec-ridderkerk.nl/html/UCIProtocol.html), so it can be loaded into any standard chess GUI (Arena, Cute Chess, En Croissant, ...) or testing tool. No pygame needed:

```bash
python uci.py      # or: pypy uci.py, much faster
```

In a GUI, add an engine whose command is `python` or `pypy` (or the full path to it) with argument `uci.py` and working directory set to this repository.

Supported: `uci`, `isready`, `ucinewgame`, `position startpos|fen ... moves ...`, `go` with `wtime btime winc binc movestogo movetime depth nodes infinite`, `stop`, `quit`, and `setoption name <NullMove|LMR|CheckExtension|Aspiration|Futility> value <true|false>`. The engine reports `info depth ... score cp|mate ... nodes nps time pv ...` after each completed depth.

## Measured Strength

**≈1970 Elo (95% CI 1908–2049)** on Stockfish's `UCI_Elo` scale, from a 120-game match against Stockfish 19 limited to `UCI_Elo 1800`, running under PyPy.

| | |
| --- | --- |
| Opponent | Stockfish 19, `UCI_LimitStrength=true`, `UCI_Elo=1800`, 1 thread, 16 MB hash |
| Time control | 120s + 1s per move (the control Stockfish calibrates `UCI_Elo` at, anchored to CCRL 40/4) |
| Openings | 60 positions: the 24 in [`match/openings.epd`](match/openings.epd) plus 36 with two random plies added, each played with both colours |
| Adjudication | A game ends once both engines report ≥ 1000 cp for the same side on each of their last 3 moves |
| Result | **+86 =3 −31** (score 72.9%); as White 45-1-14, as Black 41-2-17 |
| Elo difference | **+172** (95% CI +108 to +249), likelihood of superiority > 99.99% |
| Match record | [`match/sf1800_120+1.log`](match/sf1800_120+1.log), [`match/sf1800_120+1.games.txt`](match/sf1800_120+1.games.txt) (moves of every game). No time forfeits, crashes or illegal moves |

Caveats: the rating is tied to this hardware (AMD Ryzen 5 7500F, 8 games in parallel), PyPy, and this time control; under CPython expect roughly 300 points less. It is not a FIDE or online rating.

### Progress

| Version | Rating | Measured |
| --- | --- | --- |
| Material-only evaluation (commit `97ef50f`) | ≈1175 (1049–1271) | 48 games vs `UCI_Elo 1320`, Apple Silicon Mac, CPython |
| Current: faster move generation, selective search, tuned evaluation | **≈1970 (1908–2049)** | 120 games vs `UCI_Elo 1800`, Ryzen 5 7500F, PyPy |

The earlier match was **+14 =1 −33** against `UCI_Elo 1320` (score 30.2%, −145 Elo, CI −271 to −49); its record is in [`match/sf1320_120+1.pgn`](match/sf1320_120+1.pgn) and [`match/sf1320_120+1.log`](match/sf1320_120+1.log). 1320 is the lowest `UCI_Elo` Stockfish offers, so that estimate extrapolated below its weakest calibrated level.

### The math

**Score.** With $W$ wins, $D$ draws and $L$ losses over $N$ games, a draw counts as half a point:

$$s = \frac{W + D/2}{N} = \frac{86 + 1.5}{120} = 0.7292$$

**Elo difference.** The Elo model says a player rated $\Delta$ points above the opponent expects to score

$$E(\Delta) = \frac{1}{1 + 10^{-\Delta/400}}$$

Setting $E(\Delta) = s$ and solving for $\Delta$:

$$\Delta = -400 \log_{10}\left(\frac{1}{s} - 1\right) = -400 \log_{10}(0.3714) = +172.0$$

Adding the opponent's rating gives the estimate: $1800 + 172 = 1972$.

**Error bars.** Each game scores $x \in \{1, \tfrac12, 0\}$, so the per-game variance (wins, draws and losses as a trinomial) is

$$\sigma^2 = \frac{W(1-s)^2 + D(\tfrac12-s)^2 + L\,s^2}{N} = 0.1912$$

The standard error of the mean score is $\sigma/\sqrt{N} = 0.0399$, so the 95% interval on the score is

$$s \pm 1.96 \cdot \frac{\sigma}{\sqrt{N}} = 0.729 \pm 0.078 = [0.651,\ 0.807]$$

Both ends are pushed through the same Elo formula, which gives $[+108,\ +249]$, i.e. **1908–2049**. The interval is lopsided because the Elo curve is steeper far from 50%.

**Likelihood of superiority** (probability the engine is actually the stronger one, draws ignored):

$$\text{LOS} = \Phi\left(\frac{W - L}{\sqrt{W + L}}\right) = \Phi(5.08) > 99.99\%$$

**Why more games help.** The margin shrinks with $1/\sqrt{N}$: 4× the games halves the error bars. A score of exactly 0% or 100% makes $\Delta$ infinite, so the opponent should be close enough in strength for both sides to score.

### Reproducing

Needs [Stockfish](https://stockfishchess.org/download/) (on Windows: `winget install Stockfish.Stockfish`) and ideally [PyPy](https://pypy.org/download.html) (`winget install PyPy.PyPy.3.11`). Keep the machine awake; a sleeping machine causes time forfeits that invalidate the run.

```bash
python match/selfplay.py . /path/to/stockfish --python-a /path/to/pypy --tc 120+1 --resign 1000 \
    --option-b UCI_LimitStrength=true --option-b UCI_Elo=1800 --option-b Threads=1 --option-b Hash=16 \
    --games 120 --concurrency 8 --games-log match/sf1800_120+1.games.txt     # ~70 minutes
```

The older cutechess-cli gauntlet still works: `CUTECHESS=... STOCKFISH=... PYTHON=... match/run_match.sh 1320 24`, then `python match/elo.py match/sf1320_120+1.pgn ChessGame 1320`.

## Testing

Move generation is validated with [perft](https://www.chessprogramming.org/Perft_Results): count every leaf of the legal move tree to a fixed depth and compare against published node counts. Positions covered: the starting position, Kiwipete, and Positions 3–6 (castling, en passant, promotions, checks and pins).

The search is tested too: alpha-beta (with the selective techniques off) must return the same score as plain minimax, find forced mates, avoid horizon-effect blunders, score repetitions and the fifty-move rule as draws, and solve tactics from the suite with each selective technique on its own. The evaluation tests cover colour symmetry, phase tapering and each positional term; the UCI tests also drive a real engine process.

```bash
pytest              # fast tests (~5s)
pytest --runslow    # adds deeper perft (~4s), e.g. start d4 = 197,281, Kiwipete d3 = 97,862
pypy -m pytest      # the same suite under PyPy
```

To debug a mismatch, print per-move counts and diff them against a reference engine (e.g. Stockfish `go perft 3`):

```bash
python -m ChessGame.Perft "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1" 3
```

---

## Controls
1. Mouse click to move pieces
2. Key "Z" for undo move
3. Key "R" for reset the board


## Testing Demo
Click for the video: [Video Recording](https://www.youtube.com/watch?v=6SU0OqYx58w)



## Contributing

Pull requests are welcome. For major changes, please open an issue first
to discuss what you would like to change.

Please make sure to update tests as appropriate.
