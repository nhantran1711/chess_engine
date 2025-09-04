""" 
Main Driver File: 
Responsibilities: 
1. Handling user input 
2. Current Game State Update 
""" 

import pygame as p
import ChessEngine

width_image = 512
height_image = 512
dimension = 8
sq_size = height_image // dimension # 512 // 8
max_fps = 15
images = {}


# Initialize a global dictionary of images
def loadImages():
    pieces = ["wP", "wR", "wN", "wB", "wK", "wQ", "bP", "bR", "bN", "bB", "bK", "bQ"]
    for piece in pieces:
        images[piece] = p.transform.scale(p.image.load("images/" + piece + ".png"), (sq_size, sq_size))

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
    loadImages()

    running = True

    while running:
        for e in p.event.get():
            if e.type == p.QUIT:
                running = False
        drawGameState(screen, gamestate)
        clock.tick(max_fps)
        p.display.flip()

'''
All the graphics within the game state
'''

def drawGameState(screen, gamestate):
    drawBoard(screen) # Draw the sq on the board
    drawPieces(screen, gamestate.board) # Draw Pieces on top, could add key highlighting or move suggestion

'''
The top left of the board always light
'''
def drawBoard(screen):
    colours = [p.Color("white"), p.Color("gray")]
    for i in range(dimension):
        for j in range(dimension):
            colour = colours[((i + j) % 2)]
            p.draw.rect(screen, colour, p.Rect(j * sq_size, i * sq_size, sq_size, sq_size))

def drawPieces(screen, board):
    pass



if __name__ == "__main__":
    main()

