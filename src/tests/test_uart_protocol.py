"""Link-protocol tests.

The decoder has to survive a real serial line: it is opened mid-stream, the
MCU is already talking, bytes arrive one at a time or in clumps, and payloads
contain bytes that look like frame headers. Every case below is something that
actually happens on a 115200 8N1 line with no flow control.
"""
from __future__ import annotations

import struct

import pytest

from src.uart.protocol import (
    DISTANCE_FAULT,
    MAX_PAYLOAD,
    SOF,
    TELEMETRY_SIZE,
    AckStatus,
    CommandEncoder,
    Fault,
    Flag,
    Frame,
    FrameDecoder,
    MsgType,
    Telemetry,
    crc16_ccitt,
    encode_frame,
    parse_ack,
)


# ---------------------------------------------------------------------------
# CRC
# ---------------------------------------------------------------------------

def test_crc_matches_the_published_ccitt_false_check_value():
    """Pins the algorithm so the C implementation can be verified against it.

    0x29B1 over b"123456789" is the standard CRC-16/CCITT-FALSE check value. If
    this assertion ever changes, the MCU and the Pi have silently diverged.
    """
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_crc_is_order_sensitive():
    assert crc16_ccitt(b"\x01\x02") != crc16_ccitt(b"\x02\x01")


# ---------------------------------------------------------------------------
# Framing round-trip
# ---------------------------------------------------------------------------

def test_roundtrip_with_payload():
    raw = encode_frame(7, MsgType.CMD_DRIVE, b"\x40\x40")
    frames = FrameDecoder().feed(raw)
    assert frames == [Frame(seq=7, msg_type=MsgType.CMD_DRIVE, payload=b"\x40\x40")]


def test_roundtrip_without_payload():
    raw = encode_frame(0, MsgType.CMD_STOP)
    (frame,) = FrameDecoder().feed(raw)
    assert frame.seq == 0
    assert frame.msg_type == MsgType.CMD_STOP
    assert frame.payload == b""


def test_frame_is_len_plus_four_bytes():
    assert len(encode_frame(1, MsgType.CMD_STOP)) == 2 + 4
    assert len(encode_frame(1, MsgType.CMD_DRIVE, b"\xff\xff")) == 4 + 4


def test_max_payload_roundtrips_and_oversize_raises():
    payload = bytes(MAX_PAYLOAD)
    (frame,) = FrameDecoder().feed(encode_frame(1, MsgType.EVT_TELEMETRY, payload))
    assert frame.payload == payload
    with pytest.raises(ValueError):
        encode_frame(1, MsgType.EVT_TELEMETRY, bytes(MAX_PAYLOAD + 1))


def test_sequence_wraps_at_256():
    enc = CommandEncoder()
    for _ in range(255):
        enc.stop()
    assert enc.last_seq == 255
    enc.stop()
    assert enc.last_seq == 0


# ---------------------------------------------------------------------------
# Streaming, resync and corruption
# ---------------------------------------------------------------------------

def test_byte_at_a_time_delivery():
    raw = encode_frame(3, MsgType.CMD_DRIVE, b"\x10\x20")
    decoder = FrameDecoder()
    collected = []
    for byte in raw:
        collected.extend(decoder.feed(bytes([byte])))
    assert len(collected) == 1
    assert collected[0].payload == b"\x10\x20"


def test_garbage_prefix_is_discarded():
    """Opening the port mid-stream must not lose the next good frame."""
    decoder = FrameDecoder()
    (frame,) = decoder.feed(b"\x00\x11garbage" + encode_frame(5, MsgType.CMD_PING))
    assert frame.seq == 5
    assert decoder.dropped_bytes > 0


def test_payload_containing_sof_survives():
    # 0xA5 inside the payload must not be mistaken for a header.
    payload = bytes([SOF, SOF, 0x02, SOF])
    (frame,) = FrameDecoder().feed(encode_frame(9, MsgType.EVT_TELEMETRY, payload))
    assert frame.payload == payload


def test_corrupted_crc_is_rejected():
    raw = bytearray(encode_frame(1, MsgType.CMD_DRIVE, b"\x40\x40"))
    raw[-1] ^= 0xFF
    decoder = FrameDecoder()
    assert decoder.feed(bytes(raw)) == []
    assert decoder.crc_errors == 1


def test_corrupted_payload_is_rejected():
    raw = bytearray(encode_frame(1, MsgType.CMD_DRIVE, b"\x40\x40"))
    raw[4] ^= 0xFF  # flip a payload bit, leave the CRC alone
    decoder = FrameDecoder()
    assert decoder.feed(bytes(raw)) == []
    assert decoder.crc_errors == 1


def test_recovers_on_the_frame_after_a_corrupted_one():
    bad = bytearray(encode_frame(1, MsgType.CMD_DRIVE, b"\x40\x40"))
    bad[-1] ^= 0xFF
    good = encode_frame(2, MsgType.CMD_STOP)
    frames = FrameDecoder().feed(bytes(bad) + good)
    assert [f.seq for f in frames] == [2]


def test_truncated_frame_completes_on_the_next_read():
    raw = encode_frame(4, MsgType.CMD_DRIVE, b"\x01\x02")
    decoder = FrameDecoder()
    assert decoder.feed(raw[:5]) == []
    (frame,) = decoder.feed(raw[5:])
    assert frame.seq == 4


def test_implausible_length_does_not_wedge_the_decoder():
    # A stray SOF followed by LEN=0 is not a real header; the decoder must skip
    # it rather than waiting forever for a frame that will never arrive.
    good = encode_frame(6, MsgType.CMD_PING)
    (frame,) = FrameDecoder().feed(bytes([SOF, 0x00]) + good)
    assert frame.seq == 6


def test_multiple_frames_in_one_read():
    raw = b"".join(
        encode_frame(i, MsgType.CMD_KEEPALIVE) for i in range(5)
    )
    frames = FrameDecoder().feed(raw)
    assert [f.seq for f in frames] == [0, 1, 2, 3, 4]


def test_buffer_is_bounded_against_a_noisy_peer():
    decoder = FrameDecoder(max_buffer=64)
    for _ in range(100):
        decoder.feed(b"\x00" * 64)
    assert len(decoder._buf) <= 64
    # A good frame still decodes after all that noise.
    (frame,) = decoder.feed(encode_frame(1, MsgType.CMD_PING))
    assert frame.msg_type == MsgType.CMD_PING


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

def _telemetry(**overrides) -> Telemetry:
    base = dict(
        distance_mm=(1200, 800, 2000),
        gas_raw=310,
        servo_deg=90,
        duty_left=0,
        duty_right=0,
        flags=Flag.ARMED,
        faults=Fault.NONE,
        uptime_ms=123456,
    )
    base.update(overrides)
    return Telemetry(**base)


def test_telemetry_roundtrip():
    original = _telemetry(duty_left=-70, duty_right=70, flags=Flag.ARMED | Flag.MOVING)
    assert Telemetry.from_payload(original.to_payload()) == original


def test_telemetry_payload_is_the_documented_size():
    assert TELEMETRY_SIZE == 18
    assert len(_telemetry().to_payload()) == 18


def test_telemetry_rejects_wrong_size():
    with pytest.raises(ValueError):
        Telemetry.from_payload(b"\x00" * 17)


def test_negative_duty_survives_the_signed_encoding():
    assert Telemetry.from_payload(_telemetry(duty_left=-100).to_payload()).duty_left == -100


def test_min_distance_ignores_faulted_sensors():
    t = _telemetry(distance_mm=(DISTANCE_FAULT, 850, 1500))
    assert t.min_distance_mm == 850
    assert t.sensors_lost is False


def test_total_sensor_loss_reports_none_not_clear_road():
    """The original bug: no reading was indistinguishable from a clear path."""
    t = _telemetry(distance_mm=(DISTANCE_FAULT,) * 3)
    assert t.sensors_lost is True
    assert t.min_distance_mm is None


def test_fault_flags_decode_as_a_set():
    t = _telemetry(faults=Fault.COMM_LOST | Fault.SENSOR_2)
    decoded = Telemetry.from_payload(t.to_payload())
    assert Fault.COMM_LOST in decoded.faults
    assert Fault.SENSOR_2 in decoded.faults
    assert Fault.OVERCURRENT not in decoded.faults


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "direction,expected",
    [
        ("forward", (70, 70)),
        ("backward", (-70, -70)),
        ("left", (-70, 70)),
        ("right", (70, -70)),
        ("stop", (0, 0)),
        ("FORWARD", (70, 70)),
        ("  forward  ", (70, 70)),
    ],
)
def test_direction_maps_to_duty_pair(direction, expected):
    (frame,) = FrameDecoder().feed(CommandEncoder().drive_direction(direction, 70))
    assert struct.unpack("<bb", frame.payload) == expected


@pytest.mark.parametrize("direction", ["sideways", "", "banana", "STOP:0", "forwardx"])
def test_unknown_direction_becomes_a_stop(direction):
    """Notably including "STOP:0" and "forwardx", the two shapes the old
    prefix/exact-match parser handled inconsistently."""
    (frame,) = FrameDecoder().feed(CommandEncoder().drive_direction(direction, 70))
    assert struct.unpack("<bb", frame.payload) == (0, 0)


def test_duty_is_clamped_to_the_legal_range():
    (frame,) = FrameDecoder().feed(CommandEncoder().drive(500, -500))
    assert struct.unpack("<bb", frame.payload) == (100, -100)


def test_servo_angle_is_clamped():
    for requested, expected in ((-30, 0), (0, 0), (90, 90), (180, 180), (999, 180)):
        (frame,) = FrameDecoder().feed(CommandEncoder().servo(requested))
        assert frame.payload == bytes([expected])


def test_set_limits_roundtrip():
    (frame,) = FrameDecoder().feed(CommandEncoder().set_limits(100, 200))
    assert struct.unpack("<HH", frame.payload) == (100, 200)


def test_parse_ack():
    payload = struct.pack("<BB", 42, AckStatus.REFUSED_OBSTACLE)
    assert parse_ack(payload) == (42, AckStatus.REFUSED_OBSTACLE)


def test_parse_ack_tolerates_an_unknown_status_code():
    seq, status = parse_ack(struct.pack("<BB", 9, 0xEE))
    assert seq == 9
    assert status == 0xEE


def test_parse_ack_rejects_wrong_size():
    with pytest.raises(ValueError):
        parse_ack(b"\x01")


def test_every_command_encodes_to_a_decodable_frame():
    """Guards against a builder that forgets to bump the sequence number."""
    enc = CommandEncoder()
    raw = b"".join(
        [
            enc.drive(50, 50),
            enc.stop(),
            enc.keepalive(),
            enc.servo(45),
            enc.set_limits(120, 250),
            enc.clear_fault(),
            enc.ping(),
        ]
    )
    frames = FrameDecoder().feed(raw)
    assert len(frames) == 7
    assert [f.seq for f in frames] == [1, 2, 3, 4, 5, 6, 7]
    assert [f.msg_type for f in frames] == [
        MsgType.CMD_DRIVE,
        MsgType.CMD_STOP,
        MsgType.CMD_KEEPALIVE,
        MsgType.CMD_SERVO,
        MsgType.CMD_SET_LIMITS,
        MsgType.CMD_CLEAR_FAULT,
        MsgType.CMD_PING,
    ]
