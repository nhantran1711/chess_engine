
import random


piecesScore = {
    "K" : 0,
    "Q" : 8,
    "R" : 5,
    'B' : 3,
    "N": 3,
    "P": 1
}

# HIGHLY IMPORTANT VARIABLES, DO NOT CHANGE
CHECKMATE = 1000
STALEMATE = 0
DEPTH = 2


# Return a random moves of valid moves
def randomMove(validMoves):
    movesIndex = random.randint(0, len(validMoves) - 1)
    return validMoves[movesIndex]


# Finding the best move in the current game state
def findBestMove(gamestate, validMoves):
    turnMultipler = 1 if gamestate.whiteToMove else - 1

    oppMinMaxScore = CHECKMATE
    bestPlayerMove = None
    random.shuffle(validMoves)

    # Exploring all players current valid moves
    for playerMove in validMoves:

        # Make current moves
        gamestate.makeMoves(playerMove)

        # Explore all opponents valid moves, checking min max value 1 step ahead
        oppMoves = gamestate.getValidateMoves()
        if gamestate.checkMate:
            oppMaxScore = -CHECKMATE
        elif gamestate.staleMate:
            oppMaxScore = STALEMATE
        else:
            oppMaxScore = -CHECKMATE # Opps best move

            for opp in oppMoves:
                gamestate.makeMoves(opp)

                # Checking the current condition after making the move
                if gamestate.checkMate == True:
                    cur_score = -CHECKMATE
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


# Find best move in min max algo, helper method for the first move
# Repeatly finding min and max at each decision with the depth of constant, 
# check and find whatever the best move giving the value

def findBestMoveMinMax(gamestate, validMoves):
    global nextMove
    nextMove = None
    findMoveMinMax(gamestate, validMoves, DEPTH, gamestate.whiteToMove)
    return nextMove

def findMoveMinMax(gamestate, validMoves, depth, whiteToMove):
    global nextMove

    # STOP the recursive aka base case
    if depth == 0:
        return scoreBoard(gamestate)

    # IF white to move
    if whiteToMove:

        max_score = -CHECKMATE
        for move in validMoves:
            gamestate.makeMoves(move)
            
            # What is the next move
            nextMoves = gamestate.getValidateMoves()
            score = findMoveMinMax(gamestate, nextMoves, depth - 1, not whiteToMove)

            # Update maxscore
            if score > max_score:
                max_score = score

                # At the first depth:
                if depth == DEPTH:
                    nextMove = move
            gamestate.undoMove()
        return max_score

    # If black to move
    else:
        min_score = CHECKMATE
        for move in validMoves:
            gamestate.makeMoves(move)

            # Next move
            nextMoves = gamestate.getValidateMoves()
            score = findMoveMinMax(gamestate, nextMoves, depth - 1, not whiteToMove)

            # Update min score
            if score < min_score:
                min_score = score

                # At the first depth:
                if depth == DEPTH:
                    nextMove = move
            gamestate.undoMove()
        return min_score


# Score the board - positive trade is good for player white, a negative score is good for black
def scoreBoard(gamestate):

    # If checkmate
    if gamestate.checkMate:
        # Black wins
        if gamestate.whiteToMove:
            return -CHECKMATE
        elif not gamestate.whiteToMove:
            return CHECKMATE
        
    # If stalemate
    elif gamestate.staleMate:
        return STALEMATE

    score = 0
    for row in gamestate.board:
        for sq in row:
            if sq[0] == 'w':
                score += piecesScore[sq[1]]
            elif sq[0] == 'b':
                score -= piecesScore[sq[1]]

    return score

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
