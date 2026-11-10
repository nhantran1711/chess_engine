
import random
import time
from ChessGame.Evaluation import evaluateWhite


piecesScore = {
    "K" : 0,
    "Q" : 8,
    "R" : 5,
    'B' : 3,
    "N": 3,
    "P": 1
}

# HIGHLY IMPORTANT VARIABLES, DO NOT CHANGE
CHECKMATE = 100000 # Well above any centipawn evaluation
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
1. Hash move: best move stored in the transposition table (at the root, the previous iteration's best)
2. Captures and promotions, by MVV-LVA (most valuable victim, least valuable attacker)
3. Killer moves: quiet moves that caused a beta cutoff at the same ply
4. Remaining quiet moves by history heuristic score

Scores are relative to the side to move. Mate is CHECKMATE - ply, so faster mates score higher.

Transposition table: positions reached by different move orders share a Zobrist key, so a result
stored once is reused. Each entry keeps the depth searched, the score and whether that score is
exact or only a bound (the search was cut off by alpha or beta), plus the best move for ordering.
'''

TIME_LIMIT = 2.0 # Seconds per AI move
MAX_DEPTH = 64
MAX_PLY = 128

# Ordering values, separate from evaluation so the king counts as the most valuable attacker
mvvLvaValue = {"P" : 1, "N" : 3, "B" : 3, "R" : 5, "Q" : 9, "K" : 10}
PV_MOVE_SCORE = 1000000
CAPTURE_SCORE = 100000
KILLER_SCORES = [90000, 80000]

TT_SIZE_BITS = 20 # 2^20 entries
TT_EXACT, TT_LOWER, TT_UPPER = 0, 1, 2 # LOWER: score >= stored (beta cutoff), UPPER: score <= stored (failed low)
MATE_BOUND = CHECKMATE - MAX_PLY


class SearchTimeout(Exception):
    pass


class Searcher():
    # usePruning turns on the selective techniques (check extension, null move, late move reductions).
    # They change scores compared to plain minimax, so the exactness tests switch them off
    def __init__(self, timeLimit = TIME_LIMIT, maxDepth = MAX_DEPTH, useQuiescence = True, useTT = True, usePruning = True):
        self.timeLimit = timeLimit
        self.maxDepth = maxDepth
        self.useQuiescence = useQuiescence
        self.useTT = useTT
        self.usePruning = usePruning
        # The table survives between searches so the next move reuses this one's work
        self.ttMask = (1 << TT_SIZE_BITS) - 1
        self.tt = [None] * (1 << TT_SIZE_BITS) # (key, depth, flag, score, moveID, age)
        self.ttAge = 0
        # Hooks for the UCI front end
        self.stopRequested = False # Set from another thread to abort the search
        self.maxNodes = None
        self.infoCallback = None # Called after each completed depth: (depth, score, nodes, seconds, pv)
        self.resetTables()

    def resetTables(self):
        self.killers = [[None, None] for _ in range(MAX_PLY)] # moveIDs
        self.history = [[0] * 64 for _ in range(64)] # [from square][to square]
        self.nodes = 0
        self.deadline = None
        self.ttProbes = 0
        self.ttHits = 0 # Probe found an entry for this exact position
        self.ttCutoffs = 0 # Hit was deep enough to return without searching

    def ttProbe(self, key):
        if not self.useTT:
            return None
        self.ttProbes += 1
        entry = self.tt[key & self.ttMask]
        if entry is not None and entry[0] == key:
            self.ttHits += 1
            return entry
        return None

    # Replace an entry from an older search, or one searched no deeper than this
    def ttStore(self, key, depth, flag, score, moveID, ply):
        if not self.useTT:
            return
        index = key & self.ttMask
        old = self.tt[index]
        if old is None or old[5] != self.ttAge or depth >= old[1]:
            self.tt[index] = (key, depth, flag, scoreToTT(score, ply), moveID, self.ttAge)

    # Iterative deepening: search depth 1, 2, 3, ... until time runs out, keep the last completed result
    def search(self, gamestate, validMoves = None):
        self.resetTables()
        self.ttAge += 1
        startTime = time.time()
        self.deadline = startTime + self.timeLimit
        startLogLength = len(gamestate.moveLogs)

        rootMoves = list(validMoves) if validMoves is not None else gamestate.getValidateMoves()
        if not rootMoves:
            return None
        random.shuffle(rootMoves) # Variety between equally scored moves

        rootMoves.sort(key = lambda m: self.moveOrderScore(m, 0), reverse = True)
        bestMove = rootMoves[0] # Fallback if not even one root move finishes: best capture by MVV-LVA
        entry = self.ttProbe(gamestate.zobristKey)
        if entry is not None:
            bestMove = next((m for m in rootMoves if m.moveID == entry[4]), bestMove)
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
            self.ttStore(gamestate.zobristKey, depth, TT_EXACT, score, move.moveID, 0)
            if self.infoCallback is not None:
                self.infoCallback(depth, score, self.nodes, time.time() - startTime, self.principalVariation(gamestate, move, depth))

            if abs(score) >= MATE_BOUND: # Forced mate found, deeper search won't change it
                break
            if time.time() - startTime > self.timeLimit / 2: # Next iteration would very likely not finish
                break

        return bestMove

    # Expected line of play: the best move, then each following position's hash move from the table
    def principalVariation(self, gamestate, bestMove, maxLength):
        pv = [bestMove]
        gamestate.makeMoves(bestMove)
        while len(pv) < maxLength:
            entry = self.ttProbe(gamestate.zobristKey)
            if entry is None:
                break
            move = next((m for m in gamestate.getValidateMoves() if m.moveID == entry[4]), None)
            if move is None:
                break
            pv.append(move)
            gamestate.makeMoves(move)
        for _ in pv:
            gamestate.undoMove()
        return pv

    def searchRoot(self, gamestate, rootMoves, depth, pvMove):
        rootMoves.sort(key = lambda m: self.moveOrderScore(m, 0, pvMove.moveID), reverse = True)
        alpha, beta = -CHECKMATE - 1, CHECKMATE + 1
        bestMove = rootMoves[0]
        self.partialBest = None

        for i, move in enumerate(rootMoves):
            gamestate.makeMoves(move)
            if i == 0 or not self.usePruning:
                score = -self.negamax(gamestate, depth - 1, -beta, -alpha, 1)
            else:
                # Principal variation search: prove the move is no better with a zero window, re-search if it is
                score = -self.negamax(gamestate, depth - 1, -alpha - 1, -alpha, 1)
                if score > alpha:
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
        if gamestate.isDraw(): # Always ply >= 1 here: the root's moves are searched from searchRoot
            return STALEMATE
        alphaOriginal = alpha
        key = gamestate.zobristKey

        # A stored result at least this deep answers the node outright if it's exact or the bound is decisive
        hashMoveID = None
        entry = self.ttProbe(key)
        if entry is not None:
            hashMoveID = entry[4]
            if entry[1] >= depth:
                score = scoreFromTT(entry[3], ply)
                flag = entry[2]
                if flag == TT_EXACT or (flag == TT_LOWER and score >= beta) or (flag == TT_UPPER and score <= alpha):
                    self.ttCutoffs += 1
                    return score

        inCheck = self.usePruning and gamestate.inCheck()
        if inCheck and ply < MAX_PLY // 2:
            depth += 1 # Check extension: a check forces a reply, so it shouldn't use up the depth

        # Leaf not in check: go straight to quiescence, which only generates captures. Building every
        # legal move here would only detect stalemate, and leaves are about half of all nodes
        if depth <= 0 and not inCheck and self.usePruning and self.useQuiescence:
            return self.quiescence(gamestate, alpha, beta, ply)

        moves = gamestate.getValidateMoves()
        if not moves:
            return -(CHECKMATE - ply) if gamestate.checkMate else STALEMATE

        if depth <= 0:
            if self.useQuiescence:
                return self.quiescence(gamestate, alpha, beta, ply, moves)
            return evaluate(gamestate)

        isPV = beta - alpha > 1 # Zero-window nodes only ask "better than alpha or not?"

        # Null-move pruning: let the opponent move twice. If we still reach beta, a real move would too.
        # Unsafe in zugzwang, which is mostly king-and-pawn endings, so those are excluded
        if (self.usePruning and not isPV and not inCheck and depth >= 3 and ply < MAX_PLY - 10
                and hasPieces(gamestate) and evaluate(gamestate) >= beta):
            reduction = 3 if depth >= 6 else 2
            gamestate.makeNullMove()
            try:
                score = -self.negamax(gamestate, depth - 1 - reduction, -beta, -beta + 1, ply + 1)
            finally:
                gamestate.undoNullMove()
            if score >= beta:
                return beta if score >= MATE_BOUND else score # Don't trust a mate found by passing

        moves.sort(key = lambda m: self.moveOrderScore(m, ply, hashMoveID), reverse = True)
        bestScore = -CHECKMATE - 1
        bestMove = moves[0]

        for i, move in enumerate(moves):
            gamestate.makeMoves(move)
            if i == 0 or not self.usePruning:
                score = -self.negamax(gamestate, depth - 1, -beta, -alpha, ply + 1)
            else:
                # Late move reductions: with good ordering, quiet moves this far down rarely matter,
                # so search them shallower first and only at full depth if they beat alpha
                reduction = 0
                if depth >= 3 and i >= 3 and not inCheck and isQuiet(move) and not gamestate.inCheck():
                    reduction = 2 if i >= 8 and depth >= 5 else 1
                score = -self.negamax(gamestate, depth - 1 - reduction, -alpha - 1, -alpha, ply + 1)
                if score > alpha and reduction > 0:
                    score = -self.negamax(gamestate, depth - 1, -alpha - 1, -alpha, ply + 1)
                if alpha < score < beta: # Principal variation search: re-search with the full window
                    score = -self.negamax(gamestate, depth - 1, -beta, -alpha, ply + 1)
            gamestate.undoMove()

            if score > bestScore:
                bestScore = score
                bestMove = move
            if score > alpha:
                alpha = score
            if alpha >= beta:
                if isQuiet(move):
                    self.storeKiller(move, ply)
                    self.history[move.startRow * 8 + move.startCol][move.endRow * 8 + move.endCol] += depth * depth
                break

        if bestScore <= alphaOriginal:
            flag = TT_UPPER
        elif bestScore >= beta:
            flag = TT_LOWER
        else:
            flag = TT_EXACT
        self.ttStore(key, depth, flag, bestScore, bestMove.moveID, ply)
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

    def moveOrderScore(self, move, ply, hashMoveID = None):
        if move.moveID == hashMoveID:
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
        if self.stopRequested or (self.deadline is not None and time.time() > self.deadline):
            raise SearchTimeout()
        if self.maxNodes is not None and self.nodes >= self.maxNodes:
            raise SearchTimeout()


# Side to move has a knight, bishop, rook or queen, so passing is very unlikely to be its best option
def hasPieces(gamestate):
    colour = "w" if gamestate.whiteToMove else "b"
    for row in gamestate.board:
        for sq in row:
            if sq[0] == colour and sq[1] in "NBRQ":
                return True
    return False

def isQuiet(move):
    return move.pieceCaptured == "--" and not move.isPawnPromotion

def mvvLva(move):
    victim = mvvLvaValue[move.pieceCaptured[1]] if move.pieceCaptured != "--" else 0
    promotion = mvvLvaValue[move.promotionPiece] if move.isPawnPromotion else 0
    return (victim + promotion) * 10 - mvvLvaValue[move.pieceMoved[1]]

# Mate scores are stored relative to the node, not the root, so they stay correct when reached at another ply
def scoreToTT(score, ply):
    if score >= MATE_BOUND:
        return score + ply
    if score <= -MATE_BOUND:
        return score - ply
    return score

def scoreFromTT(score, ply):
    if score >= MATE_BOUND:
        return score - ply
    if score <= -MATE_BOUND:
        return score + ply
    return score

# Piece-square evaluation in centipawns, relative to the side to move
def evaluate(gamestate):
    score = evaluateWhite(gamestate.board)
    return score if gamestate.whiteToMove else -score

# One searcher for the whole game so its transposition table carries over between moves
gameSearcher = Searcher()

def findBestMoveAlphaBeta(gamestate, validMoves, timeLimit = TIME_LIMIT):
    gameSearcher.timeLimit = timeLimit
    return gameSearcher.search(gamestate, validMoves)
