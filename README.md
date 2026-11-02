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

Evaluation is material only for now, so the opening play is aimless; piece-square tables are the next step.

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
