import math
import random
from collections import deque

import pygame


TILE_SIZE = 28
HUD_HEIGHT = 72
FPS = 60
PACMAN_SPEED = 7.0
GHOST_SPEED = 6.0
POWER_TIME_SECONDS = 6.0

LEVEL_MAP = [
    "###################",
    "#........#........#",
    "#o##.###.#.###.##o#",
    "#.................#",
    "#.##.#.#####.#.##.#",
    "#....#...#...#....#",
    "####.### # ###.####",
    "   #.#   G   #.#   ",
    "####.# ## ## #.####",
    "#.........P.......#",
    "#.##.#.#####.#.##.#",
    "#o..#...#.#...#..o#",
    "###.###.#.#.###.###",
    "#.......#.........#",
    "###################",
]

WALL = "#"
PELLET = "."
POWER = "o"
EMPTY = " "
PACMAN_START = "P"
GHOST_START = "G"


pygame.init()
pygame.display.set_caption("Pac-Man")
FONT = pygame.font.SysFont("consolas", 24, bold=True)
SMALL_FONT = pygame.font.SysFont("consolas", 18)


class Game:
    def __init__(self) -> None:
        self.rows = len(LEVEL_MAP)
        self.cols = len(LEVEL_MAP[0])
        self.base_width = self.cols * TILE_SIZE
        self.base_height = self.rows * TILE_SIZE + HUD_HEIGHT
        self.window_width = self.base_width
        self.window_height = self.base_height
        self.screen = pygame.display.set_mode(
            (self.window_width, self.window_height),
            pygame.RESIZABLE,
        )
        self.scene = pygame.Surface((self.base_width, self.base_height))
        self.clock = pygame.time.Clock()
        self.reset_game()

    def reset_game(self) -> None:
        self.grid: list[list[str]] = []
        self.walkable_tiles: set[tuple[int, int]] = set()
        self.pacman_spawn = (1, 1)
        self.ghost_spawns: list[tuple[int, int]] = []

        for row_index, row in enumerate(LEVEL_MAP):
            grid_row: list[str] = []
            for col_index, cell in enumerate(row):
                if cell == PACMAN_START:
                    self.pacman_spawn = (col_index, row_index)
                    grid_row.append(PELLET)
                    self.walkable_tiles.add((col_index, row_index))
                elif cell == GHOST_START:
                    self.ghost_spawns.append((col_index, row_index))
                    grid_row.append(EMPTY)
                    self.walkable_tiles.add((col_index, row_index))
                else:
                    grid_row.append(cell)
                    if cell != WALL:
                        self.walkable_tiles.add((col_index, row_index))
            self.grid.append(grid_row)

        if not self.ghost_spawns:
            self.ghost_spawns = [(self.cols // 2, self.rows // 2)]

        self.score = 0
        self.lives = 3
        self.message = ""
        self.message_timer = 0.0
        self.game_over = False
        self.win = False
        self.reset_positions()

    def reset_positions(self) -> None:
        self.pacman = {
            "pos": self.tile_to_pixel(self.pacman_spawn),
            "dir": pygame.Vector2(0, 0),
            "next_dir": pygame.Vector2(0, 0),
        }
        self.ghosts = []
        colors = [(255, 64, 64), (255, 184, 255), (64, 255, 255), (255, 184, 82)]
        for index, spawn in enumerate(self.ghost_spawns):
            self.ghosts.append(
                {
                    "pos": self.tile_to_pixel(spawn),
                    "dir": pygame.Vector2(random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])),
                    "color": colors[index % len(colors)],
                }
            )
        self.power_timer = 0.0

    def tile_to_pixel(self, tile: tuple[int, int]) -> pygame.Vector2:
        x, y = tile
        return pygame.Vector2(
            x * TILE_SIZE + TILE_SIZE / 2,
            y * TILE_SIZE + TILE_SIZE / 2 + HUD_HEIGHT,
        )

    def pixel_to_tile(self, pos: pygame.Vector2) -> tuple[int, int]:
        col = int(pos.x // TILE_SIZE)
        row = int((pos.y - HUD_HEIGHT) // TILE_SIZE)
        return col, row

    def tile_center(self, tile: tuple[int, int]) -> pygame.Vector2:
        return self.tile_to_pixel(tile)

    def is_walkable(self, tile: tuple[int, int]) -> bool:
        return tile in self.walkable_tiles

    def centered_on_tile(self, pos: pygame.Vector2) -> bool:
        tile = self.pixel_to_tile(pos)
        center = self.tile_center(tile)
        return pos.distance_to(center) < 2.0

    def available_directions(self, tile: tuple[int, int]) -> list[pygame.Vector2]:
        directions: list[pygame.Vector2] = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (tile[0] + dx, tile[1] + dy)
            if self.is_walkable(neighbor):
                directions.append(pygame.Vector2(dx, dy))
        return directions

    def set_message(self, text: str, seconds: float) -> None:
        self.message = text
        self.message_timer = seconds

    def handle_input(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.VIDEORESIZE:
                self.resize_window(event.w, event.h)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if self.game_over and event.key == pygame.K_r:
                    self.reset_game()
                elif event.key == pygame.K_UP:
                    self.pacman["next_dir"] = pygame.Vector2(0, -1)
                elif event.key == pygame.K_DOWN:
                    self.pacman["next_dir"] = pygame.Vector2(0, 1)
                elif event.key == pygame.K_LEFT:
                    self.pacman["next_dir"] = pygame.Vector2(-1, 0)
                elif event.key == pygame.K_RIGHT:
                    self.pacman["next_dir"] = pygame.Vector2(1, 0)
        return True

    def resize_window(self, width: int, height: int) -> None:
        self.window_width = max(width, 480)
        self.window_height = max(height, 420)
        self.screen = pygame.display.set_mode(
            (self.window_width, self.window_height),
            pygame.RESIZABLE,
        )

    def update(self, dt: float) -> None:
        if self.game_over:
            return

        if self.message_timer > 0:
            self.message_timer = max(0.0, self.message_timer - dt)
            if self.message_timer == 0:
                self.message = ""

        if self.power_timer > 0:
            self.power_timer = max(0.0, self.power_timer - dt)

        self.move_pacman(dt)
        self.consume_tile()
        self.move_ghosts(dt)
        self.check_collisions()
        self.check_win()

    def move_pacman(self, dt: float) -> None:
        pos = self.pacman["pos"]
        current_dir = self.pacman["dir"]
        next_dir = self.pacman["next_dir"]
        tile = self.pixel_to_tile(pos)

        if self.centered_on_tile(pos):
            pos.update(self.tile_center(tile))

            if next_dir.length_squared() > 0:
                next_tile = (tile[0] + int(next_dir.x), tile[1] + int(next_dir.y))
                if self.is_walkable(next_tile):
                    current_dir = next_dir

            if current_dir.length_squared() > 0:
                forward_tile = (tile[0] + int(current_dir.x), tile[1] + int(current_dir.y))
                if not self.is_walkable(forward_tile):
                    current_dir = pygame.Vector2(0, 0)

        self.pacman["dir"] = current_dir
        self.pacman["pos"] += current_dir * PACMAN_SPEED * TILE_SIZE * dt

    def consume_tile(self) -> None:
        tile = self.pixel_to_tile(self.pacman["pos"])
        center = self.tile_center(tile)
        if self.pacman["pos"].distance_to(center) > 10:
            return

        current = self.grid[tile[1]][tile[0]]
        if current == PELLET:
            self.grid[tile[1]][tile[0]] = EMPTY
            self.score += 10
        elif current == POWER:
            self.grid[tile[1]][tile[0]] = EMPTY
            self.score += 50
            self.power_timer = POWER_TIME_SECONDS
            self.set_message("Power pellet!", 1.5)

    def shortest_step_toward(
        self,
        start: tuple[int, int],
        target: tuple[int, int],
    ) -> pygame.Vector2:
        queue: deque[tuple[int, int]] = deque([start])
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

        while queue:
            current = queue.popleft()
            if current == target:
                break

            for direction in self.available_directions(current):
                neighbor = (current[0] + int(direction.x), current[1] + int(direction.y))
                if neighbor not in came_from:
                    came_from[neighbor] = current
                    queue.append(neighbor)

        if target not in came_from:
            choices = self.available_directions(start)
            return random.choice(choices) if choices else pygame.Vector2(0, 0)

        step = target
        while came_from[step] != start and came_from[step] is not None:
            step = came_from[step]

        return pygame.Vector2(step[0] - start[0], step[1] - start[1])

    def move_ghosts(self, dt: float) -> None:
        pacman_tile = self.pixel_to_tile(self.pacman["pos"])

        for ghost in self.ghosts:
            pos = ghost["pos"]
            tile = self.pixel_to_tile(pos)
            direction = ghost["dir"]

            if self.centered_on_tile(pos):
                pos.update(self.tile_center(tile))
                if self.power_timer > 0:
                    options = self.available_directions(tile)
                    if options:
                        direction = max(
                            options,
                            key=lambda option: abs(tile[0] + int(option.x) - pacman_tile[0])
                            + abs(tile[1] + int(option.y) - pacman_tile[1]),
                        )
                else:
                    direction = self.shortest_step_toward(tile, pacman_tile)

            speed = GHOST_SPEED * 0.6 if self.power_timer > 0 else GHOST_SPEED
            ghost["dir"] = direction
            ghost["pos"] += direction * speed * TILE_SIZE * dt

    def lose_life(self) -> None:
        self.lives -= 1
        if self.lives <= 0:
            self.game_over = True
            self.win = False
            self.set_message("Game Over - Press R to restart", 999)
        else:
            self.set_message("Caught!", 1.5)
            self.reset_positions()

    def check_collisions(self) -> None:
        for ghost in self.ghosts:
            if ghost["pos"].distance_to(self.pacman["pos"]) < TILE_SIZE * 0.55:
                if self.power_timer > 0:
                    self.score += 200
                    ghost["pos"] = self.tile_to_pixel(random.choice(self.ghost_spawns))
                    ghost["dir"] = pygame.Vector2(0, 0)
                    self.set_message("Ghost eaten!", 1.0)
                else:
                    self.lose_life()
                break

    def check_win(self) -> None:
        remaining = any(cell in (PELLET, POWER) for row in self.grid for cell in row)
        if not remaining:
            self.game_over = True
            self.win = True
            self.set_message("You cleared the board - Press R to restart", 999)

    def draw(self) -> None:
        self.scene.fill((8, 8, 18))
        self.draw_hud()
        self.draw_maze()
        self.draw_entities()
        if self.message:
            self.draw_message(self.message)

        scaled_scene = pygame.transform.smoothscale(
            self.scene,
            self.scaled_scene_size(),
        )
        self.screen.fill((8, 8, 18))
        self.screen.blit(scaled_scene, self.scene_offset(scaled_scene))
        pygame.display.flip()

    def scaled_scene_size(self) -> tuple[int, int]:
        scale = min(
            self.window_width / self.base_width,
            self.window_height / self.base_height,
        )
        scale = max(scale, 0.5)
        return (
            max(1, int(self.base_width * scale)),
            max(1, int(self.base_height * scale)),
        )

    def scene_offset(self, scaled_scene: pygame.Surface) -> tuple[int, int]:
        return (
            (self.window_width - scaled_scene.get_width()) // 2,
            (self.window_height - scaled_scene.get_height()) // 2,
        )

    def draw_hud(self) -> None:
        title = FONT.render("PAC-MAN", True, (255, 219, 77))
        score = SMALL_FONT.render(f"Score: {self.score}", True, (240, 240, 240))
        lives = SMALL_FONT.render(f"Lives: {self.lives}", True, (240, 240, 240))
        controls = SMALL_FONT.render("Arrows to move   Esc to quit", True, (170, 170, 190))

        self.scene.blit(title, (18, 12))
        self.scene.blit(score, (18, 42))
        self.scene.blit(lives, (170, 42))
        self.scene.blit(controls, (300, 42))

        if self.power_timer > 0:
            power = SMALL_FONT.render("POWER", True, (120, 212, 255))
            self.scene.blit(power, (self.base_width - 95, 42))

    def draw_maze(self) -> None:
        wall_color = (31, 77, 255)
        wall_fill = (15, 26, 76)

        for row_index, row in enumerate(self.grid):
            for col_index, cell in enumerate(row):
                x = col_index * TILE_SIZE
                y = row_index * TILE_SIZE + HUD_HEIGHT
                rect = pygame.Rect(x, y, TILE_SIZE, TILE_SIZE)

                if LEVEL_MAP[row_index][col_index] == WALL:
                    pygame.draw.rect(self.scene, wall_fill, rect, border_radius=8)
                    pygame.draw.rect(self.scene, wall_color, rect, width=2, border_radius=8)
                elif cell == PELLET:
                    pygame.draw.circle(self.scene, (255, 235, 165), rect.center, 4)
                elif cell == POWER:
                    radius = 8 + int(2 * math.sin(pygame.time.get_ticks() * 0.01))
                    pygame.draw.circle(self.scene, (255, 245, 190), rect.center, radius)

    def draw_entities(self) -> None:
        pacman_pos = self.pacman["pos"]
        pacman_dir = self.pacman["dir"]
        angle = 0.0
        if pacman_dir.length_squared() > 0:
            angle = math.atan2(pacman_dir.y, pacman_dir.x)

        mouth = 0.45 + 0.2 * math.sin(pygame.time.get_ticks() * 0.02)
        start_angle = angle + mouth
        end_angle = angle + (math.tau - mouth)
        center = (int(pacman_pos.x), int(pacman_pos.y))
        radius = TILE_SIZE // 2 - 2
        pygame.draw.circle(self.scene, (255, 219, 77), center, radius)
        pygame.draw.polygon(
            self.scene,
            (8, 8, 18),
            [
                center,
                (
                    int(center[0] + math.cos(start_angle) * radius),
                    int(center[1] + math.sin(start_angle) * radius),
                ),
                (
                    int(center[0] + math.cos(end_angle) * radius),
                    int(center[1] + math.sin(end_angle) * radius),
                ),
            ],
        )

        frightened = self.power_timer > 0
        for ghost in self.ghosts:
            color = (80, 120, 255) if frightened else ghost["color"]
            gx, gy = int(ghost["pos"].x), int(ghost["pos"].y)
            body = pygame.Rect(gx - 12, gy - 12, 24, 24)
            pygame.draw.circle(self.scene, color, (gx, gy - 4), 12)
            pygame.draw.rect(self.scene, color, body)
            for offset in (-8, 0, 8):
                pygame.draw.circle(self.scene, color, (gx + offset, gy + 12), 4)

            eye_color = (255, 255, 255)
            pupil_color = (18, 18, 36)
            pygame.draw.circle(self.scene, eye_color, (gx - 5, gy - 4), 4)
            pygame.draw.circle(self.scene, eye_color, (gx + 5, gy - 4), 4)
            pygame.draw.circle(self.scene, pupil_color, (gx - 4, gy - 3), 2)
            pygame.draw.circle(self.scene, pupil_color, (gx + 6, gy - 3), 2)

    def draw_message(self, text: str) -> None:
        surface = FONT.render(text, True, (255, 255, 255))
        background = pygame.Rect(0, 0, surface.get_width() + 28, surface.get_height() + 18)
        background.center = (self.base_width // 2, HUD_HEIGHT // 2)
        pygame.draw.rect(self.scene, (20, 20, 36), background, border_radius=12)
        pygame.draw.rect(self.scene, (70, 70, 110), background, width=2, border_radius=12)
        self.scene.blit(surface, (background.x + 14, background.y + 9))

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            running = self.handle_input()
            self.update(dt)
            self.draw()


def main() -> None:
    game = Game()
    try:
        game.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
