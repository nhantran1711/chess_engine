
import random
import time


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


'''
Alpha-beta (negamax) search with iterative deepening, quiescence search and move ordering.

Move ordering, best first:
1. Best move from the previous iteration (root only)
2. Captures and promotions, by MVV-LVA (most valuable victim, least valuable attacker)
3. Killer moves: quiet moves that caused a beta cutoff at the same ply
4. Remaining quiet moves by history heuristic score

Scores are relative to the side to move. Mate is CHECKMATE - ply, so faster mates score higher.
'''

TIME_LIMIT = 2.0 # Seconds per AI move
MAX_DEPTH = 64
MAX_PLY = 128

# Ordering values, separate from evaluation so the king counts as the most valuable attacker
mvvLvaValue = {"P" : 1, "N" : 3, "B" : 3, "R" : 5, "Q" : 9, "K" : 10}
PV_MOVE_SCORE = 1000000
CAPTURE_SCORE = 100000
KILLER_SCORES = [90000, 80000]


class SearchTimeout(Exception):
    pass


class Searcher():
    def __init__(self, timeLimit = TIME_LIMIT, maxDepth = MAX_DEPTH, useQuiescence = True):
        self.timeLimit = timeLimit
        self.maxDepth = maxDepth
        self.useQuiescence = useQuiescence
        self.resetTables()

    def resetTables(self):
        self.killers = [[None, None] for _ in range(MAX_PLY)] # moveIDs
        self.history = [[0] * 64 for _ in range(64)] # [from square][to square]
        self.nodes = 0
        self.deadline = None

    # Iterative deepening: search depth 1, 2, 3, ... until time runs out, keep the last completed result
    def search(self, gamestate, validMoves = None):
        self.resetTables()
        startTime = time.time()
        self.deadline = startTime + self.timeLimit
        startLogLength = len(gamestate.moveLogs)

        rootMoves = list(validMoves) if validMoves is not None else gamestate.getValidateMoves()
        if not rootMoves:
            return None
        random.shuffle(rootMoves) # Variety between equally scored moves

        rootMoves.sort(key = lambda m: self.moveOrderScore(m, 0), reverse = True)
        bestMove = rootMoves[0] # Fallback if not even one root move finishes: best capture by MVV-LVA
        self.depthReached = 0
        self.bestScore = None
        self.partialBest = None

        for depth in range(1, self.maxDepth + 1):
            try:
                score, move = self.searchRoot(gamestate, rootMoves, depth, bestMove)
            except SearchTimeout:
                # Unwind any moves still on the board from the aborted iteration
                while len(gamestate.moveLogs) > startLogLength:
                    gamestate.undoMove()
                # The previous best move is searched first, so a partial iteration's best is at least as informed
                if self.partialBest is not None:
                    self.bestScore, bestMove = self.partialBest
                break

            bestMove, self.bestScore, self.depthReached = move, score, depth

            if abs(score) >= CHECKMATE - MAX_PLY: # Forced mate found, deeper search won't change it
                break
            if time.time() - startTime > self.timeLimit / 2: # Next iteration would very likely not finish
                break

        return bestMove

    def searchRoot(self, gamestate, rootMoves, depth, pvMove):
        rootMoves.sort(key = lambda m: self.moveOrderScore(m, 0, pvMove), reverse = True)
        alpha, beta = -CHECKMATE - 1, CHECKMATE + 1
        bestMove = rootMoves[0]
        self.partialBest = None

        for move in rootMoves:
            gamestate.makeMoves(move)
            score = -self.negamax(gamestate, depth - 1, -beta, -alpha, 1)
            gamestate.undoMove()
            if score > alpha:
                alpha = score
                bestMove = move
                self.partialBest = (score, move)
        return alpha, bestMove

    def negamax(self, gamestate, depth, alpha, beta, ply):
        self.checkTime()
        self.nodes += 1

        moves = gamestate.getValidateMoves()
        if not moves:
            return -(CHECKMATE - ply) if gamestate.checkMate else STALEMATE

        if depth == 0:
            if self.useQuiescence:
                return self.quiescence(gamestate, alpha, beta, ply, moves)
            return evaluate(gamestate)

        moves.sort(key = lambda m: self.moveOrderScore(m, ply), reverse = True)
        bestScore = -CHECKMATE - 1

        for move in moves:
            gamestate.makeMoves(move)
            score = -self.negamax(gamestate, depth - 1, -beta, -alpha, ply + 1)
            gamestate.undoMove()

            if score > bestScore:
                bestScore = score
            if score > alpha:
                alpha = score
            if alpha >= beta:
                if isQuiet(move):
                    self.storeKiller(move, ply)
                    self.history[move.startRow * 8 + move.startCol][move.endRow * 8 + move.endCol] += depth * depth
                break
        return bestScore

    # Only search captures/promotions past the horizon so the eval isn't taken mid-exchange.
    # Deeper quiescence nodes skip mate detection: they only generate legal captures, which is far cheaper
    def quiescence(self, gamestate, alpha, beta, ply, moves = None):
        self.checkTime()
        self.nodes += 1

        standPat = evaluate(gamestate) # Side to move can usually decline to capture
        if standPat >= beta or ply >= MAX_PLY - 1:
            return standPat
        if standPat > alpha:
            alpha = standPat

        if moves is None:
            captures = gamestate.getCaptureMoves()
        else:
            captures = [m for m in moves if not isQuiet(m)]
        captures.sort(key = mvvLva, reverse = True)

        for move in captures:
            gamestate.makeMoves(move)
            score = -self.quiescence(gamestate, -beta, -alpha, ply + 1)
            gamestate.undoMove()

            if score >= beta:
                return score
            if score > alpha:
                alpha = score
        return alpha

    def moveOrderScore(self, move, ply, pvMove = None):
        if pvMove is not None and move == pvMove:
            return PV_MOVE_SCORE
        if not isQuiet(move):
            return CAPTURE_SCORE + mvvLva(move)
        killers = self.killers[ply]
        for i in range(2):
            if killers[i] == move.moveID:
                return KILLER_SCORES[i]
        return self.history[move.startRow * 8 + move.startCol][move.endRow * 8 + move.endCol]

    def storeKiller(self, move, ply):
        killers = self.killers[ply]
        if killers[0] != move.moveID:
            killers[1] = killers[0]
            killers[0] = move.moveID

    def checkTime(self):
        if self.deadline is not None and time.time() > self.deadline:
            raise SearchTimeout()


def isQuiet(move):
    return move.pieceCaptured == "--" and not move.isPawnPromotion

def mvvLva(move):
    victim = mvvLvaValue[move.pieceCaptured[1]] if move.pieceCaptured != "--" else 0
    promotion = mvvLvaValue[move.promotionPiece] if move.isPawnPromotion else 0
    return (victim + promotion) * 10 - mvvLvaValue[move.pieceMoved[1]]

# Material score relative to the side to move
def evaluate(gamestate):
    score = scoreMaterial(gamestate.board)
    return score if gamestate.whiteToMove else -score

def findBestMoveAlphaBeta(gamestate, validMoves, timeLimit = TIME_LIMIT):
    return Searcher(timeLimit = timeLimit).search(gamestate, validMoves)
