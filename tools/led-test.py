import time
import board
import neopixel

# CONFIGURATION
# GPIO 12 is used as requested
pixel_pin = board.D12
num_pixels = 8
ORDER = neopixel.GRB  # Standard for most rings (Try RGB if colors are swapped)

# Initialize the strip
pixels = neopixel.NeoPixel(
    pixel_pin, 
    num_pixels, 
    brightness=0.2, # Low brightness to save eyes/power during test
    auto_write=False, 
    pixel_order=ORDER
)

def color_wipe(color, wait):
    """Wipe color across display a pixel at a time."""
    for i in range(num_pixels):
        pixels[i] = color
        pixels.show()
        time.sleep(wait)

print("Starting NeoPixel Test on GPIO 12...")

try:
    while True:
        print("Color Wipe: Red")
        color_wipe((255, 0, 0), 0.1)  # Red

        print("Color Wipe: Green")
        color_wipe((0, 255, 0), 0.1)  # Green

        print("Color Wipe: Blue")
        color_wipe((0, 0, 255), 0.1)  # Blue
        
        print("Clear")
        color_wipe((0, 0, 0), 0.05)   # Off
        time.sleep(1)

except KeyboardInterrupt:
    print("\nExiting...")
    pixels.fill((0, 0, 0))
    pixels.show()