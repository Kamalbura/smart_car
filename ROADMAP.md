# Smart Car roadmap

This roadmap separates planned work from the Version 1 implementation. Nothing
listed here is a commitment or current hardware behaviour until it is designed,
tested, and documented.

## Version 1: stabilize and document

- Complete bench and floor validation of the MCU safety firmware before relying
  on its motion-lease and fail-closed behaviour.
- Keep the ESP32 pin map, power architecture, and installation instructions in
  sync with the physical robot.
- Record exact part revisions, display driver, camera revision, battery-pack
  topology, fuse ratings, and supplier information in
  [electronics.md](electronics.md).
- Create a reproducible dependency and model inventory for release builds.
- Add hardware test evidence for motor stop time, UART-loss behaviour, sensor
  faults, battery voltage sag, and thermal limits.
- Complete the app-to-Pi transport rollout: require HTTPS, distribute and trust
  the robot certificate safely, keep bearer-token authentication, and prove
  that the app cannot fall back to cleartext HTTP.

## Version 2: drive and control

1. **Measure before selecting hardware.** Measure N20 motor voltage, no-load
   current, stall current, gearbox speed, encoder pulses per revolution, and
   the current of every motor sharing a driver channel.
2. **Replace the drive system.** Move from BO motors to 600 RPM N20 geared
   motors with encoders. Choose a motor driver only after the measurements;
   TB6612FNG is suitable only when its per-channel current and thermal limits
   cover the real load with margin.
3. **Move the safety controller.** Evaluate STM32F103C8T6 (Blue Pill) for the
   safety/control MCU. Port the protocol, deadman, sensor handling, and test
   vectors before connecting motors.
4. **Add deterministic motion feedback.** Use encoder data for odometry,
   closed-loop speed control, bounded acceleration, stopping-distance logic,
   and predictive obstacle response.
5. **Redesign the chassis.** Create a 3D-printed chassis with protected cable
   routing, accessible charging, strain relief, cooling, service access, and a
   mechanically isolated sensor/camera mount.

## Version 2: interaction and intelligence

- Evaluate LangGraph for explicit, inspectable orchestration flows. Keep motion
  authority outside the model layer: an LLM may request motion, but safety
  firmware must remain able to refuse or stop it.
- Improve the status display and NeoPixel feedback so physical state, fault
  state, and cloud-service state are distinguishable.
- Reassess local versus cloud STT, TTS, vision, and LLM components with their
  latency, privacy, cost, and licence implications documented.

## Decision gates

Do not move a roadmap item into the implemented system until it has passed the
relevant gate:

| Change | Required evidence |
|---|---|
| New motor/driver | Measured stall current, thermal test, correct fuse/wire sizing, braking and stop-time test |
| New MCU | Protocol conformance tests, watchdog/deadman test, sensor-fault test, bench test with wheels off the ground |
| New battery/charger arrangement | Verified pack topology, BMS/charger compatibility, current limits, fuse placement, charge/thermal test |
| New display/camera | Confirmed driver/interface, power budget, boot and runtime test |
| New model/orchestration layer | Offline tests, failure behaviour, safety-boundary review, dependency and licence review |

## Non-goals

- Do not bypass the MCU safety layer for faster development.
- Do not treat a software simulation as proof of safe motor behaviour.
- Do not add model weights, account keys, proprietary SDK binaries, or
  unreviewed third-party assets to the repository.
