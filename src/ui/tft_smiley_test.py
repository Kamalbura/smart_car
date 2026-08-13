import os
import time

import pygame

FBDEV = "/dev/fb0"
WIDTH, HEIGHT = 480, 320


def init_pygame_fb() -> pygame.Surface:
    os.environ.setdefault("SDL_FBDEV", FBDEV)
    os.environ.setdefault("SDL_VIDEODRIVER", "fbcon")

    pygame.display.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
    return screen


def draw_smiley(surface: pygame.Surface) -> None:
    surface.fill((0, 0, 0))

    cx, cy = WIDTH // 2, HEIGHT // 2
    radius = min(WIDTH, HEIGHT) // 3

    YELLOW = (255, 255, 0)
    BLACK = (0, 0, 0)

    pygame.draw.circle(surface, YELLOW, (cx, cy), radius)
    pygame.draw.circle(surface, BLACK, (cx, cy), radius, 4)

    eye_dx = radius // 3
    eye_dy = radius // 3
    eye_r = radius // 8
    pygame.draw.circle(surface, BLACK, (cx - eye_dx, cy - eye_dy), eye_r)
    pygame.draw.circle(surface, BLACK, (cx + eye_dx, cy - eye_dy), eye_r)

    rect_width = radius * 2 // 1
    rect_height = radius
    smile_rect = pygame.Rect(
        cx - rect_width // 2,
        cy - rect_height // 4,
        rect_width,
        rect_height,
    )
    pygame.draw.arc(surface, BLACK, smile_rect, 3.14 / 6, 5 * 3.14 / 6, 4)


def main() -> None:
    screen = init_pygame_fb()
    draw_smiley(screen)
    pygame.display.flip()

    end = time.time() + 5
    while time.time() < end:
        pygame.event.pump()
        time.sleep(0.05)

    pygame.display.quit()
    pygame.quit()


if __name__ == "__main__":
    main()
