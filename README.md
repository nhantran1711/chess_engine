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

## Testing (Perft)
Move generation is validated with [perft](https://www.chessprogramming.org/Perft_Results): count every leaf of the legal move tree to a fixed depth and compare against published node counts. Positions covered: the starting position, Kiwipete, and Positions 3–6 (castling, en passant, promotions, checks and pins).

```bash
pytest              # fast depths (~10s)
pytest --runslow    # adds deeper depths (~2.5 min), e.g. start d4 = 197,281, Kiwipete d3 = 97,862
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
