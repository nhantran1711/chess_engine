""" 
Engine File: 
Responsibilities: 
1. Storing data about current game's state information 
2. Store move's log 
3. Determine the valid moves 
""" 

import numpy as np 
from ChessGame.Move import Move
from ChessGame.CastleRight import CastleRights

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

        # En Passant
        self.enpassantPossbile = () # Tuple where its possible to en passant

        # Checking whose has castling rights
        self.currentCastlingRight = CastleRights(True, True, True, True)
        self.castlingRightLog = [CastleRights(self.currentCastlingRight.wks, self.currentCastlingRight.bks, self.currentCastlingRight.wqs, self.currentCastlingRight.bqs)]

    
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
        
        # Logic for en passant
        if move.isEnpassantMove:
            self.board[move.startRow][move.endCol] = '--'
        
        # Update game state for every move possible for en passant
        if move.pieceMoved[1] == "P" and abs(move.startRow - move.endRow) == 2: # only 2 sq on pawn advance
            self.enpassantPossbile = ((move.startRow + move.endRow) // 2, move.startCol)
        else:
            self.enpassantPossbile = ()
        
        # Caslte Move
        if move.isCastlingMove:
            if move.endCol - move.startCol == 2: # King side castle
                self.board[move.endRow][move.endCol - 1] = self.board[move.endRow][move.endCol + 1] # moves the rook
                self.board[move.endRow][move.endCol + 1] = "--"
            else: # Queen side castle
                self.board[move.endRow][move.endCol + 1 ] = self.board[move.endRow][move.endCol - 2] # Moves the rook
                self.board[move.endRow][move.endCol - 2] = "--"
        # Update castling right
        # If the rook or king move, we NEED to update it
        self.updateCastleRight(move)
        self.castlingRightLog.append(CastleRights(self.currentCastlingRight.wks, self.currentCastlingRight.bks, self.currentCastlingRight.wqs, self.currentCastlingRight.bqs))

    

    # Update castling right
    def updateCastleRight(self, move):
        # If they move white king
        if move.pieceMoved == 'wK':
            self.currentCastlingRight.wks = False
            self.currentCastlingRight.wqs = False
        # IF they move the black king
        elif move.pieceMoved == "bK":
            self.currentCastlingRight.bks = False
            self.currentCastlingRight.bqs = False
        # If they moved the white rook
        elif move.pieceMoved == "wR":
            # White position
            if move.startRow == 7:
                # If its a left rook
                if move.startCol == 0: 
                    self.currentCastlingRight.wqs = False
                # If its a right rook
                elif move.startCol == 7:
                    self.currentCastlingRight.wks = False
                            
        # If they moved a black rook
        elif move.pieceMoved == "bR":
            # White position
            if move.startRow == 0:
                # If its a left rook
                if move.startCol == 0: 
                    self.currentCastlingRight.bqs = False
                # If its a right rook
                elif move.startCol == 7:
                    self.currentCastlingRight.bks = False
        


    def undoMove(self):
        if len(self.moveLogs) != 0: # There is move to undo
            move = self.moveLogs.pop()
            self.board[move.startRow][move.startCol] = move.pieceMoved
            self.board[move.endRow][move.endCol] = move.pieceCaptured
            self.whiteToMove = not self.whiteToMove
            if move.pieceMoved == 'wK':
                self.whiteKingLocation = (move.startRow, move.startCol)
            if move.pieceMoved == 'bK':
                self.blackKingLocation = (move.startRow, move.startCol) 
            
            # restore en passant state
            self.enpassantPossbile = move.prevEnpassantPossbile

            # restore captured pawn
            if move.isEnpassantMove:
                self.board[move.endRow][move.endCol] = "--"
                self.board[move.startRow][move.endCol] = move.pieceCaptured
            
            # Undo castling rights move:
            self.castlingRightLog.pop()

            # Set current castling rights to the last available ones
            castleRights = self.castlingRightLog[-1]
            self.currentCastlingRight = CastleRights(castleRights.wks, castleRights.bks, castleRights.wqs, castleRights.bqs)

            # Undo castling moves
            if move.isCastlingMove:
                if move.endCol - move.startCol == 2: # King side castling move
                    self.board[move.endRow][move.endCol + 1] = self.board[move.endRow][move.endCol - 1]
                    self.board[move.endRow][move.endCol - 1] = "--"
                else: # Queen side
                    self.board[move.endRow][move.endCol - 2] = self.board[move.endRow][move.endCol + 1]
                    self.board[move.endRow][move.endCol + 1] = "--"
            
            # Adding condition checkmate, stalemate for AI
            self.checkMate = False
            self.staleMate = False
        

    def getValidateMoves(self):
        # Tracking valid
        # 1) Generate all moves
        # 2) For each move, make the move
        # 3) Generate all oppenent's moves
        # 4) For each move, see if they are attacking ur king

        tempEnpassantPossible = self.enpassantPossbile # Save valid en passant for quite generate all valid moves
        # Save the castlign rights
        tempCastlingRights = CastleRights(self.currentCastlingRight.wks, self.currentCastlingRight.bks, self.currentCastlingRight.wqs, self.currentCastlingRight.bqs)


        moves = self.getAllPossibleMoves()

        # # Generates castling moves if its based on the allay colour
        
        # if self.whiteToMove:
        #     self.getCastlingMoves(self.whiteKingLocation[0], self.whiteKingLocation[1], moves)
        # else:
        #     self.getCastlingMoves(self.blackKingLocation[0], self.blackKingLocation[1], moves)
        
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

        # Assign it back
        self.enpassantPossbile = tempEnpassantPossible
        self.currentCastlingRight = tempCastlingRights
        return moves

    
    # Determine if the player is in check
    def inCheck(self):
        if self.whiteToMove:
            return self.sqUnderAttack(self.whiteKingLocation[0], self.whiteKingLocation[1])
        else:
            return self.sqUnderAttack(self.blackKingLocation[0], self.blackKingLocation[1])
    
    def sqUnderAttack(self, r, c):
        self.whiteToMove = not self.whiteToMove
        oppMoves = self.getAllPossibleMoves(includingCastling = False) # Disable castling during attack
        self.whiteToMove = not self.whiteToMove

        for move in oppMoves:
            if move.endRow == r and move.endCol == c:
                return True
        return False


    def getAllPossibleMoves(self, includingCastling = True):
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
                        self.getKingMove(i, j, res, includingCastling)
                    else:
                        print('Wrong')
        return res
    
    def getPawnMove(self, r, c, moves):
        if self.whiteToMove:
            if self.board[r - 1][c] == '--':
                moves.append(Move((r, c), (r - 1, c), self.board))
                if r == 6 and self.board[r - 2][c] == '--': # 2 square pawn first move
                    moves.append(Move((r, c), (r - 2, c), self.board ))
            
            if c - 1 >= 0: # captures left
                if self.board[r - 1][c - 1][0] == 'b': # Enemy's piece black
                    moves.append(Move((r, c), (r - 1, c - 1), self.board))
                    # En passant
                elif (r - 1, c - 1) == self.enpassantPossbile:
                    moves.append(Move((r, c), (r - 1, c - 1), self.board, self.enpassantPossbile ))
            
            if c + 1 <= 7 : # captures right
                if self.board[r - 1][c + 1][0] == 'b':
                    moves.append(Move((r, c), (r - 1, c + 1), self.board))
                    # En passant
                elif (r - 1, c + 1) == self.enpassantPossbile:
                    moves.append(Move((r, c), (r - 1, c + 1), self.board, self.enpassantPossbile ))

        else: # Black's pawn moves:
            if self.board[r + 1][c] == '--':
                moves.append(Move((r, c), (r + 1, c), self.board))
                if r == 1 and self.board[r + 2][c] == '--': # 2 square pawn first move
                    moves.append(Move((r, c), (r + 2, c), self.board ))
            
            if c - 1 >= 0:
                if self.board[r + 1][c - 1][0] == 'w': # Enemy's piece black
                    moves.append(Move((r, c), (r + 1, c - 1), self.board))
                # En passant
                elif (r + 1, c - 1) == self.enpassantPossbile:
                    moves.append(Move((r, c), (r + 1, c - 1), self.board, self.enpassantPossbile ))

            if c + 1 <= 7 :
                if self.board[r + 1][c + 1][0] == 'w':
                    moves.append(Move((r, c), (r + 1, c + 1), self.board))
                # En passant
                elif (r + 1, c + 1) == self.enpassantPossbile:
                    moves.append(Move((r, c), (r + 1, c + 1), self.board, self.enpassantPossbile ))


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

    def getKingMove(self, r, c, moves, includingCastling = True):
        directions = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
        alley = 'w' if self.whiteToMove else 'b'

        for move in directions:
            endRow = r + move[0]
            endCol = c + move[1]
            if 0 <= endRow < 8 and 0 <= endCol < 8:
                sq = self.board[endRow][endCol]
                if sq[0] != alley:
                    moves.append(Move((r, c), (endRow, endCol), self.board))
        
        # Only generate castling in normal move givin:
        if includingCastling:
            self.getCastlingMoves(r, c, moves)


    # Get all valid castling moves for king at pos (r, c)
    def getCastlingMoves(self, r, c, moves):

        if not moves:
            return
        
        if self.sqUnderAttack(r, c):
            return

        if (self.whiteToMove and self.currentCastlingRight.wks) or (not self.whiteToMove and self.currentCastlingRight.bks):
            self.getKingSideCastlingMove(r, c, moves)
        
        if (self.whiteToMove and self.currentCastlingRight.wqs) or (not self.whiteToMove and self.currentCastlingRight.bqs):
            self.getQueenSideCastlingMove(r, c, moves)

    def getKingSideCastlingMove(self, r, c, moves):
        if self.board[r][c + 1] == '--' and self.board[r][c + 2] == '--':
            if not self.sqUnderAttack(r, c + 1) and not self.sqUnderAttack(r, c + 2):
                moves.append(Move((r, c), (r, c + 2), self.board, isCastlingMove = True))
    
    def getQueenSideCastlingMove(self, r, c, moves):
        if self.board[r][c - 1] == '--' and self.board[r][c - 2] == '--' and self.board[r][c - 3] == "--":
            if not self.sqUnderAttack(r, c - 1) and not self.sqUnderAttack(r, c - 2) and not self.sqUnderAttack(r, c - 3):
                moves.append(Move((r, c), (r, c - 2), self.board, isCastlingMove = True))

