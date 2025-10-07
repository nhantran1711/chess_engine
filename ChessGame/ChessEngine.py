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

    def getChessNotation(self):
        return self.getRankFile(self.startRow, self.startCol) + self.getRankFile(self.endRow, self.endCol)

    def getRankFile(self, r, c):
        return self.colsToFiles[c] + self.rowsToRanks[r]
