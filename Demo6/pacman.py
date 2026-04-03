import curses
import random
import time


PELLET_COUNT = 10
FRAME_DELAY_SECONDS = 0.12


def clamp_dimensions(height: int, width: int) -> tuple[int, int]:
    """Ensure the board is large enough to play."""
    return max(height, 10), max(width, 20)


def create_border(height: int, width: int) -> list[list[str]]:
    board = [[" " for _ in range(width)] for _ in range(height)]

    for x in range(width):
        board[0][x] = "-"
        board[height - 1][x] = "-"

    for y in range(height):
        board[y][0] = "|"
        board[y][width - 1] = "|"

    return board


def place_pellets(
    board: list[list[str]],
    width: int,
    height: int,
    blocked: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    pellets: set[tuple[int, int]] = set()

    while len(pellets) < PELLET_COUNT:
        x = random.randint(1, width - 2)
        y = random.randint(1, height - 2)

        if (x, y) not in blocked:
            pellets.add((x, y))

    for x, y in pellets:
        board[y][x] = "."

    return pellets


def draw(
    screen: curses.window,
    board: list[list[str]],
    pacman: tuple[int, int],
    ghost: tuple[int, int],
    score: int,
) -> None:
    screen.clear()
    screen.addstr(0, 0, f"Score: {score}   Move with arrows, quit with q")

    for row_index, row in enumerate(board, start=1):
        screen.addstr(row_index, 0, "".join(row))

    pacman_x, pacman_y = pacman
    ghost_x, ghost_y = ghost
    screen.addch(pacman_y + 1, pacman_x, "P")
    screen.addch(ghost_y + 1, ghost_x, "G")
    screen.refresh()


def move_pacman(
    key: int,
    pacman_x: int,
    pacman_y: int,
    width: int,
    height: int,
) -> tuple[int, int]:
    new_x, new_y = pacman_x, pacman_y

    if key == curses.KEY_UP:
        new_y -= 1
    elif key == curses.KEY_DOWN:
        new_y += 1
    elif key == curses.KEY_LEFT:
        new_x -= 1
    elif key == curses.KEY_RIGHT:
        new_x += 1

    if 1 <= new_x <= width - 2 and 1 <= new_y <= height - 2:
        return new_x, new_y

    return pacman_x, pacman_y


def move_ghost(
    ghost_x: int,
    ghost_y: int,
    width: int,
    height: int,
) -> tuple[int, int]:
    delta_x, delta_y = random.choice(
        [(-1, 0), (1, 0), (0, -1), (0, 1), (0, 0)]
    )
    new_x = ghost_x + delta_x
    new_y = ghost_y + delta_y

    if 1 <= new_x <= width - 2 and 1 <= new_y <= height - 2:
        return new_x, new_y

    return ghost_x, ghost_y


def run_game(screen: curses.window) -> None:
    curses.curs_set(0)
    curses.noecho()
    screen.keypad(True)
    screen.timeout(int(FRAME_DELAY_SECONDS * 1000))

    raw_height, raw_width = screen.getmaxyx()
    height, width = clamp_dimensions(raw_height - 2, raw_width)
    board = create_border(height, width)

    pacman = (width // 2, height // 2 - 1)
    ghost = (width // 2, height // 2 + 1)
    pellets = place_pellets(board, width, height, {pacman, ghost})
    score = 0

    while True:
        draw(screen, board, pacman, ghost, score)
        key = screen.getch()

        if key == ord("q"):
            break

        pacman = move_pacman(key, pacman[0], pacman[1], width, height)

        if pacman in pellets:
            pellets.remove(pacman)
            board[pacman[1]][pacman[0]] = " "
            score += 1

        ghost = move_ghost(ghost[0], ghost[1], width, height)

        if pacman == ghost:
            break

        if not pellets:
            break

        time.sleep(FRAME_DELAY_SECONDS)

    screen.clear()
    if pacman == ghost:
        message = f"Game Over! Final score: {score}"
    else:
        message = f"You win! Final score: {score}"
    screen.addstr(0, 0, message)
    screen.addstr(2, 0, "Press any key to exit.")
    screen.refresh()
    screen.timeout(-1)
    screen.getch()


if __name__ == "__main__":
    curses.wrapper(run_game)
