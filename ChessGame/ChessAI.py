
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
    turnMultipler = 1 if gamestate.whiteToMove else - 1

    oppMinMaxScore = CHECKMATE
    bestPlayerMove = None

    # Exploring all players current valid moves
    for playerMove in validMoves:

        # Make current moves
        gamestate.makeMoves(playerMove)

        # Explore all opponents valid moves, checking min max value 1 step ahead
        oppMoves = gamestate.getValidateMoves()
        random.shuffle(validMoves)
        oppMaxScore = -CHECKMATE # Opps best move

        for opp in oppMoves:

            gamestate.makeMoves(opp)
            # Checking the current condition after making the move
            if gamestate.checkMate == True:
                cur_score = turnMultipler * CHECKMATE
            elif gamestate.staleMate == True:
                cur_score = STALEMATE
            else:
                cur_score = -turnMultipler * scoreMaterial(gamestate.board)

            # Update opp max scorwee value
            if (cur_score > oppMaxScore):
                oppMaxScore = cur_score
            gamestate.undoMove()

        # min max value update
        if oppMinMaxScore > oppMaxScore:
            oppMinMaxScore = oppMaxScore
            bestPlayerMove = playerMove
        gamestate.undoMove()
    return bestPlayerMove


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
