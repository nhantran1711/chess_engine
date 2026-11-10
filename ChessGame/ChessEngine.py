""" 
Engine File: 
Responsibilities: 
1. Storing data about current game's state information 
2. Store move's log 
3. Determine the valid moves 
""" 

from ChessGame.Move import Move
from ChessGame.CastleRight import CastleRights
from ChessGame import Zobrist

class GameState():
    knightDirections = [(-2, 1), (-2, -1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
    kingDirections = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
    rookDirections = [(0, 1), (0, -1), (1, 0), (-1, 0)]
    bishopDirections = [(-1, -1), (-1, 1), (1, 1), (1, -1)]

    def __init__(self):
        # 8 * 8 2 Dimensional Board 
        # Plain lists, not numpy: indexing a numpy array one square at a time is several times slower
        self.board = [
            ["bR", "bN", "bB", "bQ", "bK", "bB", "bN", "bR"],
            ["bP"] * 8,
            ["--"] * 8,
            ["--"] * 8,
            ["--"] * 8,
            ["--"] * 8,
            ["wP"] * 8,
            ["wR", "wN", "wB", "wQ", "wK", "wB", "wN", "wR"],
        ]
        self.whiteToMove = True 
        self.moveLogs = []
        self.whiteKingLocation = (7, 4)
        self.blackKingLocation = (0, 4)
        self.checkMate = False
        self.staleMate = False

        # En Passant
        self.enpassantPossbile = () # Tuple where its possible to en passant
        self.enpassantLog = [self.enpassantPossbile]

        # Checking whose has castling rights
        self.currentCastlingRight = CastleRights(True, True, True, True)
        self.castlingRightLog = [CastleRights(self.currentCastlingRight.wks, self.currentCastlingRight.bks, self.currentCastlingRight.wqs, self.currentCastlingRight.bqs)]

        # Zobrist hash of the position, updated incrementally on every move
        self.zobristKey = Zobrist.computeKey(self)
        self.zobristLog = []

        # Half moves since the last capture or pawn move, for the fifty-move rule and repetition checks
        self.halfmoveClock = 0
        self.halfmoveLog = []

    # Build a game state from a FEN string (used by perft tests)
    @classmethod
    def fromFen(cls, fen):
        gs = cls()
        fields = fen.split()
        placement, side, castling = fields[0], fields[1], fields[2]
        enpassant = fields[3] if len(fields) > 3 else '-'
        gs.halfmoveClock = int(fields[4]) if len(fields) > 4 else 0

        gs.board = [["--"] * 8 for _ in range(8)]
        for r, rankStr in enumerate(placement.split('/')):
            c = 0
            for ch in rankStr:
                if ch.isdigit():
                    c += int(ch)
                    continue
                colour = 'w' if ch.isupper() else 'b'
                gs.board[r][c] = colour + ch.upper()
                if ch == 'K':
                    gs.whiteKingLocation = (r, c)
                elif ch == 'k':
                    gs.blackKingLocation = (r, c)
                c += 1

        gs.whiteToMove = side == 'w'
        gs.currentCastlingRight = CastleRights('K' in castling, 'k' in castling, 'Q' in castling, 'q' in castling)
        gs.castlingRightLog = [CastleRights(gs.currentCastlingRight.wks, gs.currentCastlingRight.bks, gs.currentCastlingRight.wqs, gs.currentCastlingRight.bqs)]
        if enpassant != '-':
            gs.enpassantPossbile = (Move.ranks[enpassant[1]], Move.filesToCols[enpassant[0]])
        gs.enpassantLog = [gs.enpassantPossbile]
        gs.zobristKey = Zobrist.computeKey(gs)
        return gs


    def makeMoves(self, move):
        self.board[move.startRow][move.startCol] = '--'
        self.board[move.endRow][move.endCol] = move.pieceMoved
        self.moveLogs.append(move) # Log the move
        self.halfmoveLog.append(self.halfmoveClock)
        self.halfmoveClock = 0 if move.pieceMoved[1] == "P" or move.pieceCaptured != "--" else self.halfmoveClock + 1
        self.whiteToMove = not self.whiteToMove # Set up the opposite

        # Update location of the king when its move
        if move.pieceMoved == 'wK':
            self.whiteKingLocation = (move.endRow, move.endCol)
        if move.pieceMoved == 'bK':
            self.blackKingLocation = (move.endRow, move.endCol) 

        # Pawn promotion logic
        if move.isPawnPromotion == True:
            self.board[move.endRow][move.endCol] = move.pieceMoved[0] + move.promotionPiece # Promote at end rank
        
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
        self.updateZobristKey(move)
        self.castlingRightLog.append(CastleRights(self.currentCastlingRight.wks, self.currentCastlingRight.bks, self.currentCastlingRight.wqs, self.currentCastlingRight.bqs))
        self.enpassantLog.append(self.enpassantPossbile)

    # XOR out what the move removed and XOR in what it added. Runs before the logs are appended,
    # so their last entries are still the rights / en passant square from before the move
    def updateZobristKey(self, move):
        self.zobristLog.append(self.zobristKey)
        key = self.zobristKey ^ Zobrist.blackToMoveKey
        key ^= Zobrist.pieceKey(move.pieceMoved, move.startRow, move.startCol)

        placedPiece = move.pieceMoved[0] + move.promotionPiece if move.isPawnPromotion else move.pieceMoved
        key ^= Zobrist.pieceKey(placedPiece, move.endRow, move.endCol)

        if move.isEnpassantMove:
            key ^= Zobrist.pieceKey(move.pieceCaptured, move.startRow, move.endCol)
        elif move.pieceCaptured != '--':
            key ^= Zobrist.pieceKey(move.pieceCaptured, move.endRow, move.endCol)

        if move.isCastlingMove:
            rook = move.pieceMoved[0] + 'R'
            if move.endCol - move.startCol == 2: # King side, rook h -> f
                rookFrom, rookTo = move.endCol + 1, move.endCol - 1
            else: # Queen side, rook a -> d
                rookFrom, rookTo = move.endCol - 2, move.endCol + 1
            key ^= Zobrist.pieceKey(rook, move.endRow, rookFrom) ^ Zobrist.pieceKey(rook, move.endRow, rookTo)

        key ^= Zobrist.castlingKey(self.castlingRightLog[-1]) ^ Zobrist.castlingKey(self.currentCastlingRight)
        key ^= Zobrist.enpassantKey(self.enpassantLog[-1]) ^ Zobrist.enpassantKey(self.enpassantPossbile)
        self.zobristKey = key

    

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

        # If a rook is captured on its starting square, that side loses the right too
        if move.pieceCaptured == "wR" and move.endRow == 7:
            if move.endCol == 0:
                self.currentCastlingRight.wqs = False
            elif move.endCol == 7:
                self.currentCastlingRight.wks = False
        elif move.pieceCaptured == "bR" and move.endRow == 0:
            if move.endCol == 0:
                self.currentCastlingRight.bqs = False
            elif move.endCol == 7:
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
            
            self.zobristKey = self.zobristLog.pop()
            self.halfmoveClock = self.halfmoveLog.pop()

            # restore en passant state
            self.enpassantLog.pop()
            self.enpassantPossbile = self.enpassantLog[-1]

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
        

    # Has this position occurred before? zobristLog[-k] is the key k half moves ago, and only
    # positions with the same side to move, since the last irreversible move, can match
    def isRepetition(self):
        log = self.zobristLog
        key = self.zobristKey
        for i in range(2, min(self.halfmoveClock, len(log)) + 1, 2):
            if log[-i] == key:
                return True
        return False

    # Fifty-move rule or a repeated position. The search treats a single repetition as a draw:
    # if repeating was good once, the same reasoning repeats it again
    def isDraw(self):
        return self.halfmoveClock >= 100 or self.isRepetition()

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

    
    # Legal captures and promotions only, for quiescence search. Avoids legality testing every quiet move
    def getCaptureMoves(self):
        moves = self.getAllPossibleMoves(includingCastling = False)
        return [m for m in moves if (m.pieceCaptured != '--' or m.isPawnPromotion) and self.isLegalMove(m)]

    # A move is legal if it doesn't leave the mover's own king attacked
    def isLegalMove(self, move):
        self.makeMoves(move)
        self.whiteToMove = not self.whiteToMove
        legal = not self.inCheck()
        self.whiteToMove = not self.whiteToMove
        self.undoMove()
        return legal

    # Determine if the player is in check
    def inCheck(self):
        if self.whiteToMove:
            return self.sqUnderAttack(self.whiteKingLocation[0], self.whiteKingLocation[1])
        else:
            return self.sqUnderAttack(self.blackKingLocation[0], self.blackKingLocation[1])
    
    # Is (r, c) attacked by the side not to move? Looks outwards from the square instead of
    # generating every opponent move, this is the hot path of legality checking
    def sqUnderAttack(self, r, c):
        enemy = 'b' if self.whiteToMove else 'w'
        board = self.board

        # Pawns: a white pawn attacks diagonally upwards, so it sits one row below the square
        pawnRow = r - 1 if enemy == 'b' else r + 1
        if 0 <= pawnRow < 8:
            for dc in (-1, 1):
                if 0 <= c + dc < 8 and board[pawnRow][c + dc] == enemy + 'P':
                    return True

        for dr, dc in self.knightDirections:
            endRow, endCol = r + dr, c + dc
            if 0 <= endRow < 8 and 0 <= endCol < 8 and board[endRow][endCol] == enemy + 'N':
                return True

        for dr, dc in self.kingDirections:
            endRow, endCol = r + dr, c + dc
            if 0 <= endRow < 8 and 0 <= endCol < 8 and board[endRow][endCol] == enemy + 'K':
                return True

        # Sliders: walk each ray until the first piece
        for directions, sliders in ((self.rookDirections, ('R', 'Q')), (self.bishopDirections, ('B', 'Q'))):
            for dr, dc in directions:
                endRow, endCol = r + dr, c + dc
                while 0 <= endRow < 8 and 0 <= endCol < 8:
                    sq = board[endRow][endCol]
                    if sq != '--':
                        if sq[0] == enemy and sq[1] in sliders:
                            return True
                        break
                    endRow += dr
                    endCol += dc
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
                self.addPawnMove((r, c), (r - 1, c), moves)
                if r == 6 and self.board[r - 2][c] == '--': # 2 square pawn first move
                    moves.append(Move((r, c), (r - 2, c), self.board ))
            
            if c - 1 >= 0: # captures left
                if self.board[r - 1][c - 1][0] == 'b': # Enemy's piece black
                    self.addPawnMove((r, c), (r - 1, c - 1), moves)
                    # En passant
                elif (r - 1, c - 1) == self.enpassantPossbile:
                    moves.append(Move((r, c), (r - 1, c - 1), self.board, self.enpassantPossbile ))
            
            if c + 1 <= 7 : # captures right
                if self.board[r - 1][c + 1][0] == 'b':
                    self.addPawnMove((r, c), (r - 1, c + 1), moves)
                    # En passant
                elif (r - 1, c + 1) == self.enpassantPossbile:
                    moves.append(Move((r, c), (r - 1, c + 1), self.board, self.enpassantPossbile ))

        else: # Black's pawn moves:
            if self.board[r + 1][c] == '--':
                self.addPawnMove((r, c), (r + 1, c), moves)
                if r == 1 and self.board[r + 2][c] == '--': # 2 square pawn first move
                    moves.append(Move((r, c), (r + 2, c), self.board ))
            
            if c - 1 >= 0:
                if self.board[r + 1][c - 1][0] == 'w': # Enemy's piece black
                    self.addPawnMove((r, c), (r + 1, c - 1), moves)
                # En passant
                elif (r + 1, c - 1) == self.enpassantPossbile:
                    moves.append(Move((r, c), (r + 1, c - 1), self.board, self.enpassantPossbile ))

            if c + 1 <= 7 :
                if self.board[r + 1][c + 1][0] == 'w':
                    self.addPawnMove((r, c), (r + 1, c + 1), moves)
                # En passant
                elif (r + 1, c + 1) == self.enpassantPossbile:
                    moves.append(Move((r, c), (r + 1, c + 1), self.board, self.enpassantPossbile ))

    # Adds a pawn move, expanding it into all four promotions on the last rank
    def addPawnMove(self, start, end, moves):
        if end[0] == 0 or end[0] == 7:
            for piece in ["Q", "R", "B", "N"]:
                moves.append(Move(start, end, self.board, promotionPiece = piece))
        else:
            moves.append(Move(start, end, self.board))


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
            # Only the king's path must be safe; the b-file square may be attacked
            if not self.sqUnderAttack(r, c - 1) and not self.sqUnderAttack(r, c - 2):
                moves.append(Move((r, c), (r, c - 2), self.board, isCastlingMove = True))

