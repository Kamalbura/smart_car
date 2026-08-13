import cv2


def main() -> None:
    # Open default camera (index 0). Change to 1 if you have multiple cameras.
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("ERROR: Cannot open camera (index 0).")
        return

    # Grab a single frame
    ret, frame = cap.read()
    if not ret or frame is None:
        print("ERROR: Failed to read frame from camera.")
        cap.release()
        return

    output_path = "img1.jpg"

    # Save the captured frame as img1.jpg in the current directory
    success = cv2.imwrite(output_path, frame)
    cap.release()

    if not success:
        print("ERROR: Failed to write image to", output_path)
        return

    print(f"Captured and saved image to {output_path}")


if __name__ == "__main__":
    main()
