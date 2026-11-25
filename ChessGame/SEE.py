"""
Static exchange evaluation (SEE): the material a capture wins or loses once every recapture on that
square is played out, each side always recapturing with its least valuable piece and free to stop.

    see(gamestate, move) -> centipawns from the mover's point of view

Sliding attackers behind the pieces already used are found because each step looks for the least
valuable attacker with the used squares treated as empty (x-rays). Pins, checks and en passant
recaptures are ignored, as usual for SEE: it is a fast estimate for move ordering and pruning.
"""

SEE_VALUE = {"P" : 100, "N" : 320, "B" : 330, "R" : 500, "Q" : 900, "K" : 20000}

KNIGHT_STEPS = [(-2, 1), (-2, -1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
KING_STEPS = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
DIAGONALS = [(-1, -1), (-1, 1), (1, 1), (1, -1)]
ORTHOGONALS = [(0, 1), (0, -1), (1, 0), (-1, 0)]


# Least valuable piece of colour attacking (r, c), skipping squares in gone: (value, (row, col)) or None
def leastValuableAttacker(board, r, c, colour, gone):
    best = None

    # Pawns: a white pawn attacks diagonally upwards, so it stands one row below the square
    pawnRow = r + 1 if colour == "w" else r - 1
    if 0 <= pawnRow < 8:
        for dc in (-1, 1):
            cc = c + dc
            if 0 <= cc < 8 and (pawnRow, cc) not in gone and board[pawnRow][cc] == colour + "P":
                return (SEE_VALUE["P"], (pawnRow, cc))

    for dr, dc in KNIGHT_STEPS:
        rr, cc = r + dr, c + dc
        if 0 <= rr < 8 and 0 <= cc < 8 and (rr, cc) not in gone and board[rr][cc] == colour + "N":
            return (SEE_VALUE["N"], (rr, cc))

    for directions, pieces in ((DIAGONALS, "BQ"), (ORTHOGONALS, "RQ")):
        for dr, dc in directions:
            rr, cc = r + dr, c + dc
            while 0 <= rr < 8 and 0 <= cc < 8:
                sq = board[rr][cc]
                if sq != "--" and (rr, cc) not in gone:
                    if sq[0] == colour and sq[1] in pieces:
                        value = SEE_VALUE[sq[1]]
                        if best is None or value < best[0]:
                            best = (value, (rr, cc))
                    break
                rr += dr
                cc += dc

    if best is not None:
        return best
    for dr, dc in KING_STEPS:
        rr, cc = r + dr, c + dc
        if 0 <= rr < 8 and 0 <= cc < 8 and (rr, cc) not in gone and board[rr][cc] == colour + "K":
            return (SEE_VALUE["K"], (rr, cc))
    return None


def see(gamestate, move):
    if move.isEnpassantMove:
        return SEE_VALUE["P"] # Pawn takes pawn; recaptures on the empty square are rare enough to ignore
    board = gamestate.board
    r, c = move.endRow, move.endCol
    mover = move.pieceMoved[0]
    opponent = "b" if mover == "w" else "w"

    # gains[i] is the material balance for the side making capture i if the exchange stopped there
    gains = [SEE_VALUE[move.pieceCaptured[1]] if move.pieceCaptured != "--" else 0]
    onSquare = SEE_VALUE[move.promotionPiece] if move.isPawnPromotion else SEE_VALUE[move.pieceMoved[1]]
    if move.isPawnPromotion:
        gains[0] += SEE_VALUE[move.promotionPiece] - SEE_VALUE["P"]
    gone = {(move.startRow, move.startCol)}
    side = opponent
    while True:
        attacker = leastValuableAttacker(board, r, c, side, gone)
        if attacker is None:
            break
        value, square = attacker
        gains.append(onSquare - gains[-1]) # Capture what stands there, after the previous balance
        onSquare = value
        gone.add(square)
        side = "w" if side == "b" else "b"
        if value == SEE_VALUE["K"]:
            # A king may only recapture if nothing defends the square; otherwise the exchange stops
            if leastValuableAttacker(board, r, c, side, gone) is not None:
                gains.pop()
            break

    # Each side may decline to continue: fold back from the last capture
    for i in range(len(gains) - 1, 0, -1):
        gains[i - 1] = -max(-gains[i - 1], gains[i])
    return gains[0]
