# Chess Engine

**Chess Engine** is my project about algorithms and chess combine into my own in-house AI player.
Prioritising algorithms such as **Greedy**, **Min Max** to help the AI opponents to pick the best possible move that will lead to the victory. 

Tech Stack:
Python,
Numpy,
PyGame


AI Level **Difficulty**:

1. Lower than **Stockfish**
2. Better than Steve

## Installation

Clone the repository:

```bash
git clone https://github.com/nhantran1711/ChessGame.git
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

- **Iterative deepening** under a time limit (2s per move): searches depth 1, 2, 3, ... and plays the deepest result, carrying each iteration's best move into the next.
- **Quiescence search** at the horizon: keeps resolving captures and promotions so it never evaluates mid-exchange (e.g. it won't take a pawn defended by a pawn with its queen).
- **Transposition table** with **Zobrist hashing**: each position has a 64-bit hash updated incrementally on every move, so positions reached by different move orders are recognised and their stored result (depth, score, exact/lower/upper bound, best move) is reused. The table persists between moves.
- **Move ordering**: hash move (best move from the table) first, then captures by **MVV-LVA**, then **killer moves**, then quiet moves by **history heuristic**. On Kiwipete at depth 2 this cuts the search from ~75,000 to ~5,000 nodes.

Transposition table effect at fixed depth (same scores with and without it):

| Position | Depth | Nodes (off → on) | Time (off → on) | Speedup | TT hit rate | TT cutoff rate |
| --- | --- | --- | --- | --- | --- | --- |
| Start | 4 | 3,714 → 3,478 | 0.6s → 0.5s | 1.1× | 7.4% | 3.3% |
| Italian | 4 | 14,766 → 10,556 | 2.9s → 1.9s | 1.5× | 4.7% | 1.7% |
| Kiwipete | 3 | 9,289 → 9,097 | 1.8s → 1.8s | 1.0× | 1.9% | 0.0% |
| Position 3 (endgame) | 6 | 36,927 → 16,822 | 4.9s → 2.2s | 2.3× | 18.9% | 11.8% |
| K+B+P vs K+P endgame | 7 | 76,350 → 22,137 | 7.2s → 2.1s | 3.5× | 23.1% | 13.2% |

(Node counts above were measured with the earlier material-only evaluation.)

## Evaluation

`ChessGame/Evaluation.py` scores a position in centipawns with **tapered piece-square tables**: every piece is worth its material value plus a bonus for the square it stands on, with separate midgame and endgame weights. The two are blended by game phase (knight/bishop 1, rook 2, queen 4; 24 with all pieces on):

$$\text{score} = \frac{mg \cdot \text{phase} + eg \cdot (24 - \text{phase})}{24}$$

so the king stays sheltered while queens are on the board and centralises in the endgame. The weights live in `ChessGame/EvalParams.py`; the current ones are the hand-written [Simplified Evaluation Function](https://www.chessprogramming.org/Simplified_Evaluation_Function) tables.

### Texel tuning

`tuning/texel.py` fits the weights to game results ([Texel's tuning method](https://www.chessprogramming.org/Texel%27s_Tuning_Method)). Each quiet position (not in check, no capture or promotion into or out of it) is labelled with its game's result $y \in \{1, \tfrac12, 0\}$ from White's view, and the evaluation $e$ is turned into a predicted score

$$p = \frac{1}{1 + 10^{-K e / 400}}$$

The weights minimise the mean squared error $\frac1N \sum (p_i - y_i)^2$. $K$ is fitted once with the starting weights (golden-section search) and then held fixed. For a fixed position the evaluation is linear in the weights, so each position is stored once as sparse (piece-square, sign, phase) features and the gradient is a weighted sum over them; optimisation is full-batch Adam. Positions are split into train/test **by game** (positions from one game share a label), and the weights with the lowest held-out error are kept.

```bash
python tuning/gen_openings.py 20000 8 tuning/openings_random8.epd      # random 8-ply openings
CUTECHESS=/path/to/cutechess-cli STOCKFISH=/path/to/stockfish \
    tuning/gen_games.sh 1000 tuning/games.pgn                          # 6,000 games, Stockfish 1400/1800/2200 round robin
python tuning/texel.py tuning/games.pgn                                # prints train/test MSE, rewrites ChessGame/EvalParams.py
```

Check any new weights in a head-to-head match against the previous version before keeping them:

```bash
git worktree add ../chess-old HEAD
CUTECHESS=/path/to/cutechess-cli PYTHON=$(which python) match/run_vs.sh . ../chess-old 100 10+0.1
```

## UCI Engine

The engine speaks the [UCI protocol](https://www.wbec-ridderkerk.nl/html/UCIProtocol.html), so it can be loaded into any standard chess GUI (Arena, Cute Chess, En Croissant, ...) or testing tool. No pygame needed:

```bash
python uci.py
```

In a GUI, add an engine whose command is `python` (or the full path to your venv's python) with argument `uci.py` and working directory set to this repository.

Supported: `uci`, `isready`, `ucinewgame`, `position startpos|fen ... moves ...`, `go` with `wtime btime winc binc movestogo movetime depth nodes infinite`, `stop`, `quit`. The engine reports `info depth ... score cp|mate ... nodes nps time pv ...` after each completed depth.

Engine-vs-engine matches, e.g. with [fastchess](https://github.com/Disservin/fastchess) or cutechess-cli:

```bash
fastchess -engine cmd=python args=uci.py dir=. name=new \
          -engine cmd=python args=uci.py dir=/path/to/old/checkout name=old \
          -each tc=10+0.1 -rounds 100 -repeat -concurrency 4
```

## Measured Strength

**≈1175 Elo (95% CI 1049–1271)** on Stockfish's `UCI_Elo` scale, from a 48-game match against Stockfish 19 limited to `UCI_Elo 1320`. This was measured with the material-only evaluation (commit `97ef50f`), before piece-square tables.

| | |
| --- | --- |
| Opponent | Stockfish 19, `UCI_LimitStrength=true`, `UCI_Elo=1320`, 1 thread, 16 MB hash |
| Time control | 120s + 1s per move (the control Stockfish calibrates `UCI_Elo` at, anchored to CCRL 40/4) |
| Openings | 24 positions from [`match/openings.epd`](match/openings.epd), each played with both colours |
| Result | **+14 =1 −33** (score 30.2%); as White 7-0-17, as Black 7-1-16 |
| Elo difference | **−145** (95% CI −271 to −49), likelihood of superiority 0.3% |
| Match record | [`match/sf1320_120+1.pgn`](match/sf1320_120+1.pgn), [`match/sf1320_120+1.log`](match/sf1320_120+1.log) — no time forfeits, crashes or illegal moves |

Caveats: 1320 is the lowest `UCI_Elo` Stockfish offers, so the estimate extrapolates 145 points below its weakest calibrated level. The rating is tied to this hardware (Apple Silicon Mac, 3 games in parallel) and time control; it is not a FIDE or online rating.

### The math

**Score.** With $W$ wins, $D$ draws and $L$ losses over $N$ games, a draw counts as half a point:

$$s = \frac{W + D/2}{N} = \frac{14 + 0.5}{48} = 0.3021$$

**Elo difference.** The Elo model says a player rated $\Delta$ points above the opponent expects to score

$$E(\Delta) = \frac{1}{1 + 10^{-\Delta/400}}$$

Setting $E(\Delta) = s$ and solving for $\Delta$:

$$\Delta = -400 \log_{10}\left(\frac{1}{s} - 1\right) = -400 \log_{10}(2.310) = -145.5$$

Adding the opponent's rating gives the estimate: $1320 - 145 = 1175$.

**Error bars.** Each game scores $x \in \{1, \tfrac12, 0\}$, so the per-game variance (wins, draws and losses as a trinomial) is

$$\sigma^2 = \frac{W(1-s)^2 + D(\tfrac12-s)^2 + L\,s^2}{N} = 0.2056$$

The standard error of the mean score is $\sigma/\sqrt{N} = 0.0655$, so the 95% interval on the score is

$$s \pm 1.96 \cdot \frac{\sigma}{\sqrt{N}} = 0.302 \pm 0.128 = [0.174,\ 0.430]$$

Both ends are pushed through the same Elo formula, which gives $[-271,\ -49]$, i.e. **1049–1271**. The interval is lopsided because the Elo curve is steeper far from 50%. cutechess-cli reports the same centre with a symmetric approximation, −145.5 ± 110.9.

**Likelihood of superiority** (probability the engine is actually the stronger one, draws ignored):

$$\text{LOS} = \Phi\left(\frac{W - L}{\sqrt{W + L}}\right) = \Phi(-2.77) = 0.3\%$$

**Why more games help.** The margin shrinks with $1/\sqrt{N}$: 4× the games halves the error bars. A score of exactly 0% or 100% makes $\Delta$ infinite, so the opponent should be close enough in strength for both sides to score.

### Reproducing

Needs [cutechess-cli](https://github.com/cutechess/cutechess), [Stockfish](https://stockfishchess.org/download/) and a Python with numpy. Keep the machine awake (`caffeinate -i` on macOS); a sleeping machine causes time forfeits that invalidate the run.

```bash
CUTECHESS=/path/to/cutechess-cli STOCKFISH=/path/to/stockfish PYTHON=$(which python) \
    caffeinate -i match/run_match.sh 1320 24     # UCI_Elo, rounds (2 games each), ~2 hours
python match/elo.py match/sf1320_120+1.pgn ChessGame 1320
```

## Testing

Move generation is validated with [perft](https://www.chessprogramming.org/Perft_Results): count every leaf of the legal move tree to a fixed depth and compare against published node counts. Positions covered: the starting position, Kiwipete, and Positions 3–6 (castling, en passant, promotions, checks and pins).

The search is tested too: alpha-beta must return the same score as plain minimax, find forced mates, and avoid horizon-effect blunders.

```bash
pytest              # fast tests (~4s)
pytest --runslow    # adds deeper perft and search tests (~55s), e.g. start d4 = 197,281, Kiwipete d3 = 97,862
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
