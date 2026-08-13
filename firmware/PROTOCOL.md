# Pi ↔ motion MCU link protocol, v1

The contract between `src/uart/protocol.py` on the Raspberry Pi and the
firmware on the motion MCU. Both sides implement this document; the Python side
is the executable reference and its tests in `src/tests/test_uart_protocol.py`
are the conformance suite.

The MCU on the built robot is an **ESP32-WROOM-32** (30-pin devkit), and
`firmware/port/esp32` is the implementation that exists. The protocol is
deliberately MCU-agnostic — no hardware assumptions beyond a UART — so an
HK32F103/STM32F103 port can reuse `firmware/core/` unchanged.

## Why this replaced the ASCII protocol

The previous scheme wrote `FORWARD\n` and read back `DATA:S1:42,S2:...`. Four
properties of it were actively dangerous on a moving robot:

1. **No deadman.** Motor state was latched GPIO with no notion of command age.
   If the Pi crashed, the cable came loose, or `systemctl stop uart` ran, the
   robot kept driving until it hit something. Nothing on either side could
   detect that the link was gone.
2. **Sensors failed open.** `readDistance()` returned `-1` on echo timeout and
   the minimum-distance scan skipped non-positive values, so three unplugged
   sensors produced `minDist = 9999` — "clear road" — and re-enabled the motors.
3. **The parser was asymmetric.** `FORWARD` matched with `startsWith` while
   `STOP` required exact `==`. `STOP:0`, `STOP ` or any decorated stop fell
   through to `UNKNOWN` and left the motors latched. The most safety-critical
   verb had the strictest match.
4. **No integrity check.** No framing, no CRC, no sequence numbers, and the
   ACKs the MCU emitted were never read. A corrupted or dropped command was
   undetectable by either side.

## Physical layer

| Property | Value |
|---|---|
| Baud | 115200 |
| Format | 8N1, no flow control |
| Pi device | `/dev/serial0` (`nav.uart_device`) |
| Levels | 3.3 V TTL — **do not** connect a 5 V UART directly |

The MCU must never require flow control: the Pi side sets a write timeout and
treats a blocked write as a link fault.

## Frame format

```
+-------+-------+-------+-------+---------------+-----------+
| SOF   | LEN   | SEQ   | TYPE  | PAYLOAD       | CRC16     |
| 0xA5  | 1 B   | 1 B   | 1 B   | LEN - 2 bytes | 2 B, LE   |
+-------+-------+-------+-------+---------------+-----------+
```

- **SOF** — always `0xA5`.
- **LEN** — counts `SEQ + TYPE + PAYLOAD`, so `LEN = 2 + payload_len`. Valid
  range is `2..255`, giving a maximum payload of 253 bytes. Total frame size on
  the wire is `LEN + 4`.
- **SEQ** — incremented per frame by the sender, wraps at 256. Each direction
  keeps its own counter.
- **TYPE** — message type. Commands (Pi → MCU) are `< 0x80`, events
  (MCU → Pi) are `>= 0x80`.
- **CRC16** — CRC-16/CCITT-FALSE over `LEN`, `SEQ`, `TYPE` and `PAYLOAD`.
  Excludes the SOF and the CRC field itself. Little-endian on the wire.

### CRC

Poly `0x1021`, init `0xFFFF`, no input/output reflection, no final XOR. The
standard check value must hold on both sides:

```
crc16_ccitt("123456789") == 0x29B1
```

Reference implementation for the firmware — bit-serial, no table, no allocation:

```c
uint16_t crc16_ccitt(const uint8_t *data, uint16_t len) {
    uint16_t crc = 0xFFFF;
    while (len--) {
        crc ^= (uint16_t)(*data++) << 8;
        for (uint8_t i = 0; i < 8; i++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}
```

### Resynchronisation

A receiver opened mid-stream, or one that hits corruption, recovers as follows:

1. Scan forward to the next `0xA5`, discarding everything before it.
2. If `LEN < 2`, that byte was payload, not a header — discard **only that
   byte** and rescan from the next one.
3. If the CRC fails, likewise discard only the SOF byte and rescan.

Discarding the whole candidate frame on a CRC failure is wrong: it can swallow
a genuine frame that began inside the discarded span. Recovery is bounded to at
most one frame's worth of bytes.

Receivers must bound their reassembly buffer. The Python decoder uses 2048
bytes and counts `crc_errors`, `resyncs` and `dropped_bytes` so link quality is
observable rather than guessed at.

## Message catalogue

### Pi → MCU

| Type | Name | Payload | Meaning |
|---|---|---|---|
| `0x01` | `CMD_DRIVE` | `int8 left, int8 right` | Per-side duty, −100..100 % |
| `0x02` | `CMD_STOP` | — | Immediate brake |
| `0x03` | `CMD_KEEPALIVE` | — | Renew the motion lease, no duty change |
| `0x04` | `CMD_SERVO` | `uint8 angle` | 0..180° |
| `0x05` | `CMD_SET_LIMITS` | `uint16 stop_mm, uint16 warn_mm` | Obstacle thresholds |
| `0x06` | `CMD_CLEAR_FAULT` | — | Clear latched faults (see caveat below) |
| `0x07` | `CMD_PING` | — | Liveness probe |

Turns are counter-rotation: `left` and `right` take opposite signs. This
replaces the old `LEFT`/`RIGHT` tokens with a real differential-drive
primitive, so speed and radius are both controllable — the old firmware had no
PWM at all and drove every motion at 100 % duty.

### MCU → Pi

| Type | Name | Payload | Rate |
|---|---|---|---|
| `0x81` | `EVT_TELEMETRY` | 18 bytes, below | 20 Hz |
| `0x82` | `EVT_ACK` | `uint8 acked_seq, uint8 status` | per command |
| `0x83` | `EVT_FAULT` | `uint16 fault_bits, uint16 detail` | on change |
| `0x84` | `EVT_BOOT` | `uint8 proto, uint8 major, uint8 minor` | once at reset |

`EVT_BOOT` lets the Pi detect an MCU reset it did not initiate — a brownout, a
watchdog bite, or a loose power lead — which the old protocol could not
distinguish from silence.

### `EVT_TELEMETRY` payload

Little-endian, 18 bytes, struct format `<HHHHBbbBHI`:

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 2 | `distance_mm[0]` | `0xFFFF` = sensor faulted |
| 2 | 2 | `distance_mm[1]` | |
| 4 | 2 | `distance_mm[2]` | |
| 6 | 2 | `gas_raw` | Gas sensor ADC (MQ-3), 0..4095 |
| 8 | 1 | `servo_deg` | |
| 9 | 1 | `duty_left` | signed, −100..100 — **actual** applied duty |
| 10 | 1 | `duty_right` | signed |
| 11 | 1 | `flags` | live state bits |
| 12 | 2 | `faults` | latched fault bits |
| 14 | 4 | `uptime_ms` | since MCU reset |

`duty_left`/`duty_right` must report what the MCU is *actually* driving, not
what was last requested. The old firmware declared `leftMotorSpeed` and
`rightMotorSpeed` and never assigned them, so telemetry reported `0` while the
robot was moving.

Distances are millimetres, not centimetres, and `0xFFFF` is the explicit
"no answer" sentinel. A consumer that forgets to check it sees an implausibly
large value and fails loud, rather than a plausibly small one.

**Flags** (`uint8`): `OBSTACLE 0x01`, `WARNING 0x02`, `MOVING 0x04`,
`ARMED 0x08`, `SCANNING 0x10`.

**Faults** (`uint16`, latched): `COMM_LOST 0x0001`, `SENSOR_1 0x0002`,
`SENSOR_2 0x0004`, `SENSOR_3 0x0008`, `ALL_SENSORS_LOST 0x0010`,
`OVERCURRENT 0x0020`, `LOW_BATTERY 0x0040`, `MOTOR_FAULT 0x0080`.

**ACK status**: `OK 0x00`, `BAD_LENGTH 0x01`, `UNKNOWN_TYPE 0x02`,
`REFUSED_OBSTACLE 0x03`, `REFUSED_FAULT 0x04`, `CLAMPED 0x05`.

A refused command is still ACKed, with the reason. Silence must only ever mean
"the link is broken", never "I chose not to".

## Motion is a lease, not a latch

This is the single most important behavioural change.

- The MCU keeps `last_valid_frame_ms`, updated on **any** correctly-framed,
  CRC-valid frame.
- If `now - last_valid_frame_ms > 300 ms` and either duty is non-zero, the MCU
  **brakes** and latches `COMM_LOST`.
- The Pi sends `CMD_KEEPALIVE` every 100 ms for as long as it intends motion to
  continue. Three consecutive misses stop the robot.
- `CMD_KEEPALIVE` renews the lease without altering duty, so keepalives cannot
  accidentally restart motion after a stop.

Consequences, all of which were previously failure modes: pulling the UART
cable stops the robot; `systemctl stop uart` stops the robot; an orchestrator
crash stops the robot; a wedged Pi stops the robot. None of this depends on the
Pi behaving correctly, which is the entire point — the Pi is the component most
likely to fail.

## Safety authority lives on the MCU

The MCU is the final authority on motion and may refuse any command. The Pi's
checks in `motor_bridge` and `orchestrator` are advisory duplicates and cannot
be relied on, because they are useless precisely when the Pi is the thing that
failed.

**Sensors fail closed.** A sensor with N consecutive echo timeouts reports
`0xFFFF` and sets its `SENSOR_n` fault bit. If *all* sensors are faulted, the
MCU sets `ALL_SENSORS_LOST` and treats the situation as an obstacle. Blindness
is never clear road.

**Every direction is gated, not just forward.** The old firmware consulted
`motorsEnabled`/`obstacleDetected` in exactly one branch — `FORWARD` — so
`BACKWARD`, `LEFT` and `RIGHT` executed unconditionally at 0 cm and full duty.
Under v1:

- Forward is refused below `stop_mm` (`REFUSED_OBSTACLE`).
- Rotation and reverse are permitted inside the stop zone but **clamped to an
  escape duty** (≈30 %), because you must be able to back out of a corner.
- Reverse is inherently blind: there is no rear sensor on this chassis. It is
  clamped to escape duty at all times. Fitting a rear sensor is the real fix
  and the firmware reserves `distance_mm[2]` for it.

**`CMD_CLEAR_FAULT` re-reads the sensors before clearing.** The old
`CLEARBLOCK` cleared the flags blind, so `CLEARBLOCK` + `FORWARD` drove into a
wall until the next sensor sweep re-latched roughly 50–140 ms later. If an
obstacle is still present, the clear is ACKed `REFUSED_OBSTACLE` and the fault
stays latched.

**Nothing blocks the control loop.** Echo timing uses timer input capture
rather than blocking `pulseIn` (which cost up to 90 ms per iteration), the
three sensors are triggered round-robin one per slot to avoid cross-talk, and
`SCAN` is a state machine rather than a chain of `delay()` calls — the old
`performScan()` blocked for ~2.8 s during which no commands were read and no
collision check ran, while the chassis was spinning.

**IWDG.** The independent watchdog runs from the LSI oscillator and is petted
only when the main loop completes a full cycle, so it survives a main-clock
failure and bites on a hung loop.

## Golden vectors

Byte-exact frames for firmware bring-up. Verified against
`src/uart/protocol.py`.

```
CMD_STOP          seq=1              A5 02 01 02 8F B1
CMD_DRIVE         seq=1 fwd 70%      A5 04 01 01 46 46 E6 56
CMD_DRIVE         seq=1 left 70%     A5 04 01 01 BA 46 4A 00
CMD_KEEPALIVE     seq=1              A5 02 01 03 AE A1
CMD_SERVO         seq=1 angle=90     A5 03 01 04 5A 57 1F
EVT_ACK           seq=1 ack(1,OK)    A5 04 01 82 01 00 B5 88
EVT_TELEMETRY     seq=1              A5 14 01 81 B0 04 20 03 D0 07 36 01
                                     5A 00 00 08 00 00 40 E2 01 00 E9 29
```

That telemetry frame decodes to distances `(1200, 800, 2000) mm`, gas `310`,
servo `90°`, duties `0/0`, flags `ARMED`, no faults, uptime `123456 ms`.

## Migration

`nav.command` payloads on the ZeroMQ bus are unchanged — the orchestrator still
publishes `{"direction": "forward"}`. `CommandEncoder.drive_direction()` maps
that vocabulary onto duty pairs, so only `src/uart/motor_bridge.py` changes on
the Pi side.

Unknown directions map to a stop, which is the same defaulting the ASCII bridge
did, except here it is an explicit table lookup rather than a fallthrough in a
prefix-matching `if`/`else if` chain.
