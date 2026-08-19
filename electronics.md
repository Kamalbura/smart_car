# Smart Car electronics

This document records the Version 1 hardware that was built and the direction
for Version 2. It is a build record, not a substitute for checking voltages,
polarity, current capability, and temperatures on the physical robot before
powering it.

## Version 1 build

| Area | Component / implementation |
|---|---|
| Chassis and drive | [4WD BO-motor chassis](https://www.amazon.in/Chassis-Robotics-Projects-Compatible-Clearance/dp/B0FBLGCKB6) with an L298N dual H-bridge. The two motors on each side are treated as one left/right drive channel. |
| Main computer | Raspberry Pi 4, 8 GB RAM, in a [dual-fan aluminium heatsink case](https://robu.in/product/aluminum-heat-sink-case-with-double-fans-for-raspberry-pi-4b-black/). The build has been operated at 2 GHz; this is an overclock, not a guaranteed configuration. |
| Motor/safety MCU | ESP32-WROOM-32 on a custom PCB for the motor, sensor, and control wiring. |
| Motor driver | [L298N dual H-bridge](https://robu.in/product/l298n-dual-h-bridge-dc-stepper-motor-driver-controller-module/). |
| Distance sensing | Three [HC-SR04 ultrasonic sensors](https://robu.in/product/hc-sr04-ultrasonic-range-finder/). |
| Vision | Simple 5 MP Raspberry Pi camera; the exact camera module revision is not recorded. |
| UI | 2.5-inch Adafruit display for status and face output, plus an 8-pixel WS2812/NeoPixel circular board for facial/status lighting. |
| Audio | USB sound card for microphone input and speaker output; PAM8403 class-D amplifier and speaker. |
| Power | Two 2S battery packs, each with its own 10 A 2S BMS and TP5100 2S charge board. Charging input is a 9 V PD-decoy module supplied by a USB-PD charger (up to 9 V × 3 A = 27 W available at the charger). |

The 8-pixel LED board is represented by the supplied [WS2812 circular-board
listing](https://robu.in/product/8bit-ws2812-5050-rgb-led-built-full-color-driving-lights-circular-development-board/).

## Power and grounding

The reported build uses common ground between the Raspberry Pi, ESP32, motor
driver, audio chain, sensors, and power rails. Keep high-current motor return
paths physically separate from Pi and audio return paths until the common/star
ground point; do not use thin signal ground wires as motor-current returns.

The power rails include a capacitor array at the rail connection:

- 1000 uF bulk capacitor for motor/load transients;
- 1 uF high-frequency bypass capacitor; and
- 0.11 uF local bypass capacitor (recorded value; confirm the printed marking
  before replacing it).

The PAM8403 is reported as powered from the L298N board’s 5 V output. Verify
that output’s current rating and thermal behaviour with the amplifier active;
use a separately regulated 5 V rail if it is not sufficient. The Pi requires a
stable, regulated 5 V supply sized for the Pi, USB sound card, display, camera,
and cooling load. A 27 W PD source is not by itself a guarantee that every
downstream rail and charger is correctly rated.

**Battery/charging safety:** the exact relationship between the two 2S packs
(separate loads, parallel, or another topology) is not recorded here. Do not
directly parallel independent protected packs or BMS outputs unless the cells,
state of charge, BMS documentation, fusing, and wiring have been reviewed.
Use one correctly configured TP5100/BMS path per pack, appropriate fusing, and
charge only under supervision on a non-flammable surface.

## Verified code-to-wiring map

The active ESP-IDF firmware map is in
[`firmware/port/esp32/main/board.h`](firmware/port/esp32/main/board.h). The
legacy Arduino sketch in [`src/uart/esp-code.ino`](src/uart/esp-code.ino) uses
the same assignments.

| Function | ESP32 pin | Notes |
|---|---:|---|
| Sonar 1 trigger / echo | GPIO 4 / 5 | HC-SR04 front-facing sensor |
| Sonar 2 trigger / echo | GPIO 18 / 19 | HC-SR04 front-facing sensor |
| Sonar 3 trigger / echo | GPIO 21 / 22 | HC-SR04 front-facing sensor |
| Gas-sensor analogue input | GPIO 34 / ADC1_CH6 | Firmware records a raw value; it identifies the fitted part as MQ-3. |
| Servo signal | GPIO 23 | 50 Hz servo PWM |
| Left motor input 1 / 2 | GPIO 25 / 26 | L298N channel input |
| Right motor input 1 / 2 | GPIO 27 / 14 | L298N channel input |
| Pi-to-ESP32 UART | ESP32 RX GPIO 16, TX GPIO 17 | UART2, 115200 baud |

Connect UART lines crossed (Pi TX to ESP32 RX and Pi RX to ESP32 TX) and share
ground. Raspberry Pi and ESP32 UART I/O are both 3.3 V logic. HC-SR04 ECHO is
commonly 5 V, while ESP32 GPIO is not 5 V tolerant: each echo line needs a
verified level shifter or divider before reaching the ESP32.

The firmware assumes the L298N ENA/ENB jumpers are fitted and applies PWM to
the direction inputs. Check the L298N board’s logic-level behaviour with the
ESP32’s 3.3 V output and measure motor stall current with the actual paired
motors before relying on the 10 A BMS rating.

## Raspberry Pi configuration recorded by the repository

- The Pi-to-ESP32 serial device is `/dev/serial0` at 115200 baud in
  [`config/system.yaml`](config/system.yaml).
- The 5 MP camera is selected as camera index `0`; no camera-module revision
  or CSI pin change is defined in software.
- Audio expects a USB Audio input device and uses `smartcar_capture` for the
  microphone path. TTS playback is configured for `plughw:3,0`; enumerate ALSA
  devices on the target before relying on that card number.
- The LED service defaults to eight NeoPixels on `board.D12` at 25% brightness.
- The existing face program currently documents a 3.5-inch ILI9486/Waveshare
  framebuffer panel (`/dev/fb0`), not the stated 2.5-inch Adafruit display.
  Confirm the display driver, framebuffer, resolution, and wiring before
  changing any display configuration.

## Version 2: proposed work

Version 2 is a plan, not current hardware support:

- migrate the motion controller from ESP32 to an
  [STM32F103C8T6 Blue Pill](https://www.flyrobo.in/stm32f103c8t6-development-board-stm32-arm-core-module?search=stm32%20g474&description=true);
- replace BO motors with N20 geared 600 RPM motors with encoders for
  deterministic odometry and predictive control;
- design a 3D-printed chassis around the final battery, motor, sensor, and
  service-access layout;
- evaluate LangGraph for the model/orchestration layer; and
- replace the L298N after motor measurements.

### Motor-driver decision before Version 2

Do not select a new driver by module name alone. First measure the 2S supply
voltage under load and the stall current of one N20 motor, then multiply for
the actual left/right channel topology. Select a 3.3 V-logic-compatible driver
with continuous-current and thermal margin above that measured load, reverse,
brake/coast, and a known fault/overcurrent strategy.

TB6612FNG is a possible compact replacement only if the measured continuous
and peak current of each driven channel stays inside its ratings. If two motors
share a channel or the stall current is higher, use a driver sized per motor or
per side with adequate current margin and thermal design. The L298N is retained
for Version 1 but is inefficient and has a substantial voltage drop, making it
a poor default for a higher-performance encoded-drive upgrade.

No Version 2 driver, MCU, motor, or LangGraph change is implemented by this
document.
