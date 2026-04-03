
import pygame
import random
import time

# --- Constants ---
FONT_SIZE = 20
MIN_INTERVAL = 0.5
MAX_INTERVAL = 2.0
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
ALPHANUMERIC = "abcdefghijklmnopqrstuvwxyz0123456789"

# --- Cell Class ---
class Cell:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.char = random.choice(ALPHANUMERIC)
        self.color = WHITE
        self.next_char_time = time.time() + random.uniform(MIN_INTERVAL, MAX_INTERVAL)
        self.next_color_time = time.time() + random.uniform(MIN_INTERVAL, MAX_INTERVAL)

    def update(self):
        current_time = time.time()
        if current_time >= self.next_char_time:
            self.char = random.choice(ALPHANUMERIC)
            self.next_char_time = current_time + random.uniform(MIN_INTERVAL, MAX_INTERVAL)
        if current_time >= self.next_color_time:
            self.color = (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))
            self.next_color_time = current_time + random.uniform(MIN_INTERVAL, MAX_INTERVAL)

# --- Grid Management ---
def create_grid(width, height):
    cols = width // FONT_SIZE
    rows = height // FONT_SIZE
    return [[Cell(x, y) for y in range(rows)] for x in range(cols)]

# --- Main Function ---
def main():
    pygame.init()

    # Get display info
    info = pygame.display.Info()
    screen_width, screen_height = info.current_w, info.current_h

    # Create a fullscreen display
    screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
    
    # Hide the mouse cursor for a screensaver effect
    pygame.mouse.set_visible(False)

    # Font
    try:
        font = pygame.font.SysFont("Consolas", FONT_SIZE)
    except pygame.error:
        font = pygame.font.SysFont("Courier", FONT_SIZE)

    # Pre-render character surfaces (Font Cache)
    font_cache = {char: font.render(char, True, WHITE) for char in ALPHANUMERIC}
    for char in ALPHANUMERIC:
        font_cache[char].set_colorkey(BLACK)

    grid = create_grid(screen_width, screen_height)

    running = True
    clock = pygame.time.Clock()
    frame_count = 0  # To ignore the initial mouse event

    while running:
        for event in pygame.event.get():
            # Exit on quit or any key press
            if event.type == pygame.QUIT or event.type == pygame.KEYDOWN:
                running = False
            # Exit on mouse motion, but only after the first frame
            if event.type == pygame.MOUSEMOTION and frame_count > 1:
                running = False

        # --- Update ---
        for row in grid:
            for cell in row:
                cell.update()

        # --- Draw ---
        screen.fill(BLACK)
        for x, col in enumerate(grid):
            for y, cell in enumerate(col):
                # Optimization: Use a pre-rendered surface from the cache
                char_surface = font.render(cell.char, True, cell.color)
                screen.blit(char_surface, (x * FONT_SIZE, y * FONT_SIZE))


        pygame.display.flip()
        frame_count += 1

    pygame.quit()

if __name__ == "__main__":
    main()
