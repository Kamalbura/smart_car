import argparse
import time
from pathlib import Path

import serial  # type: ignore
import yaml


def load_uart_config() -> tuple[str, int, float]:
    """Load UART settings from config/system.yaml (nav section)."""
    cfg_path = Path(__file__).parent / "config" / "system.yaml"
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    nav = data.get("nav", {})
    device = nav.get("uart_device", "/dev/ttyAMA0")
    baud = int(nav.get("baud_rate", 115200))
    timeout = float(nav.get("timeout", 1.0))
    return device, baud, timeout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read and print data from the ESP32 over UART."
    )
    parser.add_argument(
        "--device",
        help="Override UART device (defaults to nav.uart_device in config/system.yaml)",
    )
    parser.add_argument(
        "--baud",
        type=int,
        help="Override baud rate (defaults to nav.baud_rate)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        help="Override read timeout seconds (defaults to nav.timeout)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=15.0,
        help="How many seconds to listen (default: 15)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg_device, cfg_baud, cfg_timeout = load_uart_config()

    device = args.device or cfg_device
    baud = args.baud or cfg_baud
    timeout = args.timeout or cfg_timeout

    print(f"Opening UART {device} @ {baud} baud (timeout={timeout}s)...")

    try:
        ser = serial.Serial(port=device, baudrate=baud, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Failed to open UART {device}: {exc}")
        return

    read_seconds = max(args.duration, 0.5)
    end_time = time.time() + read_seconds
    print(f"Listening for ESP32 data for ~{read_seconds:.0f} seconds...")
    print("Press Ctrl+C to stop earlier.\n")

    try:
        while time.time() < end_time:
            line = ser.readline()
            if not line:
                continue
            try:
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            except Exception:  # noqa: BLE001
                text = repr(line)
            print(f"[RX] {text}")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        ser.close()
        print("UART closed.")


if __name__ == "__main__":
    main()
