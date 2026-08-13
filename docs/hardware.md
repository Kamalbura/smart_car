# Hardware — as actually built

Authoritative. Recorded from the builder, and it supersedes every other
hardware description in this repository. Where the code or older docs disagree,
they are wrong and the disagreement is called out below.

## Bill of materials

| Subsystem | Part | Notes |
|---|---|---|
| Compute | Raspberry Pi 4 Model B, 8 GB | Aluminium heatsink case with fans, stable OC to 2.0 GHz |
| Motion MCU | ESP32-WROOM-32, **30-pin** devkit | UART2 to the Pi |
| Motor driver | **1×** L298N | Both sides on one board |
| Motors | 4× BO gear motors | Left pair ganged to channel A, right pair to channel B |
| Chassis | 4WD wooden kit car chassis | [Kit2Create smart wooden chassis](https://www.amazon.in/dp/B08WHQTMKQ) |
| Camera | 5 MP CSI module | OV5647 sensor |
| Distance | 3× HC-SR04 | All front-facing, no rear coverage |
| Gas | **MQ-3 (alcohol)** | Not MQ2 — see corrections |
| Servo | Hobby servo on GPIO23 | Attached and centred; not currently swept |
| Display | Waveshare 3.5" SPI (ILI9486) | Migration planned — see below |
| LEDs | 8× WS2812B ring, GPIO12 | Needs root for bit-bang timing |
| Audio in | USB sound card + soldered omnidirectional electret | Chosen for sensitivity |
| Audio out | PAM8403 class-D amp, dual speaker box | Fed from the USB card's line out |

## Power

Two independent packs, which is the part most worth understanding.

Both packs are 2S Li-ion behind their own **10 A 2S BMS**.

**Drive pack** — DMEGC 2400 mAh, 3C. Feeds the L298N directly at pack voltage.
3C × 2.4 Ah gives about 7 A available; four BO motors at simultaneous stall
draw roughly 3–4 A, so there is comfortable headroom and the BMS is correctly
sized to trip before the cells are abused.

**Logic pack** — 3000 mAh, 3C → XL-series 5 A buck converter → 5 V rail for the
Pi and peripherals. About 9 A available against a real draw nearer 2 A from the
pack (Pi 4 under load, display, LED ring, amplifier, through the buck), so the
BMS here is oversized and will never be the limiting factor — which is fine,
and means it contributes no heat.

The two packs give broadly similar runtime, on the order of an hour and a half
each, which is the right way to size them: neither subsystem strands the other
by dying first.

**Separating the packs is the most important decision in this design.** A
motor stall cannot sag the Pi's rail, because they do not share one. That, plus
the capacitor stack below, is why the Pi survives a hard turn. Keeping the
grounds common while keeping the positives separate is exactly right.

**Charging** — 12 V 3 A adapter → step-down to 9 V → TP5100 2S charger. The
TP5100 needs headroom above the 8.4 V full-charge voltage, which is why the
adapter is stepped to 9 V rather than used directly.

**Bulk decoupling** — a 1000 µF / 470 µF / 100 µF / 0.1 µF stack in parallel
across the supply. The descending values are deliberate: large electrolytics
have too much ESL and ESR to answer fast transients, so each smaller capacitor
covers a higher frequency band than the one before it. This is what absorbs the
current step when four motors start or stall, and it is the reason the Pi does
not brown out on a hard turn.

**Grounding** — all grounds common, which is mandatory for the 3.3 V UART
between the Pi and the ESP32 to have a shared reference.

The speaker amplifier originally ran from its own 1S cell and has since been
moved onto the shared 5 V rail.

## Corrections to the rest of the repo

| Claim elsewhere | Reality |
|---|---|
| `MQ2` gas sensor (code, `board.h`, `esp-code.ino`) | **MQ-3**, an alcohol sensor. The pin and ADC read are identical, so it works electrically, but the label is wrong and any threshold tuned for smoke/LPG is meaningless. `book/mbook.tex` had this right. |
| "12 V Li-Ion drive rail" (`book/chapters/02_hardware.tex`) | The drive pack is **2S — 7.4 V nominal, 8.4 V full**. 12 V appears only as the charger's input, before the step-down to 9 V. |
| 2× L298N for 4 motors (`docs/08_embedded_esp32_layer.md`) | **One**, with two motors ganged per channel. |
| "two drive wheels plus casters" (`book/chapters/01_overview.tex`) | Four driven wheels. |
| "Capacitor bank (not implemented)" (`book/chapters/14_limitations.tex`) | Implemented — see the stack above. |
| Camera "assumed v2 / IMX219" (`docs/12_known_unknowns.md`) | 5 MP module, i.e. **OV5647**. |
| SSD1306 OLED, 16-LED ring on GPIO18, `/dev/ttyUSB0` (`docs/08_*`, `docs/05_*`) | None of these exist. That document describes a different robot. |

## Engineering notes on the current build

**The L298N is the weakest link.** Its Darlington output stage drops roughly
1.8–2 V. At a 7.4 V pack the motors see about 5.5 V, so you lose a quarter of
your pack voltage as heat in the driver. Two BO motors per channel at stall is
also close to the L298N's ~2 A continuous rating, so a stalled wheel will drive
it into thermal shutdown.

A TB6612FNG or DRV8833 is a drop-in-ish MOSFET replacement dropping ~0.3 V
instead of ~2 V. That is more torque, less heat, and longer runtime from the
same pack, for about the same money. It is the single highest-value hardware
change available.

**The L298N's 5 V regulator is the thinnest margin in the build.** The audio
amplifier is fed from it, and the amp's switching noise was cured by adding a
small decoupling capacitor at the amp — the correct fix, and better than piling
more bulk capacitance at the Pi.

The arithmetic is worth knowing, because it works today with little to spare.
The onboard regulator on an L298N board is usually a 78M05 rated 500 mA (some
boards fit a 1 A 7805). Against that:

| Load | Typical | Worst case |
|---|---|---|
| PAM8403, moderate volume | 200–400 mA | ~1 A at full tilt into 4 Ω |
| 8× WS2812B at brightness 0.25 | 100–150 mA | 480 mA at full-white |

Typical combined draw already sits near the 500 mA rating, and both peaks
coincide exactly when you would least want them to — a loud alert with the ring
lit. The regulator is also dropping 7.4 V to 5 V, so at 500 mA it dissipates
about 1.2 W into a TO-220 with almost no heatsinking.

The second-order problem is that this rail is fed from the **drive** pack, which
partly undoes the pack separation described above: a motor stall sags it, and
the amp and LEDs are the first things to misbehave.

Moving the NeoPixel ring (and ideally the amp) onto the Pi's 5 V rail is the
fix. That rail has a 5 A buck behind a 9 A pack and only ~3 A of Pi to feed, so
it has genuine headroom, and the grounds are already common so it costs one
wire. Whatever else changes, keep the **ESP32** off the L298N regulator: a
brownout there resets the safety controller at exactly the moment it matters,
and the currently-flashed Arduino sketch reports nothing when that happens. The
newer firmware at least announces it with `EVT_BOOT` and brakes within 300 ms.

**No rear sensor.** All three ultrasonics face forward, which is why reverse is
permanently speed-capped in the safety layer rather than gated — the firmware
cannot see behind it. A fourth HC-SR04 at the back is cheap and would let
reverse be gated like every other direction.

**No wheel encoders.** This is the blocker for autonomy, not compute or the
model. Without them every motion is open-loop and unbounded: "forward" means
"forward until something else happens", and `duration_ms` is parsed and thrown
away. Encoders plus an IMU turn that into "forward 50 cm", executed closed-loop
on the MCU.

**PAM8403 now shares the 5 V rail.** Class-D amplifiers inject switching noise
into their supply, and that rail is shared with the Pi and a USB sound card. If
you hear a whine that changes with motor load, an LC filter or a dedicated
feed for the amp is the fix, not more capacitance at the Pi.

## Display migration

The Waveshare 3.5" SPI panel is the bottleneck it feels like. 480×320 at 16 bpp
is ~307 kB per frame; even at a 32 MHz SPI clock that caps you near 10 fps
before any drawing, and it consumes SPI0 plus several GPIOs.

Three options, in the order I would consider them for a battery robot:

**DSI (recommended).** An official 7", or a smaller 4.3" DSI panel. Uses the
dedicated ribbon connector, so SPI0 and its GPIOs come free, and it draws from
the Pi's own 5 V without another cable. Best mechanical fit on a moving chassis
— no rigid HDMI cable to fatigue.

**HDMI.** Fastest to get working and the best framerate, but most small HDMI
panels want their own 5 V feed, and a full-size HDMI cable on a robot that
turns in place is a genuine reliability problem. Use a right-angle micro-HDMI
adapter if you go this way.

**Keep SPI, change the driver.** If the current panel is fine mechanically and
only the framerate hurts, a DMA-accelerated driver of the `fbcp-ili9341` family
gets an ILI9486 to roughly 30 fps. Zero hardware change.

Given the display shows a face and status rather than video, DSI is the right
call: it frees the SPI bus, survives vibration better, and is a single ribbon.
