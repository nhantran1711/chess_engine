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
    queenDirections = rookDirections + bishopDirections

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



    # Pass the turn, for null-move pruning in the search. Logged as None so undoMove reverses it.
    # The halfmove clock restarts so repetition checks never look back across a null move
    def makeNullMove(self):
        self.moveLogs.append(None)
        self.halfmoveLog.append(self.halfmoveClock)
        self.halfmoveClock = 0
        self.zobristLog.append(self.zobristKey)
        self.zobristKey ^= Zobrist.blackToMoveKey ^ Zobrist.enpassantKey(self.enpassantPossbile) ^ Zobrist.enpassantKey(())
        self.whiteToMove = not self.whiteToMove
        self.enpassantPossbile = ()
        self.enpassantLog.append(())
        self.castlingRightLog.append(CastleRights(self.currentCastlingRight.wks, self.currentCastlingRight.bks, self.currentCastlingRight.wqs, self.currentCastlingRight.bqs))

    def undoNullMove(self):
        self.moveLogs.pop()
        self.halfmoveClock = self.halfmoveLog.pop()
        self.zobristKey = self.zobristLog.pop()
        self.whiteToMove = not self.whiteToMove
        self.enpassantLog.pop()
        self.enpassantPossbile = self.enpassantLog[-1]
        self.castlingRightLog.pop()

    def undoMove(self):
        if len(self.moveLogs) != 0 and self.moveLogs[-1] is None:
            self.undoNullMove()
        elif len(self.moveLogs) != 0: # There is move to undo
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
        moves = self.filterLegal(self.getAllPossibleMoves())
        if len(moves) == 0:
            if self.inCheck():
                self.checkMate = True
            else:
                self.staleMate = True
        else:
            self.checkMate = False
            self.staleMate = False
        return moves

    # Legal captures and promotions only, for quiescence search
    def getCaptureMoves(self):
        return self.filterLegal(self.getAllPossibleMoves(includingCastling = False, capturesOnly = True))

    # Keep the moves that don't leave the mover's king attacked. Instead of playing every move
    # and testing for check, work out once which pieces give check and which are pinned:
    #   - the king may go to any square the enemy doesn't attack
    #   - with two checkers only the king can move
    #   - with one checker, another piece must capture it or step between it and the king
    #   - a pinned piece may only move along the line of its pin
    # Castling is already checked by its generator. En passant can uncover a sideways attack
    # through both pawns, so it's rare enough to test by playing it
    def filterLegal(self, moves):
        kr, kc = self.whiteKingLocation if self.whiteToMove else self.blackKingLocation
        checkers, blockSquares, pins = self.checksAndPins(kr, kc)
        board = self.board
        legal = []
        for move in moves:
            sr, sc, er, ec = move.startRow, move.startCol, move.endRow, move.endCol
            if sr == kr and sc == kc:
                if move.isCastlingMove:
                    legal.append(move)
                    continue
                # Lift the king so a slider checking along the line still attacks the square behind it
                king = board[kr][kc]
                board[kr][kc] = '--'
                attacked = self.sqUnderAttack(er, ec)
                board[kr][kc] = king
                if not attacked:
                    legal.append(move)
            elif move.isEnpassantMove:
                if self.isLegalMove(move):
                    legal.append(move)
            elif checkers > 1:
                continue
            elif checkers == 1 and (er, ec) not in blockSquares:
                continue
            else:
                pin = pins.get((sr, sc))
                # Pinned: the destination must stay on the king's line through the piece
                if pin is None or (er - kr) * pin[1] == (ec - kc) * pin[0]:
                    legal.append(move)
        return legal

    # Count the pieces checking the king at (kr, kc), the squares that answer a single check
    # (the checker and, for a slider, the squares between), and the own pieces pinned to the king
    def checksAndPins(self, kr, kc):
        board = self.board
        ally, enemy = ('w', 'b') if self.whiteToMove else ('b', 'w')
        checkers = 0
        blockSquares = set()
        pins = {} # (row, col) of pinned piece -> direction of the pin from the king

        for i, (dr, dc) in enumerate(self.rookDirections + self.bishopDirections):
            sliders = ('R', 'Q') if i < 4 else ('B', 'Q')
            pinned = None
            path = []
            r, c = kr + dr, kc + dc
            while 0 <= r < 8 and 0 <= c < 8:
                sq = board[r][c]
                path.append((r, c))
                if sq != '--':
                    if sq[0] == ally:
                        if pinned is not None:
                            break # Two own pieces in the way, no pin
                        pinned = (r, c)
                    else:
                        if sq[1] in sliders:
                            if pinned is None:
                                checkers += 1
                                blockSquares.update(path)
                            else:
                                pins[pinned] = (dr, dc)
                        break
                r += dr
                c += dc

        for dr, dc in self.knightDirections:
            r, c = kr + dr, kc + dc
            if 0 <= r < 8 and 0 <= c < 8 and board[r][c] == enemy + 'N':
                checkers += 1
                blockSquares.add((r, c))

        pawnRow = kr - 1 if ally == 'w' else kr + 1
        if 0 <= pawnRow < 8:
            for dc in (-1, 1):
                if 0 <= kc + dc < 8 and board[pawnRow][kc + dc] == enemy + 'P':
                    checkers += 1
                    blockSquares.add((pawnRow, kc + dc))

        return checkers, blockSquares, pins

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


    # Pseudo-legal moves (may leave the king in check; filterLegal removes those).
    # capturesOnly keeps captures and promotions, for quiescence search
    def getAllPossibleMoves(self, includingCastling = True, capturesOnly = False):
        res = []
        ally = 'w' if self.whiteToMove else 'b'
        for r, row in enumerate(self.board):
            for c, sq in enumerate(row):
                if sq[0] != ally:
                    continue
                piece = sq[1]
                if piece == 'P':
                    self.getPawnMove(r, c, res, capturesOnly)
                elif piece == 'N':
                    self.getStepMoves(r, c, res, self.knightDirections, capturesOnly)
                elif piece == 'B':
                    self.getSlideMoves(r, c, res, self.bishopDirections, capturesOnly)
                elif piece == 'R':
                    self.getSlideMoves(r, c, res, self.rookDirections, capturesOnly)
                elif piece == 'Q':
                    self.getSlideMoves(r, c, res, self.queenDirections, capturesOnly)
                else:
                    self.getStepMoves(r, c, res, self.kingDirections, capturesOnly)
                    if includingCastling and not capturesOnly:
                        self.getCastlingMoves(r, c, res)
        return res

    def getPawnMove(self, r, c, moves, capturesOnly = False):
        board = self.board
        if self.whiteToMove:
            step, startRow, enemy = -1, 6, 'b'
        else:
            step, startRow, enemy = 1, 1, 'w'
        endRow = r + step
        promotes = endRow == 0 or endRow == 7

        if board[endRow][c] == '--' and (promotes or not capturesOnly):
            self.addPawnMove((r, c), (endRow, c), moves)
            if r == startRow and board[endRow + step][c] == '--': # 2 square pawn first move
                moves.append(Move((r, c), (endRow + step, c), board))

        for endCol in (c - 1, c + 1):
            if 0 <= endCol < 8:
                if board[endRow][endCol][0] == enemy:
                    self.addPawnMove((r, c), (endRow, endCol), moves)
                elif (endRow, endCol) == self.enpassantPossbile:
                    moves.append(Move((r, c), (endRow, endCol), board, self.enpassantPossbile))

    # Adds a pawn move, expanding it into all four promotions on the last rank
    def addPawnMove(self, start, end, moves):
        if end[0] == 0 or end[0] == 7:
            for piece in ["Q", "R", "B", "N"]:
                moves.append(Move(start, end, self.board, promotionPiece = piece))
        else:
            moves.append(Move(start, end, self.board))

    # Knight and king: one step in each direction
    def getStepMoves(self, r, c, moves, directions, capturesOnly = False):
        board = self.board
        ally = 'w' if self.whiteToMove else 'b'
        for dr, dc in directions:
            endRow, endCol = r + dr, c + dc
            if 0 <= endRow < 8 and 0 <= endCol < 8:
                sq = board[endRow][endCol]
                if sq[0] != ally and (sq != '--' or not capturesOnly):
                    moves.append(Move((r, c), (endRow, endCol), board))

    # Bishop, rook and queen: slide until blocked, capturing the first enemy piece
    def getSlideMoves(self, r, c, moves, directions, capturesOnly = False):
        board = self.board
        enemy = 'b' if self.whiteToMove else 'w'
        for dr, dc in directions:
            endRow, endCol = r + dr, c + dc
            while 0 <= endRow < 8 and 0 <= endCol < 8:
                sq = board[endRow][endCol]
                if sq == '--':
                    if not capturesOnly:
                        moves.append(Move((r, c), (endRow, endCol), board))
                else:
                    if sq[0] == enemy:
                        moves.append(Move((r, c), (endRow, endCol), board))
                    break
                endRow += dr
                endCol += dc


    # Get all valid castling moves for king at pos (r, c)
    def getCastlingMoves(self, r, c, moves):
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

