from time import sleep

from picamera2 import Picamera2


def main() -> None:
    print("Starting Picamera2 test, capturing single image...")

    picam2 = Picamera2()

    # Configure for a still image
    config = picam2.create_still_configuration()
    picam2.configure(config)

    picam2.start()

    # Give the camera a moment to adjust exposure
    sleep(2)

    output_path = "img1.jpg"
    picam2.capture_file(output_path)

    picam2.stop()

    print(f"Captured and saved image to {output_path}")


if __name__ == "__main__":
    main()
