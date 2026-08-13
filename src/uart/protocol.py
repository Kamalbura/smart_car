"""Framed, checksummed link protocol between the Pi and the motion MCU.

This replaces the newline-delimited ASCII scheme (``FORWARD\\n`` outbound,
``DATA:S1:42,S2:...`` inbound), which had no framing, no checksum, no sequence
numbers, and ACKs that the Pi never read. Four specific hazards motivated the
rewrite:

* **No deadman.** Motor state was latched GPIO. If the Pi died, the cable came
  loose, or ``uart.service`` was stopped, the robot kept driving indefinitely.
  Here, motion is a *lease*: the MCU brakes unless it keeps hearing from us.
* **Fail-open sensors.** Three simultaneous echo timeouts read as "clear road".
  Here, a faulted sensor reports ``DISTANCE_FAULT`` and the MCU treats a total
  sensor loss as an obstacle.
* **Asymmetric parsing.** ``FORWARD`` matched by prefix while ``STOP`` required
  exact equality, so any decorated stop was a silent no-op that left the motors
  latched. Here, commands are opaque type bytes -- there is no partial match.
* **No integrity check.** Neither side could detect a corrupted or dropped
  command. Here, every frame carries a CRC and a sequence number.

The wire format is deliberately plain enough to implement identically in C on a
Cortex-M3 with no dynamic allocation and no libc string handling.

Frame layout::

    +-------+-------+-------+-------+-------------+---------+
    | SOF   | LEN   | SEQ   | TYPE  | PAYLOAD     | CRC16   |
    | 0xA5  | 1 B   | 1 B   | 1 B   | LEN - 2 B   | 2 B LE  |
    +-------+-------+-------+-------+-------------+---------+

``LEN`` counts SEQ + TYPE + PAYLOAD, so it equals ``2 + len(payload)`` and the
whole frame occupies ``LEN + 4`` bytes. The CRC is CRC-16/CCITT-FALSE (poly
0x1021, init 0xFFFF, no reflection, no final XOR) over LEN, SEQ, TYPE and
PAYLOAD -- everything except the SOF and the CRC field itself.

A stray 0xA5 inside a payload cannot desynchronise the stream permanently: an
implausible length or a failed CRC causes the decoder to discard that one byte
and rescan from the next, so it recovers within at most one frame.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import List, Optional, Tuple

SOF = 0xA5
PROTOCOL_VERSION = 1

#: ``LEN`` is a single byte covering SEQ + TYPE + PAYLOAD.
MAX_PAYLOAD = 0xFF - 2

#: Sentinel distance meaning "this sensor did not answer". Chosen so that a
#: naive consumer that forgets to check sees an implausibly large value rather
#: than a plausibly small one -- failing loud instead of driving forward.
DISTANCE_FAULT = 0xFFFF

#: The MCU brakes if it has not received a valid frame within this window.
#: The Pi must send a keepalive at roughly 3x this rate while it intends motion
#: to continue.
COMMAND_TIMEOUT_MS = 300
KEEPALIVE_INTERVAL_MS = 100


class MsgType(IntEnum):
    """Message type byte. Pi->MCU commands are < 0x80, MCU->Pi events >= 0x80."""

    CMD_DRIVE = 0x01
    CMD_STOP = 0x02
    CMD_KEEPALIVE = 0x03
    CMD_SERVO = 0x04
    CMD_SET_LIMITS = 0x05
    CMD_CLEAR_FAULT = 0x06
    CMD_PING = 0x07

    EVT_TELEMETRY = 0x81
    EVT_ACK = 0x82
    EVT_FAULT = 0x83
    EVT_BOOT = 0x84


class AckStatus(IntEnum):
    OK = 0x00
    BAD_LENGTH = 0x01
    UNKNOWN_TYPE = 0x02
    REFUSED_OBSTACLE = 0x03
    REFUSED_FAULT = 0x04
    CLAMPED = 0x05


class Flag(IntFlag):
    """Live state bits in telemetry."""

    OBSTACLE = 0x01
    WARNING = 0x02
    MOVING = 0x04
    ARMED = 0x08
    SCANNING = 0x10


class Fault(IntFlag):
    """Latched fault bits. Cleared by :func:`clear_fault`."""

    NONE = 0x0000
    COMM_LOST = 0x0001
    SENSOR_1 = 0x0002
    SENSOR_2 = 0x0004
    SENSOR_3 = 0x0008
    ALL_SENSORS_LOST = 0x0010
    OVERCURRENT = 0x0020
    LOW_BATTERY = 0x0040
    MOTOR_FAULT = 0x0080


# ---------------------------------------------------------------------------
# CRC
# ---------------------------------------------------------------------------

def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE. Bit-serial to mirror the MCU implementation."""
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Frame:
    seq: int
    msg_type: int
    payload: bytes

    @property
    def type_name(self) -> str:
        try:
            return MsgType(self.msg_type).name
        except ValueError:
            return f"UNKNOWN_0x{self.msg_type:02X}"


def encode_frame(seq: int, msg_type: int, payload: bytes = b"") -> bytes:
    """Serialise one frame. ``seq`` wraps at 256."""
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload of {len(payload)} exceeds {MAX_PAYLOAD}")
    body = bytes([2 + len(payload), seq & 0xFF, msg_type & 0xFF]) + payload
    return bytes([SOF]) + body + struct.pack("<H", crc16_ccitt(body))


class FrameDecoder:
    """Incremental decoder for a byte stream that may start mid-frame.

    Tolerates garbage, truncation and resynchronisation, and bounds its own
    buffer so a peer emitting noise forever cannot grow it without limit.
    """

    def __init__(self, max_buffer: int = 2048) -> None:
        self._buf = bytearray()
        self._max_buffer = max_buffer
        self.crc_errors = 0
        self.resyncs = 0
        self.dropped_bytes = 0

    def feed(self, data: bytes) -> List[Frame]:
        """Add received bytes and return every complete frame now available."""
        self._buf.extend(data)
        if len(self._buf) > self._max_buffer:
            excess = len(self._buf) - self._max_buffer
            del self._buf[:excess]
            self.dropped_bytes += excess
        frames: List[Frame] = []
        while True:
            frame, progressed = self._try_decode_one()
            if frame is not None:
                frames.append(frame)
                continue
            if not progressed:
                break
        return frames

    def _try_decode_one(self) -> Tuple[Optional[Frame], bool]:
        """Return ``(frame, progressed)``.

        ``progressed`` is True whenever bytes were consumed or discarded, which
        tells the caller to try again immediately. Discarding a spurious SOF
        must not end the scan -- otherwise a single corrupted frame hides every
        good frame queued behind it until more data happens to arrive.
        """
        buf = self._buf
        start = buf.find(SOF)
        if start < 0:
            if buf:
                self.dropped_bytes += len(buf)
                del buf[:]
                return None, True
            return None, False
        if start > 0:
            self.dropped_bytes += start
            self.resyncs += 1
            del buf[:start]

        # Need SOF + LEN before the length is even known.
        if len(buf) < 2:
            return None, False
        length = buf[1]
        if length < 2 or length > 2 + MAX_PAYLOAD:
            # Implausible length: that 0xA5 was payload, not a header.
            self._drop_false_sof()
            return None, True

        total = length + 4
        if len(buf) < total:
            return None, False

        body = bytes(buf[1 : 2 + length])
        received_crc = struct.unpack_from("<H", buf, 2 + length)[0]
        if crc16_ccitt(body) != received_crc:
            self.crc_errors += 1
            self._drop_false_sof()
            return None, True

        frame = Frame(seq=buf[2], msg_type=buf[3], payload=bytes(buf[4:total - 2]))
        del buf[:total]
        return frame, True

    def _drop_false_sof(self) -> None:
        """Discard one byte so the scan continues past a spurious SOF."""
        del self._buf[:1]
        self.dropped_bytes += 1
        self.resyncs += 1


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

_TELEMETRY_STRUCT = struct.Struct("<HHHHBbbBHI")
TELEMETRY_SIZE = _TELEMETRY_STRUCT.size  # 18


@dataclass(frozen=True)
class Telemetry:
    distance_mm: tuple  # three sensors; DISTANCE_FAULT if that sensor is out
    gas_raw: int
    servo_deg: int
    duty_left: int
    duty_right: int
    flags: Flag
    faults: Fault
    uptime_ms: int

    @classmethod
    def from_payload(cls, payload: bytes) -> "Telemetry":
        if len(payload) != TELEMETRY_SIZE:
            raise ValueError(
                f"telemetry payload is {len(payload)} bytes, expected {TELEMETRY_SIZE}"
            )
        d1, d2, d3, gas, servo, left, right, flags, faults, uptime = (
            _TELEMETRY_STRUCT.unpack(payload)
        )
        return cls(
            distance_mm=(d1, d2, d3),
            gas_raw=gas,
            servo_deg=servo,
            duty_left=left,
            duty_right=right,
            flags=Flag(flags),
            faults=Fault(faults),
            uptime_ms=uptime,
        )

    def to_payload(self) -> bytes:
        return _TELEMETRY_STRUCT.pack(
            self.distance_mm[0],
            self.distance_mm[1],
            self.distance_mm[2],
            self.gas_raw,
            self.servo_deg,
            self.duty_left,
            self.duty_right,
            int(self.flags),
            int(self.faults),
            self.uptime_ms,
        )

    @property
    def min_distance_mm(self) -> Optional[int]:
        """Closest working sensor, or ``None`` if every sensor is faulted.

        ``None`` is deliberately not 0 and not a large number: callers are
        forced to handle "I cannot see" as its own case rather than
        accidentally treating it as clear road, which is precisely the bug this
        protocol exists to fix.
        """
        working = [d for d in self.distance_mm if d != DISTANCE_FAULT]
        return min(working) if working else None

    @property
    def sensors_lost(self) -> bool:
        return all(d == DISTANCE_FAULT for d in self.distance_mm)


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


#: Differential-drive duty pairs for the direction vocabulary the orchestrator
#: already speaks, so `nav.command` payloads need no change. Left/right signs
#: give counter-rotation for turns (spin in place).
DIRECTION_TO_DUTY = {
    "forward": (1, 1),
    "backward": (-1, -1),
    "left": (-1, 1),
    "right": (1, -1),
    "stop": (0, 0),
}


class CommandEncoder:
    """Builds outbound frames and owns the sequence counter."""

    def __init__(self) -> None:
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    @property
    def last_seq(self) -> int:
        return self._seq

    def drive(self, left_pct: int, right_pct: int) -> bytes:
        """Set per-side duty as a signed percentage, -100..100."""
        payload = struct.pack(
            "<bb", _clamp(int(left_pct), -100, 100), _clamp(int(right_pct), -100, 100)
        )
        return encode_frame(self._next_seq(), MsgType.CMD_DRIVE, payload)

    def drive_direction(self, direction: str, speed_pct: int = 70) -> bytes:
        """Encode one of the orchestrator's direction words as a duty pair.

        Unknown directions become a stop. That is the same defaulting the old
        ASCII bridge did, but here it is explicit rather than a fallthrough in
        a prefix-matching parser.
        """
        left, right = DIRECTION_TO_DUTY.get(str(direction).strip().lower(), (0, 0))
        speed = _clamp(int(speed_pct), 0, 100)
        return self.drive(left * speed, right * speed)

    def stop(self) -> bytes:
        return encode_frame(self._next_seq(), MsgType.CMD_STOP)

    def keepalive(self) -> bytes:
        """Refresh the motion lease without changing the commanded duty."""
        return encode_frame(self._next_seq(), MsgType.CMD_KEEPALIVE)

    def servo(self, angle_deg: int) -> bytes:
        payload = struct.pack("<B", _clamp(int(angle_deg), 0, 180))
        return encode_frame(self._next_seq(), MsgType.CMD_SERVO, payload)

    def set_limits(self, stop_mm: int, warn_mm: int) -> bytes:
        payload = struct.pack(
            "<HH", _clamp(int(stop_mm), 0, 4000), _clamp(int(warn_mm), 0, 4000)
        )
        return encode_frame(self._next_seq(), MsgType.CMD_SET_LIMITS, payload)

    def clear_fault(self) -> bytes:
        return encode_frame(self._next_seq(), MsgType.CMD_CLEAR_FAULT)

    def ping(self) -> bytes:
        return encode_frame(self._next_seq(), MsgType.CMD_PING)


def parse_ack(payload: bytes) -> tuple:
    """Return ``(acked_seq, AckStatus)`` from an EVT_ACK payload."""
    if len(payload) != 2:
        raise ValueError(f"ack payload is {len(payload)} bytes, expected 2")
    seq, status = struct.unpack("<BB", payload)
    try:
        return seq, AckStatus(status)
    except ValueError:
        return seq, status
