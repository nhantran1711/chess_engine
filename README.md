# ChessGame Engine


## Overview
A chess game engine built with **Python**, **Pygame**, and **NumPy**.  
Play chess with a graphical interface and extend it with a custom AI to evaluate and checking valid and best move possible.
This is my project since I am passionate about Machine Learning as well as Chess.

---

## Features
- 8×8 chessboard rendered with **Pygame**
- Pieces represented with NumPy for fast AI logic
- Standard chess setup with white and black pieces
- Modular design: separate

---

## Installation

Clone the repository:

```bash
git clone https://github.com/nhantran1711/ChessGame.git
```


Install Dependencies
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

## Future Improvements
✅ Display chessboard and pieces

✅ Mouse-based piece movement

✅ Legal move validation

✅ AI opponent

✅ Castling, en passant, and promotion



