# Chess Engine

**Chess Engine** is my project about algorithms and chess combine into my own in-house AI player.
Prioritising algorithms such as **Greedy**, **Min Max** to help the AI opponents to pick the best possible move that will lead to the victory. 

Tech Stack:
Python (runs under CPython or PyPy),
Rust for the fast UCI engine ([`engine/`](engine/)),
PyGame for the GUI,
NumPy for the evaluation tuner


AI Level **Difficulty**:

1. **≈2880** on Stockfish's `UCI_Elo` scale for the Rust engine, **≈1970** for the Python one ([Measured Strength](#measured-strength))
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

All ratings are on Stockfish's `UCI_Elo` scale, from 120s + 1s matches against Stockfish 19 at limited strength.

| Engine | Rating (95% CI) | Evidence |
| --- | --- | --- |
| **Rust engine** ([below](#rust-engine)) | **≈2880 (2792–2954)** | 48 games vs `UCI_Elo 3000`: **+7 =18 −23** |
| Python engine, under PyPy | ≈1970 (1908–2049) | 120 games vs `UCI_Elo 1800`: +86 =3 −31 |

Head to head on the same machine, an earlier Rust version beat the Python one (under PyPy) **+38 =2 −0** over 40 games at 60s + 0.6s.

### Rust engine match

**≈2880 Elo (95% CI 2792–2954)** from a 48-game match against Stockfish 19 limited to `UCI_Elo 3000`.

| | |
| --- | --- |
| Opponent | Stockfish 19, `UCI_LimitStrength=true`, `UCI_Elo=3000`, 1 thread, 16 MB hash (the Rust engine: 1 thread, 32 MB) |
| Time control | 120s + 1s per move |
| Openings | The 24 positions in [`match/openings.epd`](match/openings.epd), each played with both colours |
| Adjudication | A game ends once both engines report ≥ 1000 cp for the same side on each of their last 3 moves; a draw after 300 plies |
| Result | **+7 =18 −23** (score 33.3%); as White 5-12-7, as Black 2-6-16 |
| Elo difference | **−120** (95% CI −208 to −46) |
| Match record | [`match/rust_v3_sf3000_120+1.log`](match/rust_v3_sf3000_120+1.log), [`match/rust_v3_sf3000_120+1.games.txt`](match/rust_v3_sf3000_120+1.games.txt) (moves of every game), played with `match/selfplay.py`. No time forfeits, crashes or illegal moves |

Caveats: measured on an AMD Ryzen 5 7500F (5 games in parallel). It is not a FIDE or online rating. The engine scored far better with White than with Black, so 48 games leave a wide interval.

Earlier versions, before the search, time-management and evaluation work listed under [Rust Engine](#rust-engine):

- **+33 =5 −10** (74.0%, +181 Elo, CI +88 to +308, so ≈2781, 2688–2908) against `UCI_Elo 2600` on the Ryzen with 5 games in parallel ([`match/rust_v2_sf2600_120+1.log`](match/rust_v2_sf2600_120+1.log), [`match/rust_v2_sf2600_120+1.games.txt`](match/rust_v2_sf2600_120+1.games.txt)).
- **+42 =2 −4** (89.6%, +374 Elo, CI +257 to +653, so ≈2574, 2457–2853) against `UCI_Elo 2200` on an Apple M1 with 3 games in parallel ([`match/rust_v2_sf2200_120+1.pgn`](match/rust_v2_sf2200_120+1.pgn), [`match/rust_v2_sf2200_120+1.log`](match/rust_v2_sf2200_120+1.log)). That score was too lopsided for a tight interval.

Head-to-head (the earlier Rust version) against the Python engine: **+38 =2 −0** (97.5%), Elo difference +636 with a 95% lower bound of +482 (no upper bound, since the Python engine never won). Python ran under PyPy 3.11, 60s + 0.6s, 3 games in parallel; record in [`match/rust_vs_pypy_60+0.6.pgn`](match/rust_vs_pypy_60+0.6.pgn).

### Python engine match

**≈1970 Elo (95% CI 1908–2049)** from a 120-game match against Stockfish 19 limited to `UCI_Elo 1800`, running under PyPy.

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
| Python: faster move generation, selective search, tuned evaluation | ≈1970 (1908–2049) | 120 games vs `UCI_Elo 1800`, Ryzen 5 7500F, PyPy |
| Rust: straight port of the earlier Python search and tables (commit `d651436`) | ≈2011 (1918–2144) | 48 games vs `UCI_Elo 1800`, Apple M1 |
| Rust: full port of the current search and tuned evaluation | ≈2574 (2457–2853) | 48 games vs `UCI_Elo 2200`, Apple M1 |
| Rust: same engine, against a closer opponent | ≈2781 (2688–2908) | 48 games vs `UCI_Elo 2600`, Ryzen 5 7500F |
| **Rust: stronger search, time management, 99-term self-tuned evaluation** | **≈2880 (2792–2954)** | 48 games vs `UCI_Elo 3000`, Ryzen 5 7500F |

The straight Rust port scored **+34 =6 −8** against `UCI_Elo 1800` ([`match/rust_sf1800_120+1.pgn`](match/rust_sf1800_120+1.pgn)): the same search as the 5,000 nodes/s Python engine, but about 1,400× faster. Two of its losses were time forfeits caused by the Mac going to sleep mid-match (Stockfish lost a game on time in the same minute), so it is slightly underrated.

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

## Rust Engine

[`engine/`](engine/) is the engine rewritten in Rust as a standalone UCI binary, and the strongest version: **≈2880 Elo** ([Measured Strength](#measured-strength)), about 900 points above the Python engine. It started as a port of the Python engine's search and evaluation (see [AI Search](#ai-search) and [Evaluation](#evaluation)) and has since gone further than it:

- Search: iterative deepening with aspiration windows, PVS, transposition table (probed in quiescence too), quiescence with SEE and delta pruning, check extensions, singular extensions with multi-cut, null-move pruning with a depth- and eval-scaled reduction, reverse futility pruning, razoring, futility pruning, late move pruning, SEE pruning of quiet moves and captures, internal iterative reductions, logarithmic late move reductions adjusted by history, and repetition / fifty-move draw detection.
- Move ordering: hash move, MVV-LVA with capture history, SEE-losing captures after the killers, quiet moves by butterfly history plus continuation history one and two plies back, all with history gravity and penalties for moves that failed to cut off.
- Time management: a soft target per move, stretched when the best move keeps changing or the score drops and shortened when it is stable, plus a hard limit that stops the search mid-iteration.
- Evaluation: piece-square tables plus 99 positional terms in [`engine/src/eval.rs`](engine/src/eval.rs): pawn structure (passed, doubled, isolated, supported and phalanx pawns, passed-pawn blockers and king distances), king safety (pawn shield, open files, attacks on the king zone, number of attackers, safe checks), mobility tables per piece, threats (pawn and minor-piece attacks on bigger pieces, undefended pieces), outposts, the bishop pair, rooks on open files and the seventh rank, and a side-to-move bonus.
- Weights: Texel-tuned by the engine itself, `chessgame tune` ([`engine/src/tune.rs`](engine/src/tune.rs)), which fits all 966 weights with Adam and writes [`engine/src/params.rs`](engine/src/params.rs). On the quiet-labeled.v7 set it reaches an MSE of 0.05978, against 0.06374 for the previous (Python-tuned) weights and terms. The Rust weights are therefore no longer shared with the Python engine; [`tuning/export_rust_params.py`](tuning/export_rust_params.py) is kept for history but would overwrite them with the older, smaller set, so it refuses to run without `--force`.

```bash
cd engine
cargo build --release          # binary: engine/target/release/chessgame
cargo test --release           # perft to depth 4-6 on six positions, hash, capture-generator, SEE, draw and mate tests
./target/release/chessgame bench 14
python -c "import gzip,shutil; shutil.copyfileobj(gzip.open('../tuning/data/quiet-labeled.v7.epd.gz','rb'), open('../tuning/data/quiet-labeled.v7.epd','wb'))"
./target/release/chessgame tune ../tuning/data/quiet-labeled.v7.epd 1500   # ~1 minute on 12 threads, rewrites src/params.rs
```

The board uses bitboards (one 64-bit mask per piece type and colour) with copy-make instead of make/undo, and pseudo-legal move generation with a king-in-check test after each move. With the full evaluation it searches about 1.6 million nodes per second; `bench 14` (depth 14 on six positions) takes 2.5 million nodes and 1.6 s on a Ryzen 5 7500F. Point a GUI at `engine/target/release/chessgame` directly; the UCI commands are the same as the Python engine's, plus `go perft N`, `eval` and a `Hash` option (MB, default 32).

### Testing changes

`chessgame arena NEW BASE` ([`engine/src/arena.rs`](engine/src/arena.rs)) plays two engine binaries against each other and stops with a sequential probability ratio test (SPRT), the standard way to tell whether a change gains Elo. Openings are a line from [`match/openings.epd`](match/openings.epd) plus four random plies, kept only if roughly balanced, and each is played with both colours. Keep a copy of the old binary to test against:

```bash
cp engine/target/release/chessgame.exe engine/test/base.exe    # before the change (no .exe outside Windows); engine/test/ is ignored by git
# ... make the change, cargo build --release ...
cp engine/target/release/chessgame.exe engine/test/new.exe
engine/test/new.exe arena engine/test/new.exe engine/test/base.exe --tc 5+0.05 --concurrency 10 --sprt 0 5
```

The changes above were each tested this way at 5s + 0.05s, against the version before them:

| Change | Elo vs previous version (95% CI) | Games |
| --- | --- | --- |
| Search: the selective-search techniques above, except singular extensions | +238 (+173 to +320) | 64 |
| Time management | +91 (+66 to +116) | 380 |
| Singular extensions, two-ply continuation history | not measured (match stopped early to save time) | |
| New evaluation terms, retuned | +99 (+74 to +126) | 420 |

Self-play at a fast time control overstates gains against other engines; the [Measured Strength](#measured-strength) match is the real number.

The match scripts take the binary too (`match/selfplay.py` also accepts any UCI executable). On an M1, `CONCURRENCY=4` (one game per performance core) and `ADJUDICATE_DRAWS=1` cut a 48-game gauntlet to under an hour:

```bash
ENGINE=engine/target/release/chessgame CONCURRENCY=4 ADJUDICATE_DRAWS=1 CUTECHESS=... STOCKFISH=... \
    caffeinate -i match/run_match.sh 2200 24
CUTECHESS=... PYTHON=pypy match/run_vs.sh engine/target/release/chessgame . 20 60+0.6   # Rust vs this checkout's Python
```

Without cutechess-cli (as on Windows), `match/selfplay.py` runs the same gauntlet. Give it absolute paths to real executables: WinGet's `stockfish` link cannot be started by Python, so point it at the `.exe` under `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Stockfish.Stockfish_*`:

```bash
python match/selfplay.py C:/path/to/engine/target/release/chessgame.exe C:/path/to/stockfish.exe --tc 120+1 --resign 1000 \
    --option-b UCI_LimitStrength=true --option-b UCI_Elo=3000 --option-b Threads=1 --option-b Hash=16 \
    --games 48 --concurrency 5 --games-log match/rust_v3_sf3000_120+1.games.txt     # ~1.5 hours on a Ryzen 5 7500F
```

The pygame GUI (`main.py`) still uses the Python engine.

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
