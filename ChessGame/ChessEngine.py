""" 
Engine File: 
Responsibilities: 
1. Storing data about current game's state information 
2. Store move's log 
3. Determine the valid moves 
""" 

import numpy as np 
from ChessGame.Move import Move

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
        self.whiteKingLocation = (7, 4)
        self.blackKingLocation = (0, 4)
        self.checkMate = False
        self.staleMate = False
    
    def makeMoves(self, move):
        self.board[move.startRow][move.startCol] = '--'
        self.board[move.endRow][move.endCol] = move.pieceMoved
        self.moveLogs.append(move) # Log the move
        self.whiteToMove = not self.whiteToMove # Set up the opposite

        # Update location of the king when its move
        if move.pieceMoved == 'wK':
            self.whiteKingLocation = (move.endRow, move.endCol)
        if move.pieceMoved == 'bK':
            self.blackKingLocation = (move.endRow, move.endCol) 

        # Pawn promotion logic -> Always make it a queen
        if move.isPawnPromotion == True:
            self.board[move.endRow][move.endCol] = move.pieceMoved[0] + "Q" # Promote at end rank


    def undoMove(self):
        if len(self.moveLogs) != 0:
            move = self.moveLogs.pop()
            self.board[move.startRow][move.startCol] = move.pieceMoved
            self.board[move.endRow][move.endCol] = move.pieceCaptured
            self.whiteToMove = not self.whiteToMove
            if move.pieceMoved == 'wK':
                self.whiteKingLocation = (move.startRow, move.startCol)
            if move.pieceMoved == 'bK':
                self.blackKingLocation = (move.startRow, move.startCol) 

    def getValidateMoves(self):
        # Tracking valid
        # 1) Generate all moves
        # 2) For each move, make the move
        # 3) Generate all oppenent's moves
        # 4) For each move, see if they are attacking ur king

        moves = self.getAllPossibleMoves()
        
        for i in range(len(moves) -1, -1, -1):
            self.makeMoves(moves[i])
            self.whiteToMove = not self.whiteToMove
            if self.inCheck():
                moves.remove(moves[i])
            self.whiteToMove = not self.whiteToMove
            self.undoMove()
        
        if len(moves) == 0:
            if self.inCheck():
                self.checkMate = True
            else:
                self.staleMate = True
        else:
            self.checkMate = False
            self.staleMate = False
        
        return moves

    
    # Determine if the player is in check
    def inCheck(self):
        if self.whiteToMove:
            return self.sqUnderAttack(self.whiteKingLocation[0], self.whiteKingLocation[1])
        else:
            return self.sqUnderAttack(self.blackKingLocation[0], self.blackKingLocation[1])
    
    def sqUnderAttack(self, r, c):
        self.whiteToMove = not self.whiteToMove
        oppMoves = self.getAllPossibleMoves()
        self.whiteToMove = not self.whiteToMove

        for move in oppMoves:
            if move.endRow == r and move.endCol == c:
                return True
        return False


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
                    else:
                        print('Wrong')
        print(piece)
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
        enemy = ''
        if self.whiteToMove:
            enemy = 'b'
        else:
            enemy = 'w'
        
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        for d in directions:
            for i in range(1, 8):
                endRow = r + d[0] * i
                endCol = c + d[1] * i
                if 0 <= endRow < 8 and 0 <= endCol < 8: # valid on board
                    sq = self.board[endRow][endCol]
                    if sq == '--': # empty
                        moves.append(Move((r, c), (endRow, endCol), self.board))
                    elif sq[0] == enemy:
                        moves.append(Move((r, c), (endRow, endCol), self.board))
                        break
                    else:
                        break
                else: # Off board
                    break

    def getKnightMove(self, r, c, moves):
        directions = [(-2, 1), (-2, -1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
        alley = 'w' if self.whiteToMove else 'b'
        for move in directions:
            endRow = r + move[0]
            endCol = c + move[1]
            if 0 <= endRow < 8 and 0 <= endCol < 8:
                sq = self.board[endRow][endCol]
                if sq[0] != alley:
                    moves.append(Move((r, c), (endRow, endCol), self.board))




    def getBishopMove(self, r, c, moves):
        directions = [(-1, -1), (-1, 1), (1, 1,), (1, -1)]
        enemy = 'b' if self.whiteToMove else 'w'

        for move in directions:
            for i in range(1, 8):
                endRow = r + move[0] * i
                endCol = c + move[1] * i
                if 0 <= endRow < 8 and 0 <= endCol < 8:
                    sq = self.board[endRow][endCol]
                    if sq == '--':
                        moves.append(Move((r, c), (endRow, endCol), self.board))
                    elif sq[0] == enemy:
                        moves.append(Move((r, c), (endRow, endCol), self.board))
                        break
                    else:
                        break
                else:
                    break

    def getQueenMove(self, r, c, moves):
        self.getBishopMove(r, c, moves)
        self.getRookMove(r, c, moves)

    def getKingMove(self, r, c, moves):
        directions = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
        alley = 'w' if self.whiteToMove else 'b'

        for move in directions:
            endRow = r + move[0]
            endCol = c + move[1]
            if 0 <= endRow < 8 and 0 <= endCol < 8:
                sq = self.board[endRow][endCol]
                if sq[0] != alley:
                    moves.append(Move((r, c), (endRow, endCol), self.board))


