""" 
Main Driver File: 
Responsibilities: 
1. Handling user input 
2. Current Game State Update 
""" 

import os
import pygame as p
from ChessGame import ChessEngine, ChessAI

width_image = 512
height_image = 512
dimension = 8
sq_size = height_image // dimension # 512 // 8
max_fps = 15
images = {}


# Initialize a global dictionary of images
def loadImages():
    pieces = ["wP", "wR", "wN", "wB", "wK", "wQ", "bP", "bR", "bN", "bB", "bK", "bQ"]

    global images
    script_dir = os.path.dirname(__file__)  # ChessGame/
    images_dir = os.path.join(script_dir, "images")
    
    for piece in pieces:
        path = os.path.join(images_dir, piece + ".png")
        images[piece] = p.transform.scale(p.image.load(path), (sq_size, sq_size))

'''
The Main Driver of the code.
This will handling user's input and update the graphics
'''

def main():
    p.init()

    screen = p.display.set_mode((width_image, height_image))
    screen.fill(p.Color("white"))

    clock = p.time.Clock()
    gamestate = ChessEngine.GameState()
    validMoves = gamestate.getValidateMoves()
    moveMade = False
    animate = False
    loadImages()
    squareSelected = () # Init no square first, last click of user's input (tuple(row, rol))
    playerClicks = [] # player click's two tuples : eg[(6, 4), (4, 4)]
    # Checking game over
    gameOver = False

    running = True

    playerOne = True # If human -> True, AI plays -> False
    playerTwo = False # If human black -> True, AI plays black -> False

    while running:
        isHumanTurn = (gamestate.whiteToMove and playerOne) or (not gamestate.whiteToMove and playerTwo)


        for e in p.event.get():
            if e.type == p.QUIT:
                running = False
            
            # Mouse handling
            elif e.type == p.MOUSEBUTTONDOWN:
                if not gameOver and isHumanTurn:
                    location = p.mouse.get_pos() # x, y location
                    col = location[0] // sq_size
                    row = location[1] // sq_size

                    # Handling user clicked the same square twice:
                    if squareSelected == (row, col):
                        squareSelected = () # Deselect
                        playerClicks = [] # Clear 
                    else:
                        squareSelected = (row, col)
                        playerClicks.append(squareSelected)
                    
                    if len(playerClicks) == 2:
                        move = ChessEngine.Move(playerClicks[0], playerClicks[1], gamestate.board)
                        print(move.getChessNotation())

                        for i in range(len(validMoves)):
                            if move == validMoves[i]:
                                gamestate.makeMoves(validMoves[i])
                                moveMade = True
                                animate = True
                                squareSelected = () # Reset
                                playerClicks = []
                        if not moveMade:
                            playerClicks = [squareSelected]
            # Key handling
            elif e.type == p.KEYDOWN:
                # Undo key : z
                if e.key == p.K_z: # Undo key
                    gamestate.undoMove()
                    moveMade = True
                    animate = False
                
                # Reset key : r
                if e.key == p.K_r:
                    gamestate = ChessEngine.GameState()
                    validMoves = gamestate.getValidateMoves()
                    squareSelected = ()
                    playerClicks = []
                    moveMade = False
                    animate = False

        # Finder move AI
        if not gameOver and not isHumanTurn:
            # Finding the best move at the current board state
            AIMove = ChessAI.findBestMove(gamestate, validMoves)
            
            if AIMove is None:
                AIMove = ChessAI.randomMove(validMoves)

            gamestate.makeMoves(AIMove)
            moveMade = True
            animate = True

            
        if moveMade == True:
            if animate:
                animatemove(gamestate.moveLogs[-1], screen, gamestate.board, clock)
            validMoves = gamestate.getValidateMoves()
            moveMade = False
            animate = False
            
        
        drawGameState(screen, gamestate, validMoves, squareSelected)

        if gamestate.checkMate:
            gameOver = True
            if gamestate.whiteToMove:
                drawText(screen, "Black wins")
            else:
                drawText(screen, "White wins")
            
        elif gamestate.staleMate:
            gameOver = True
            drawText(screen, "Stalemate!")
        clock.tick(max_fps)
        p.display.flip()

'''
All the graphics within the game state
'''

def drawGameState(screen, gamestate, validMoves, sqSelected):
    # Draw the sq on the board
    drawBoard(screen) 

    # Highlighting the moves and sq before draw the piece
    highlightingsq(screen, gamestate, validMoves, sqSelected)

    # Draw Pieces on top
    drawPieces(screen, gamestate.board) 


'''
The top left of the board always light
'''
def drawBoard(screen):
    global colours
    colours = [p.Color("white"), p.Color("gray")]

    # m * n time complexity 
    for i in range(dimension):
        for j in range(dimension):
            colour = colours[((i + j) % 2)]
            p.draw.rect(screen, colour, p.Rect(j * sq_size, i * sq_size, sq_size, sq_size))

def drawPieces(screen, board):
    
    # m * n time complexity 
    for row in range(dimension):
        for col in range(dimension):
            piece = board[row][col]
            if piece != "--":
                screen.blit(images[piece], p.Rect(col * sq_size, row * sq_size, sq_size, sq_size)) 


# Highlighting square
def highlightingsq(screen, gamestate, validMoves, sqSelected):

    # Make sure sq is not empty
    if sqSelected:
        r, c = sqSelected


        # Fixing this
        who_to_move = None
        if gamestate.whiteToMove:
            who_to_move = "w"
        else:
            who_to_move = "b"

        # Check whethere location is check on their own square

        if gamestate.board[r][c][0] == who_to_move:

            # Highlightin the selected sq
            s = p.Surface((sq_size, sq_size))

            # Tranparency value
            s.set_alpha(150)

            # Colour
            s.fill(p.Color("blue"))

            # Bliting the surface s to location
            screen.blit(s, (c * sq_size, r * sq_size))

            # Highting moves from the selected square
            s.fill(p.Color("yellow"))

            # Getting all valid moves
            for move in validMoves:
                if move.startRow == r and move.startCol == c:
                    screen.blit(s, (sq_size * move.endCol, sq_size * move.endRow))


# Animating move
def animatemove(move, screen, board, clock):
    global colours

    dR = move.endRow - move.startRow
    dC = move.endCol - move.startCol

    # Frame to move one sq
    frames = 5
    frameCount = (abs(dR) + abs(dC)) * (frames)

    for frame in range(frameCount + 1):
        r, c = ((move.startRow + dR * frame / frameCount, move.startCol + dC * frame / frameCount))
        drawBoard(screen)
        drawPieces(screen, board)

        # Erase move from ending sq
        color = colours[(move.endRow + move.endCol) % 2]
        endSq = p.Rect(move.endCol * sq_size, move.endRow * sq_size, sq_size, sq_size)
        p.draw.rect(screen, color, endSq)

        # Draw captured piece onto
        if move.pieceCaptured != '--':
            # print("Checking")
            screen.blit(images[move.pieceCaptured], endSq)

        # Drawing the moving piece
        screen.blit(images[move.pieceMoved], p.Rect(c * sq_size, r * sq_size, sq_size, sq_size))
        p.display.flip()

        clock.tick(60)


# Draw Text
def drawText(screen, text):
    # Getting arial font
    font = p.font.SysFont("arial", 32, True, False)

    # Text object rendering giving text
    textObject = font.render(text, 0, p.Color('Black'))

    # Location for textObject
    textLocation = p.Rect(0, 0, width_image, height_image).move(width_image / 2 - textObject.get_width() / 2, height_image / 2 - textObject.get_width() / 2)

    screen.blit(textObject, textLocation)

if __name__ == "__main__":
    main()

