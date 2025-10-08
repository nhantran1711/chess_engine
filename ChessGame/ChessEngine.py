""" 
Engine File: 
Responsibilities: 
1. Storing data about current game's state information 
2. Store move's log 
3. Determine the valid moves 
""" 

import numpy as np 


class GameState(): 
    def __init__(self): 
        # 8 * 8 2 Dimensional Board 
        self.board = np.full((8, 8), "--", dtype = "<U2") 
        # Black Pieces 
        self.board[0] = ["bR", "bN", "bB", "bQ", "bK", "bB", "bN", "bR"] 
        self.board[1] = ["bP"] * 8
        # White Pieces 
        self.board[6] = ["wP"] * 8 
        self.board[7] = ["wR", "wN", "wB", "wQ", "wK", "wB", "wN", "wR"] 
        self.whiteToMove = True 
        self.moveLogs = []
    
    def makeMoves(self, move):
        self.board[move.startRow][move.startCol] = '--'
        self.board[move.endRow][move.endCol] = move.pieceMoved
        self.moveLogs.append(move) # Log the move
        self.whiteToMove = not self.whiteToMove # Set up the opposite


    def undoMove(self):
        if len(self.moveLogs) != 0:
            move = self.moveLogs.pop()
            self.board[move.startRow][move.startCol] = move.pieceMoved
            self.board[move.endRow][move.endCol] = move.pieceCaptured
            self.whiteToMove = not self.whiteToMove

    def getValidateMoves(self):
        return self.getAllPossibleMoves()

    def getAllPossibleMoves(self):
        res = []
        
        for i in range(len(self.board)):
            for j in range(len(self.board)):
                player = self.board[i][j][0]
                if (player == 'w' and self.whiteToMove) or (player == 'b' and not self.whiteToMove):
                    piece = self.board[i][j][1]
                    if piece == 'P':
                        self.getPawnMove(i, j, res)
                    elif piece == 'R':
                        self.getRookMove(i, j, res)
                    elif piece == 'N':
                        self.getKnightMove(i, j, res)
                    elif piece == 'B':
                        self.getBishopMove(i, j, res)
                    elif piece == 'Q':
                        self.getQueenMove(i, j, res)
                    elif piece == 'K':
                        self.getKingMove(i, j, res)
        return res
    
    def getPawnMove(self, r, c, moves):
        if self.whiteToMove:
            if self.board[r - 1][c] == '--':
                moves.append(Move((r, c), (r - 1, c), self.board))
                if r == 6 and self.board[r - 2][c] == '--': # 2 square pawn first move
                    moves.append(Move((r, c), (r - 2, c), self.board ))
            
            if c - 1 >= 0:
                if self.board[r - 1][c - 1][0] == 'b': # Enemy's piece black
                    moves.append(Move((r, c), (r - 1, c - 1), self.board))
            
            if c + 1 <= 7 :
                if self.board[r - 1][c + 1][0] == 'b':
                    moves.append(Move((r, c), (r - 1, c + 1), self.board))

        else: # Black's pawn moves:
            if self.board[r + 1][c] == '--':
                moves.append(Move((r, c), (r + 1, c), self.board))
                if r == 1 and self.board[r + 2][c] == '--': # 2 square pawn first move
                    moves.append(Move((r, c), (r + 2, c), self.board ))
            
            if c - 1 >= 0:
                if self.board[r + 1][c - 1][0] == 'w': # Enemy's piece black
                    moves.append(Move((r, c), (r + 1, c - 1), self.board))
            
            if c + 1 <= 7 :
                if self.board[r + 1][c + 1][0] == 'w':
                    moves.append(Move((r, c), (r + 1, c + 1), self.board))

    def getRookMove(self, r, c, moves):
        pass

    def getKnightMove(self, r, c, moves):
        pass

    def getKnightMove(self, r, c, moves):
        pass

    def getBishopMove(self, r, c, moves):
        pass

    def getQueenMove(self, r, c, moves):
        pass

    def getKingMove(self, r, c, moves):
        pass

class Move():
    ranks = {
        "1" : 7,
        "2" : 6,
        "3" : 5,
        "4" : 4,
        "5" : 3,
        "6" : 2,
        "7" : 1,
        "8" : 0
    }

    rowsToRanks = {v: k for k, v in ranks.items()}
    filesToCols = {
        "a" : 0,
        "b" : 1,
        "c" : 2,
        "d" : 3,
        "e" : 4,
        "f" : 5,
        "g" : 6,
        "h" : 7
    }
    colsToFiles = {v : k for k, v in filesToCols.items()}

    def __init__(self, start, end, board):
        self.startRow = start[0]
        self.startCol = start[1]
        self.endRow = end[0]
        self.endCol = end[1]
        self.pieceMoved = board[self.startRow][self.startCol]
        self.pieceCaptured = board[self.endRow][self.endCol]
        self.moveID = self.startRow * 1000 + self.startCol * 100 + self.endRow * 10 + self.endCol



    def __eq__(self, other):
        if isinstance(other, Move):
            return self.moveID == other.moveID
        return False

    def getChessNotation(self):
        return self.getRankFile(self.startRow, self.startCol) + self.getRankFile(self.endRow, self.endCol)

    def getRankFile(self, r, c):
        return self.colsToFiles[c] + self.rowsToRanks[r]
