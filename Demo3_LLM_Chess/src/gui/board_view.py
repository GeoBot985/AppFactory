import tkinter as tk
import chess

from src.config import LIGHT_SQUARE_COLOR, DARK_SQUARE_COLOR

class BoardView(tk.Canvas):
    def __init__(self, parent, square_size=60):
        self.square_size = square_size
        self.legend_margin = 24
        canvas_size = self.legend_margin + square_size * 8
        super().__init__(parent, width=canvas_size, height=canvas_size)
        self.piece_images = {}
        self.draw_board()

    def draw_board(self):
        for row in range(8):
            for col in range(8):
                color = LIGHT_SQUARE_COLOR if (row + col) % 2 == 0 else DARK_SQUARE_COLOR
                x1 = self.legend_margin + col * self.square_size
                y1 = row * self.square_size
                x2 = x1 + self.square_size
                y2 = y1 + self.square_size
                self.create_rectangle(x1, y1, x2, y2, fill=color, outline="")
        self.draw_legend()

    def draw_legend(self):
        for col, file_name in enumerate("abcdefgh"):
            x = self.legend_margin + col * self.square_size + self.square_size // 2
            y = 8 * self.square_size + self.legend_margin // 2
            self.create_text(x, y, text=file_name, font=("Segoe UI", 12), fill="#333333", tags="legend")

        for row in range(8):
            x = self.legend_margin // 2
            y = row * self.square_size + self.square_size // 2
            self.create_text(x, y, text=str(8 - row), font=("Segoe UI", 12), fill="#333333", tags="legend")

    def update_board(self, board: chess.Board):
        self.delete("pieces")
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece:
                self.draw_piece(square, piece)

    def draw_piece(self, square, piece):
        row = 7 - chess.square_rank(square)
        col = chess.square_file(square)
        x = self.legend_margin + col * self.square_size + self.square_size // 2
        y = row * self.square_size + self.square_size // 2
        
        piece_symbol = piece.unicode_symbol(invert_color=False)

        # The default font might not support all chess characters.
        # A font like 'Segoe UI Symbol' or 'DejaVu Sans' is a good choice.
        self.create_text(x, y, text=piece_symbol, font=("Segoe UI Symbol", 36), tags="pieces")
