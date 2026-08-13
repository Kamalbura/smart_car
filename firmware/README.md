# Motion MCU firmware

The second processor. It owns the motors, the ultrasonics, the servo and the
gas sensor, and it is the **final authority on whether the robot moves** — the
Raspberry Pi can only ask.

That split is the point. The Pi runs Linux, Python, three cloud SDKs and a
neural network; it is the component most likely to hang, crash or get
`systemctl stop`ped. Nothing about the robot's physical safety may depend on it
behaving correctly.

## Layout

```
firmware/
├── PROTOCOL.md          wire format, message catalogue, golden vectors
├── CMakeLists.txt       host test build
├── core/                portable, no hardware dependencies
│   ├── sc_protocol.c    framing + CRC
│   └── sc_safety.c      motion-safety state machine
├── test/                host tests for the above
└── port/
    ├── esp32/           ESP-IDF project  (buildable today)
    └── stm32/           HK32F103/STM32F103 port (planned)
```

`core/` is compiled into every target unchanged. There is one copy of the
protocol and one copy of the safety rules; a change that breaks the tests
breaks the firmware too.

## What is verified, and how

The two things that are dangerous to get wrong are frame integrity and the
motion rules, so those live in `core/` and are tested three ways:

1. **`src/uart/safety.py` + `src/tests/test_uart_safety.py`** — the reference
   implementation, 22 conformance vectors, run by `pytest`.
2. **`firmware/test/test_safety.c`** — the same 22 vectors against the C, plus
   a millisecond-wrap case that only matters on the target.
3. **`firmware/test/test_protocol.c`** — byte-exact golden vectors shared with
   `src/uart/protocol.py`. If these pass, the Pi and the MCU cannot disagree
   about the wire format.

Driver code (`port/*/drv_*.c`) is not unit-tested; it is verified on the bench
against the checklist at the bottom of this file.

## Running the host tests

These build for your development machine, not the target — no ESP-IDF and no
ARM toolchain needed, just a C compiler.

```bash
cmake -S firmware -B firmware/build -G Ninja
cmake --build firmware/build
./firmware/build/sc_tests
```

If CMake reports **no C compiler**, pick one:

- **On the Raspberry Pi** — it already has gcc, and the Python side runs there
  anyway. Zero installation; this is the easiest route.
- **On Windows** — `choco install mingw`, or install the Visual Studio Build
  Tools and drop the `-G Ninja` flag.

Expected output ends with `OK` and a non-zero check count. A failing golden
vector means the wire format has drifted and nothing else matters until it is
fixed.

## ESP32

Built and flashed with ESP-IDF v5.2:

```bash
cd firmware/port/esp32
idf.py set-target esp32
idf.py build
idf.py -p COM5 flash monitor
```

`idf.py` must run from a real ESP-IDF shell. Under Git Bash / MSys it prints
`MSys/Mingw is no longer supported` **and exits 0 without building anything**,
so always confirm `build/smart_car_mcu.bin` actually exists rather than
trusting the exit code. Use PowerShell (`export.ps1`) or the ESP-IDF CMD
shortcut.

`sdkconfig` is generated; only `sdkconfig.defaults` is tracked.

### Wiring — unchanged from the previous build

| Function | GPIO |
|---|---|
| Sonar 1 trig / echo | 4 / 5 |
| Sonar 2 trig / echo | 18 / 19 |
| Sonar 3 trig / echo | 21 / 22 |
| MQ-3 gas (ADC1_CH6) | 34 |
| Servo | 23 |
| Motor left IN1 / IN2 | 25 / 26 |
| Motor right IN1 / IN2 | 27 / 14 |
| Link to Pi (UART2) RX / TX | 16 / 17 |

ENA/ENB are jumpered high, so PWM is applied to the direction pins directly.

The console stays on UART0 and the Pi link is UART2, so log output can never
corrupt the protocol stream. The previous firmware shared a single command
buffer between the USB console and the Pi, which meant a half-typed console
command and a Pi command could concatenate into one garbage token.

## HK32F103 / STM32F103 (planned)

Same `core/`, different `port/`. The MCU is a better fit than the ESP32 for
this job — no radio stack stealing determinism from the safety loop, hardware
timer input capture for echo timing, TIM1's dead-time insertion and BRK input
for the H-bridge, and 5 V-tolerant GPIO so HC-SR04 ECHO needs no divider.

Two things to know before you start, both specific to the HK32 clone:

- **SWD attach fails out of the box.** Its debug IDCODE differs from a genuine
  ST part, so OpenOCD refuses with an IDCODE mismatch. Bypass the check with
  `-c "set CPUTAPID 0"`. Budget an evening for this; it is the whole difficulty
  of using an HK32.
- **Skip USB.** The USB peripheral is the least-compatible block on these
  clones, and some parts ship without ST's system-memory DFU bootloader. Flash
  over SWD (any ST-Link clone) or the UART bootloader. This firmware needs
  neither.

## Bench bring-up checklist

Do these in order, with the robot **on blocks, wheels off the ground**, before
it is ever allowed to drive on the floor.

1. `idf.py monitor` — confirm the boot banner and `EVT_BOOT`.
2. Telemetry arrives at 20 Hz with plausible distances. Wave a hand at each
   sensor in turn and watch the right field move.
3. Unplug one sonar. That sensor reports `0xFFFF` after three sweeps and its
   `SENSOR_n` fault bit sets; the other two keep working.
4. Unplug all three. `ALL_SENSORS_LOST` sets and forward is refused with
   `REFUSED_OBSTACLE`. **Blindness must read as blocked, never as clear road.**
5. Command forward at 50 %. Confirm both wheels turn and telemetry reports the
   duty actually applied.
6. Put an obstacle inside the stop distance. Forward is refused; rotation and
   reverse still work, at escape duty.
7. **Pull the UART cable while driving.** The wheels must stop within 300 ms
   and `COMM_LOST` must latch. This is the single most important test here — it
   is the one the old firmware failed, and the reason a wedged Pi used to mean
   a robot that kept going.
8. Reconnect. `COMM_LOST` clears, and the wheels stay stopped until a new
   `CMD_DRIVE` arrives. A keepalive alone must never restart motion.
