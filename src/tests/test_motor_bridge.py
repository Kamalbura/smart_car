"""Tests for the UART motor bridge -- the live service that turns nav.command
messages into bytes on the wire.

Focus is the Pi-side safety gate. It is advisory (the MCU is the authority) but
it must not be *wrong*, because a check that says "safe" when it has no idea is
worse than no check: it looks like defence in depth and is not.

Runs with sim=True, so no serial port and no hardware.
"""
from __future__ import annotations

import time

import pytest

from src.uart.motor_bridge import MotorCommand, SensorData, UARTMotorBridge

CONFIG = {
    "nav": {
        "uart_device": "/dev/null",
        "baud_rate": 115200,
        "timeout": 1.0,
        "commands": {
            "forward": "FORWARD",
            "backward": "BACKWARD",
            "left": "LEFT",
            "right": "RIGHT",
            "stop": "STOP",
            "scan": "SCAN",
        },
    },
    "logs": {"directory": "logs"},
}


@pytest.fixture
def bridge():
    return UARTMotorBridge(CONFIG, sim=True)


def _clear() -> SensorData:
    return SensorData(s1=200, s2=200, s3=200, obstacle=False, warning=False)


# ---------------------------------------------------------------------------
# Wire formatting
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "direction,expected",
    [
        ("forward", "FORWARD\n"),
        ("backward", "BACKWARD\n"),
        ("left", "LEFT\n"),
        ("right", "RIGHT\n"),
        ("stop", "STOP\n"),
        ("scan", "SCAN\n"),
        ("FORWARD", "FORWARD\n"),
    ],
)
def test_known_directions_map_to_tokens(bridge, direction, expected):
    assert bridge._format_command(MotorCommand(direction=direction)) == expected


@pytest.mark.parametrize("direction", ["sideways", "", "banana", "forwardx"])
def test_unknown_direction_becomes_stop(bridge, direction):
    """Unknown must fail safe, not fail silent."""
    assert bridge._format_command(MotorCommand(direction=direction)) == "STOP\n"


def test_servo_angle_is_encoded(bridge):
    assert bridge._format_command(MotorCommand(direction="servo", target="45")) == "SERVO:45\n"


def test_servo_defaults_when_angle_is_unparseable(bridge):
    assert bridge._format_command(MotorCommand(direction="servo", target="abc")) == "SERVO:90\n"


# ---------------------------------------------------------------------------
# Telemetry parsing
# ---------------------------------------------------------------------------

def test_parses_a_full_data_line(bridge):
    line = "S1:45,S2:120,S3:200,MQ2:310,SERVO:90,LMOTOR:0,RMOTOR:0,OBSTACLE:0,WARNING:1"
    sd = bridge._parse_sensor_data(line)
    assert (sd.s1, sd.s2, sd.s3) == (45, 120, 200)
    assert sd.mq2 == 310
    assert sd.obstacle is False
    assert sd.warning is True
    assert sd.min_distance == 45


def test_partially_malformed_line_is_rejected_wholesale(bridge):
    """Any unparseable field discards the entire frame.

    Accepting the readable half would be worse: you could take the distances
    while silently missing the OBSTACLE flag that came later in the same line.
    The legacy ASCII protocol carries no checksum, so a flipped byte is
    indistinguishable from real data -- dropping the frame and letting
    telemetry go stale is correct, because the staleness gate below then blocks
    forward motion rather than acting on half a truth.
    """
    assert bridge._parse_sensor_data("S1:45,GARBAGE,S2:") is None
    assert bridge._parse_sensor_data("S1:notanumber") is None


def test_unknown_fields_are_ignored_not_fatal(bridge):
    """Forward compatibility: a newer MCU may add fields we do not know."""
    sd = bridge._parse_sensor_data("S1:45,S2:120,S3:200,NEWFIELD:7,OBSTACLE:0")
    assert sd is not None
    assert sd.min_distance == 45


def test_min_distance_ignores_invalid_readings():
    # -1 is the ESP32's "no echo" marker and must not win the minimum.
    assert SensorData(s1=-1, s2=150, s3=-1).min_distance == 150


def test_min_distance_is_negative_when_every_sensor_is_invalid():
    assert SensorData(s1=-1, s2=-1, s3=-1).min_distance == -1


# ---------------------------------------------------------------------------
# The Pi-side safety gate
# ---------------------------------------------------------------------------

def test_forward_allowed_on_a_clear_road(bridge):
    bridge._record_sensor_data(_clear())
    allowed, _ = bridge._check_pi_side_safety(MotorCommand(direction="forward"))
    assert allowed is True


def test_forward_blocked_when_esp_reports_obstacle(bridge):
    bridge._record_sensor_data(SensorData(s1=5, s2=200, s3=200, obstacle=True))
    allowed, reason = bridge._check_pi_side_safety(MotorCommand(direction="forward"))
    assert allowed is False
    assert reason


def test_forward_blocked_inside_warning_zone(bridge):
    bridge._record_sensor_data(SensorData(s1=15, s2=200, s3=200, warning=True))
    allowed, _ = bridge._check_pi_side_safety(MotorCommand(direction="forward"))
    assert allowed is False


def test_stop_is_never_blocked(bridge):
    bridge._record_sensor_data(SensorData(s1=1, s2=1, s3=1, obstacle=True))
    allowed, _ = bridge._check_pi_side_safety(MotorCommand(direction="stop"))
    assert allowed is True


def test_escape_manoeuvres_stay_available(bridge):
    """Blocking every direction at an obstacle would trap the robot."""
    bridge._record_sensor_data(SensorData(s1=1, s2=1, s3=1, obstacle=True))
    for direction in ("backward", "left", "right"):
        allowed, _ = bridge._check_pi_side_safety(MotorCommand(direction=direction))
        assert allowed is True, direction


# -- the fail-open cases -----------------------------------------------------

def test_forward_blocked_when_no_telemetry_has_ever_arrived(bridge):
    """Never heard from the MCU: that is ignorance, not safety.

    The gate used to read `if direction == "forward" and self._last_sensor_data`,
    so with no data the whole check was skipped and forward was permitted --
    exactly the state the robot is in at boot, or with the UART unplugged.
    """
    assert bridge._last_sensor_data is None
    allowed, reason = bridge._check_pi_side_safety(MotorCommand(direction="forward"))
    assert allowed is False
    assert "telemetry" in reason.lower() or "no sensor" in reason.lower()


def test_forward_blocked_when_telemetry_is_stale(bridge):
    """A frame from a minute ago says nothing about the road now.

    Without an age check, the last known-good frame authorises forward motion
    forever -- so an MCU that has crashed or been unplugged reads as a clear
    road, which is the same fail-open inversion the firmware had.
    """
    bridge._record_sensor_data(_clear())
    bridge._last_sensor_ts = time.time() - 60.0
    allowed, reason = bridge._check_pi_side_safety(MotorCommand(direction="forward"))
    assert allowed is False
    assert "stale" in reason.lower()


def test_forward_blocked_when_every_sensor_reads_invalid(bridge):
    """All three sensors returning -1 is blindness, not a clear road."""
    bridge._record_sensor_data(SensorData(s1=-1, s2=-1, s3=-1))
    allowed, reason = bridge._check_pi_side_safety(MotorCommand(direction="forward"))
    assert allowed is False
    assert "sensor" in reason.lower()


def test_fresh_telemetry_reopens_the_gate(bridge):
    bridge._record_sensor_data(_clear())
    bridge._last_sensor_ts = time.time() - 60.0
    assert bridge._check_pi_side_safety(MotorCommand(direction="forward"))[0] is False

    bridge._record_sensor_data(_clear())
    assert bridge._check_pi_side_safety(MotorCommand(direction="forward"))[0] is True
