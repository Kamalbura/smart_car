#!/bin/bash
# Simple launcher to run a Pygame app on the SPI TFT framebuffer (/dev/fb0)
# without affecting the main HDMI desktop.

export SDL_FBDEV=/dev/fb0
export SDL_VIDEODRIVER=fbcon
export SDL_NOMOUSE=1

# Activate project venv if needed
if [ -f "$HOME/project_root/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$HOME/project_root/.venv/bin/activate"
fi

# Replace this with your actual Pygame entrypoint
python -m src.ui.tft_app "${@}"
