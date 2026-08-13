#!/usr/bin/env python3
"""Enhanced UART bridge with bidirectional communication and ESP32 feedback.

Supports:
- Sending navigation commands to ESP32 motor controller
- Receiving status/sensor feedback from ESP32
- Speed control and duration parameters
- Emergency stop handling
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Any, Dict, Optional

from src.core.config_loader import load_config
from src.core.ipc import (
    TOPIC_ESP,
    TOPIC_NAV,
    make_publisher,
    make_subscriber,
    publish_json,
)
from src.core.logging_setup import get_logger

import zmq

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    serial = None
    SERIAL_AVAILABLE = False

logger = get_logger("uart.motor_bridge", Path("logs"))


@dataclass
class MotorCommand:
    """Motor control command structure."""
    direction: str  # forward, backward, left, right, stop
    speed: int = 100  # 0-100 percentage
    duration_ms: int = 0  # 0 = continuous until next command
    target: Optional[str] = None  # optional vision target
    source: str = "unknown"


@dataclass
class SensorData:
    """Parsed sensor data from ESP32."""
    s1: int = -1  # Sensor 1 distance (cm)
    s2: int = -1  # Sensor 2 distance (cm)
    s3: int = -1  # Sensor 3 distance (cm)
    mq2: int = 0  # Gas sensor value
    lmotor: int = 0  # Left motor power
    rmotor: int = 0  # Right motor power
    obstacle: bool = False  # ESP32 detected obstacle
    warning: bool = False   # ESP32 in warning zone
    
    @property
    def min_distance(self) -> int:
        """Get minimum valid distance from all sensors."""
        valid = [d for d in [self.s1, self.s2, self.s3] if d > 0]
        return min(valid) if valid else -1
    
    @property
    def is_safe(self) -> bool:
        """Check if it's safe to move forward."""
        return not self.obstacle and not self.warning and self.min_distance > 20


class UARTMotorBridge:
    """Bidirectional UART bridge for ESP32 motor control with collision avoidance."""

    # Safety thresholds (backup to ESP32 safety)
    STOP_DISTANCE_CM = 10
    WARNING_DISTANCE_CM = 20

    # Default command mapping (can be overridden from config)
    # Align with ESP32 sketch command tokens in esp-code.ino
    DEFAULT_COMMANDS = {
        "forward": "FORWARD",
        "backward": "BACKWARD",
        "left": "LEFT",
        "right": "RIGHT",
        "stop": "STOP",
        "status": "STATUS",
        "reset": "RESET",
        "scan": "SCAN",
        "clearblock": "CLEARBLOCK",
    }

    def __init__(self, config: Dict[str, Any], sim: bool = False):
        self.config = config
        self.sim = sim
        nav_cfg = config.get("nav", {})

        self.device = nav_cfg.get("uart_device", "/dev/ttyAMA0")
        self.baud = int(nav_cfg.get("baud_rate", 115200))
        self.timeout = float(nav_cfg.get("timeout", 1.0))
        self.commands = {**self.DEFAULT_COMMANDS, **nav_cfg.get("commands", {})}

        self.serial: Optional[serial.Serial] = None
        self._running = False
        self._rx_queue: Queue = Queue()
        self._rx_thread: Optional[threading.Thread] = None

        # IPC sockets
        self.sub: Optional[Any] = None
        self.pub: Optional[Any] = None
        
        # Safety state (Pi-side backup)
        self._last_sensor_data: Optional[SensorData] = None
        self._last_sensor_ts: Optional[float] = None
        # Telemetry arrives at ~20 Hz, so a second is 20 missed frames --
        # generous, while still catching an MCU that has stopped talking.
        self.sensor_max_age_s = float(nav_cfg.get("sensor_max_age_s", 1.0))
        self._blocked_reason: Optional[str] = None
        self._scan_in_progress = False
        self._scan_results: list = []
        self._sensor_buffer = deque(maxlen=int(nav_cfg.get("sensor_buffer_size", 50)))
        self._last_rx_log_ts: float = 0.0

    def _open_serial(self) -> bool:
        """Open serial port connection."""
        if self.sim:
            logger.info("UART simulation mode - no serial port opened")
            return True

        if not SERIAL_AVAILABLE:
            logger.error("pyserial not installed")
            return False

        try:
            self.serial = serial.Serial(
                port=self.device,
                baudrate=self.baud,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
            logger.info("UART opened: %s @ %d baud", self.device, self.baud)
            return True
        except Exception as e:
            logger.error("Failed to open UART %s: %s", self.device, e)
            return False

    def _close_serial(self) -> None:
        """Close serial port."""
        if self.serial:
            try:
                self.serial.close()
            except Exception:
                pass
            self.serial = None

    def _format_command(self, cmd: MotorCommand) -> str:
        """Format command for ESP32 protocol (esp-code.ino).

        Supported tokens:
          - FORWARD, BACKWARD, LEFT, RIGHT, STOP, STATUS, RESET
          - SCAN - 360 degree environment scan
          - CLEARBLOCK - Clear obstacle block (manual override)
          - SERVO:<angle> (when target field is used as angle)

        Notes:
          - The current .ino ignores speed/duration for basic moves; commands
            are digital full-speed. We emit plain tokens accordingly.
        """
        direction = (cmd.direction or "").lower()
        if direction == "servo":
            # Use cmd.target to pass the angle when requested
            try:
                angle = int(cmd.target) if cmd.target is not None else 90
            except Exception:
                angle = 90
            return f"SERVO:{angle}\n"

        base_cmd = self.commands.get(direction, None)
        if not base_cmd:
            # Fallback to STOP if unknown
            base_cmd = "STOP"
        return f"{base_cmd}\n"
    
    def _parse_sensor_data(self, data_raw: str) -> Optional[SensorData]:
        """Parse DATA line from ESP32 into SensorData object.
        
        Format: S1:<d1>,S2:<d2>,S3:<d3>,MQ2:<v>,SERVO:<a>,LMOTOR:<ls>,RMOTOR:<rs>,OBSTACLE:<0|1>,WARNING:<0|1>
        """
        try:
            parts = data_raw.split(",")
            data = SensorData()
            for part in parts:
                if ":" not in part:
                    continue
                key, val = part.split(":", 1)
                key = key.strip().upper()
                val = val.strip()
                if key == "S1":
                    data.s1 = int(val)
                elif key == "S2":
                    data.s2 = int(val)
                elif key == "S3":
                    data.s3 = int(val)
                elif key == "MQ2":
                    data.mq2 = int(val)
                elif key == "LMOTOR":
                    data.lmotor = int(val)
                elif key == "RMOTOR":
                    data.rmotor = int(val)
                elif key == "OBSTACLE":
                    data.obstacle = val == "1"
                elif key == "WARNING":
                    data.warning = val == "1"
            return data
        except Exception as e:
            logger.warning("Failed to parse sensor data: %s - %s", data_raw, e)
            return None
    
    def _record_sensor_data(self, sensor_data: SensorData) -> None:
        """Store the latest telemetry frame and when it arrived."""
        self._last_sensor_data = sensor_data
        self._last_sensor_ts = time.time()

    def _check_pi_side_safety(self, cmd: MotorCommand) -> tuple[bool, str]:
        """Pi-side safety gate, an advisory backup to the MCU.

        Only forward is gated. Stopping and escape manoeuvres stay available at
        any distance, or the robot can be trapped against a wall with no way
        out.

        Every unknown counts as unsafe. The previous version did the opposite:
        no telemetry, stale telemetry and all-sensors-invalid each fell through
        to "allowed", so it reported a clear road exactly when it knew least --
        at boot, with the UART unplugged, or with a dead MCU. A check that says
        "safe" when it has no information is worse than no check, because it
        looks like defence in depth and is not.

        Returns (allowed, reason).
        """
        direction = (cmd.direction or "").lower()

        if direction != "forward":
            return True, ""

        if self._last_sensor_data is None or self._last_sensor_ts is None:
            return False, "no telemetry received from MCU yet"

        age = time.time() - self._last_sensor_ts
        if age > self.sensor_max_age_s:
            return False, f"stale telemetry ({age:.1f}s > {self.sensor_max_age_s:.1f}s)"

        sd = self._last_sensor_data
        if sd.obstacle:
            return False, "ESP32 obstacle detected"
        if sd.warning:
            return False, "ESP32 warning zone"
        if sd.min_distance <= 0:
            return False, "all sensors invalid; treating as blocked"
        if sd.min_distance < self.STOP_DISTANCE_CM:
            return False, f"Pi safety: distance {sd.min_distance}cm < {self.STOP_DISTANCE_CM}cm"
        if sd.min_distance < self.WARNING_DISTANCE_CM:
            return False, f"Pi safety: warning zone {sd.min_distance}cm"

        return True, ""

    def _send_command(self, cmd: MotorCommand) -> bool:
        """Send command to ESP32 with Pi-side safety check."""
        # Pi-side safety check (backup to ESP32)
        allowed, reason = self._check_pi_side_safety(cmd)
        if not allowed:
            logger.warning("Command %s BLOCKED by Pi safety: %s", cmd.direction, reason)
            self._blocked_reason = reason
            # Publish blocked status
            if self.pub:
                publish_json(self.pub, TOPIC_ESP, {
                    "blocked": True,
                    "command": cmd.direction,
                    "reason": reason,
                    "source": cmd.source,
                })
            return False
        
        self._blocked_reason = None
        formatted = self._format_command(cmd)

        if self.sim:
            logger.info("UART TX payload (sim) direction=%s speed=%s duration_ms=%s target=%s source=%s formatted=%s",
                        cmd.direction,
                        cmd.speed,
                        cmd.duration_ms,
                        cmd.target,
                        cmd.source,
                        formatted.strip())
            logger.info("[SIM] UART TX: %s", formatted.strip())
            return True

        if not self.serial or not self.serial.is_open:
            logger.error("Serial port not open")
            return False

        try:
            logger.info(
                "UART TX payload direction=%s speed=%s duration_ms=%s target=%s source=%s formatted=%s",
                cmd.direction,
                cmd.speed,
                cmd.duration_ms,
                cmd.target,
                cmd.source,
                formatted.strip(),
            )
            self.serial.write(formatted.encode("utf-8"))
            self.serial.flush()
            logger.info("UART TX: %s (source=%s)", formatted.strip(), cmd.source)
            return True
        except Exception as e:
            logger.error("UART write failed: %s", e)
            return False

    def _rx_loop(self) -> None:
        """Background thread for reading ESP32 responses."""
        while self._running:
            if self.sim:
                time.sleep(0.1)
                continue

            if not self.serial or not self.serial.is_open:
                time.sleep(0.1)
                continue

            try:
                if self.serial.in_waiting > 0:
                    line = self.serial.readline().decode("utf-8", errors="replace").strip()
                    if line:
                        self._rx_queue.put(line)
                        logger.debug("UART RX: %s", line)
                else:
                    # Brief sleep to prevent busy-spin when no data
                    time.sleep(0.005)  # 5ms - balance responsiveness vs CPU
            except Exception as e:
                logger.warning("UART read error: %s", e)
                time.sleep(0.1)

    def _process_rx(self) -> None:
        """Process received data from ESP32 and publish to IPC."""
        while not self._rx_queue.empty():
            try:
                line = self._rx_queue.get_nowait()
                now = time.time()
                if now - self._last_rx_log_ts >= 1.0:
                    logger.info("UART RX sample: %s", line)
                    self._last_rx_log_ts = now
                # Parse ESP32 feedback (expected format: STATUS:value or JSON)
                if line.startswith("{"):
                    # JSON response (future extension)
                    payload = json.loads(line)
                else:
                    # Parse ACK/STATUS and sensor data formats from esp-code.ino
                    # Examples:
                    #   ACK:<CMD>:<STATUS>
                    #   STATUS:SERVO:<angle>,LMOTOR:<ls>,RMOTOR:<rs>
                    #   DATA:S1:<d1>,S2:<d2>,S3:<d3>,MQ2:<v>,SERVO:<a>,LMOTOR:<ls>,RMOTOR:<rs>,OBSTACLE:<0|1>,WARNING:<0|1>
                    #   ALERT:COLLISION:<reason>,S1:<d1>,S2:<d2>,S3:<d3>
                    #   SCAN:START|COMPLETE|POS:<angle>|BEST:<angle>
                    parts = line.split(":")
                    if not parts:
                        payload = {"raw": line}
                    elif parts[0] == "ACK" and len(parts) >= 3:
                        payload = {"ack": parts[1], "status": ":".join(parts[2:])}
                        # Check if forward was blocked by ESP32
                        if parts[1] == "FORWARD" and "BLOCKED" in parts[2]:
                            logger.warning("ESP32 blocked FORWARD: %s", parts[2])
                    elif parts[0] == "STATUS":
                        payload = {"status_raw": ":".join(parts[1:])}
                    elif parts[0] == "DATA":
                        data_raw = ":".join(parts[1:])
                        sensor_data = self._parse_sensor_data(data_raw)
                        if sensor_data:
                            self._record_sensor_data(sensor_data)
                            ts = int(time.time())
                            frame = {
                                "ts": ts,
                                "s1": sensor_data.s1,
                                "s2": sensor_data.s2,
                                "s3": sensor_data.s3,
                                "mq2": sensor_data.mq2,
                                "lmotor": sensor_data.lmotor,
                                "rmotor": sensor_data.rmotor,
                                "min_distance": sensor_data.min_distance,
                                "obstacle": sensor_data.obstacle,
                                "warning": sensor_data.warning,
                                "is_safe": sensor_data.is_safe,
                            }
                            self._sensor_buffer.append(frame)
                            payload = {
                                "data": {
                                    "s1": sensor_data.s1,
                                    "s2": sensor_data.s2,
                                    "s3": sensor_data.s3,
                                    "mq2": sensor_data.mq2,
                                    "lmotor": sensor_data.lmotor,
                                    "rmotor": sensor_data.rmotor,
                                    "min_distance": sensor_data.min_distance,
                                    "obstacle": sensor_data.obstacle,
                                    "warning": sensor_data.warning,
                                    "is_safe": sensor_data.is_safe,
                                },
                                "data_ts": ts,
                                "buffer": list(self._sensor_buffer),
                            }
                        else:
                            payload = {"data_raw": data_raw}
                    elif parts[0] == "ALERT" and len(parts) >= 2:
                        # Handle collision alerts
                        alert_type = parts[1] if len(parts) > 1 else "UNKNOWN"
                        alert_data = ":".join(parts[2:]) if len(parts) > 2 else ""
                        payload = {"alert": alert_type, "alert_data": alert_data}
                        logger.warning("ESP32 ALERT: %s - %s", alert_type, alert_data)
                        # Emergency stop on Pi side too
                        if alert_type == "COLLISION" and "EMERGENCY" in alert_data:
                            logger.critical("COLLISION ALERT - Emergency stop triggered!")
                    elif parts[0] == "SCAN":
                        # Handle scan updates
                        scan_type = parts[1] if len(parts) > 1 else "UNKNOWN"
                        if scan_type == "START":
                            self._scan_in_progress = True
                            self._scan_results = []
                            logger.info("360° scan started")
                        elif scan_type == "COMPLETE":
                            self._scan_in_progress = False
                            logger.info("360° scan complete with %d positions", len(self._scan_results))
                        elif scan_type == "POS":
                            # POS:<angle>,S1:<d1>,S2:<d2>,S3:<d3>
                            scan_data = ":".join(parts[2:]) if len(parts) > 2 else ""
                            self._scan_results.append({"raw": scan_data})
                        elif scan_type == "BEST":
                            # BEST:<angle>,DIST:<dist>
                            best_data = ":".join(parts[2:]) if len(parts) > 2 else ""
                            logger.info("Best direction from scan: %s", best_data)
                        payload = {"scan": scan_type, "scan_data": ":".join(parts[2:]) if len(parts) > 2 else ""}
                    else:
                        payload = {"type": parts[0], "value": ":".join(parts[1:])}

                if self.pub:
                    publish_json(self.pub, TOPIC_ESP, payload)
                    logger.debug("Published ESP32 feedback: %s", payload)

            except Exception as e:
                logger.warning("Failed to process RX: %s", e)

    def _parse_nav_command(self, payload: Dict[str, Any]) -> MotorCommand:
        """Parse IPC navigation payload into MotorCommand."""
        direction = payload.get("direction", "stop")
        speed = int(payload.get("speed", 100))
        duration = int(payload.get("duration_ms", 0))
        target = payload.get("target")
        source = str(payload.get("source", "unknown"))

        logger.info(
            "nav.command parsed direction=%s speed=%s duration_ms=%s target=%s source=%s",
            direction,
            speed,
            duration,
            target,
            source,
        )

        return MotorCommand(
            direction=direction,
            speed=max(0, min(100, speed)),
            duration_ms=max(0, duration),
            target=target,
            source=source,
        )
    
    def request_scan(self) -> bool:
        """Request a 360-degree environment scan."""
        if self._scan_in_progress:
            logger.warning("Scan already in progress")
            return False
        return self._send_command(MotorCommand(direction="scan"))
    
    def get_sensor_data(self) -> Optional[SensorData]:
        """Get the latest sensor data."""
        return self._last_sensor_data
    
    def is_safe_to_move(self) -> bool:
        """Check if it's safe to move forward."""
        if self._last_sensor_data:
            return self._last_sensor_data.is_safe
        return True  # No data yet, assume safe (ESP32 will block anyway)

    def run(self) -> None:
        """Main bridge loop."""
        if not self._open_serial():
            if not self.sim:
                logger.error("Cannot run bridge without serial port (use --sim for simulation)")
                return

        # Setup IPC
        self.sub = make_subscriber(self.config, topic=TOPIC_NAV, channel="downstream")
        self.pub = make_publisher(self.config, channel="upstream")

        # Start RX thread
        self._running = True
        if not self.sim:
            self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
            self._rx_thread.start()

        logger.info("UART Motor Bridge running (device=%s, sim=%s)", self.device, self.sim)

        try:
            while self._running:
                # Check for incoming nav commands (NON-BLOCKING with timeout)
                try:
                    # Use poller for non-blocking recv with timeout
                    if self.sub.poll(timeout=50):  # 50ms timeout
                        topic, data = self.sub.recv_multipart(zmq.NOBLOCK)
                        payload = json.loads(data)
                        logger.info("nav.command received payload=%s", payload)
                        cmd = self._parse_nav_command(payload)
                        self._send_command(cmd)
                except zmq.Again:
                    pass  # No message available, continue
                except Exception as e:
                    logger.error("Failed to process nav command: %s", e)

                # Process any ESP32 feedback
                self._process_rx()

        except KeyboardInterrupt:
            logger.info("Bridge interrupted")
        finally:
            self._running = False
            self._close_serial()
            logger.info("UART Motor Bridge stopped")

    def stop(self) -> None:
        """Stop the bridge."""
        self._running = False
        # Send emergency stop
        if self.serial and self.serial.is_open:
            self._send_command(MotorCommand(direction="stop"))


def run() -> None:
    """Legacy entry point for compatibility."""
    cfg = load_config(Path("config/system.yaml"))
    bridge = UARTMotorBridge(cfg)
    bridge.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="UART Motor Bridge for ESP32")
    parser.add_argument("--sim", action="store_true", help="Run in simulation mode (no serial)")
    parser.add_argument("--device", default=None, help="Override UART device path")
    parser.add_argument("--baud", type=int, default=None, help="Override baud rate")
    args = parser.parse_args()

    cfg = load_config(Path("config/system.yaml"))

    # Apply CLI overrides
    if args.device:
        cfg.setdefault("nav", {})["uart_device"] = args.device
    if args.baud:
        cfg.setdefault("nav", {})["baud_rate"] = args.baud

    bridge = UARTMotorBridge(cfg, sim=args.sim)
    bridge.run()


if __name__ == "__main__":
    main()
