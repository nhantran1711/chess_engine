
import random


piecesScore = {
    "K" : 0,
    "Q" : 8,
    "R" : 5,
    'B' : 3,
    "N": 3,
    "P": 1
}

CHECKMATE = 1000
STALEMATE = 0



# Return a random moves of valid moves
def randomMove(validMoves):
    movesIndex = random.randint(0, len(validMoves) - 1)
    return validMoves[movesIndex]


# Finding the best move in the current game state
def findBestMove(gamestate, validMoves):
    pass


# Score the board based on mateial
def scoreMaterial(board):
    score = 0
    for row in board:
        for sq in row:
            if sq[0] == 'w':
                score += piecesScore[sq[1]]
            elif sq[0] == 'b':
                score -= piecesScore[sq[1]]

    return score
