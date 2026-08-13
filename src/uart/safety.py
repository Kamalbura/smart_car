"""Reference implementation of the motion-safety rules.

This is the executable specification for the MCU firmware. `firmware/src/
safety.c` is a direct transliteration of this module, and both are exercised by
the same conformance vectors, so the Pi and the MCU cannot silently disagree
about when motion is allowed.

It is a pure state machine: no I/O, no clock of its own, no hardware. Time is
passed in, which is what makes it testable on the host and mechanical to port
to C with no dynamic allocation.

Running it on the Pi as well is deliberate. `motor_bridge` and `orchestrator`
each grew their own partial copy of these rules, and the copies disagreed --
`_check_pi_side_safety` gated on the last telemetry frame with no staleness
check, so a dead MCU authorised forward motion forever. One tested
implementation replaces both, and lets the Pi predict a refusal instead of
discovering it from an ACK.

**The MCU remains the authority.** This module running on the Pi is advisory,
because Pi-side checks are worthless in exactly the case that matters: when the
Pi is the component that failed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from src.uart.protocol import COMMAND_TIMEOUT_MS, AckStatus, Fault

#: Consecutive echo timeouts before a sensor is declared faulted. One dropped
#: echo is normal on an HC-SR04 -- soft or angled surfaces scatter the pulse --
#: so reacting to a single miss would make the robot undriveable.
SENSOR_FAULT_THRESHOLD = 3


@dataclass(frozen=True)
class SafetyLimits:
    stop_mm: int = 100
    warn_mm: int = 200
    #: Duty permitted for manoeuvres that get us out of trouble.
    escape_duty_pct: int = 30
    #: Duty ceiling for forward motion inside the warning band.
    warn_duty_pct: int = 50
    #: Reverse has no sensor coverage on this chassis, so it is capped at all
    #: times rather than only when an obstacle is seen.
    reverse_duty_pct: int = 30
    command_timeout_ms: int = COMMAND_TIMEOUT_MS


@dataclass(frozen=True)
class Decision:
    left: int
    right: int
    status: AckStatus

    @property
    def moving(self) -> bool:
        return self.left != 0 or self.right != 0


def _clamp_magnitude(value: int, ceiling: int) -> int:
    """Limit speed without changing direction."""
    if value > ceiling:
        return ceiling
    if value < -ceiling:
        return -ceiling
    return value


class SafetyState:
    def __init__(self, limits: Optional[SafetyLimits] = None) -> None:
        self.limits = limits or SafetyLimits()
        self._timeouts: List[int] = [0, 0, 0]
        self._distance_mm: List[Optional[int]] = [None, None, None]
        self._faults = Fault.NONE
        self._applied: Tuple[int, int] = (0, 0)
        self._last_frame_ms: Optional[int] = None

    # -- observation ------------------------------------------------------

    def update_sensors(self, readings_mm: Sequence[Optional[int]]) -> None:
        """Feed one sweep. ``None`` means the echo timed out."""
        for index, reading in enumerate(readings_mm[:3]):
            if reading is None:
                self._timeouts[index] += 1
                if self._timeouts[index] >= SENSOR_FAULT_THRESHOLD:
                    self._distance_mm[index] = None
            else:
                self._timeouts[index] = 0
                self._distance_mm[index] = int(reading)
        self._recompute_sensor_faults()

    def _recompute_sensor_faults(self) -> None:
        bits = [Fault.SENSOR_1, Fault.SENSOR_2, Fault.SENSOR_3]
        for index, bit in enumerate(bits):
            if self._distance_mm[index] is None:
                self._faults |= bit
            else:
                self._faults &= ~bit
        if all(d is None for d in self._distance_mm):
            self._faults |= Fault.ALL_SENSORS_LOST
        else:
            self._faults &= ~Fault.ALL_SENSORS_LOST

    def on_valid_frame(self, now_ms: int) -> None:
        """Renew the motion lease. Any well-formed frame counts."""
        self._last_frame_ms = now_ms
        # Comms are demonstrably back. The stop the dropout caused still
        # stands -- duty stays where tick() left it -- but the operator should
        # not have to clear a fault that has already resolved itself.
        self._faults &= ~Fault.COMM_LOST

    # -- decisions --------------------------------------------------------

    @property
    def min_distance_mm(self) -> Optional[int]:
        working = [d for d in self._distance_mm if d is not None]
        return min(working) if working else None

    @property
    def blind(self) -> bool:
        return all(d is None for d in self._distance_mm)

    @property
    def faults(self) -> Fault:
        return self._faults

    @property
    def applied(self) -> Tuple[int, int]:
        return self._applied

    def request_drive(self, left: int, right: int) -> Decision:
        """Evaluate a requested duty pair against the current sensor picture."""
        left = _clamp_magnitude(int(left), 100)
        right = _clamp_magnitude(int(right), 100)

        if left == 0 and right == 0:
            return self._apply(Decision(0, 0, AckStatus.OK))

        # Blindness is treated as an obstacle at zero distance. The original
        # firmware did the opposite: three timed-out sensors produced a
        # sentinel 9999 that read as clear road and re-enabled the motors.
        distance = 0 if self.blind else self.min_distance_mm

        advancing = left > 0 and right > 0
        reversing = left < 0 and right < 0

        if reversing:
            # No rear sensor exists on this chassis, so reverse is permanently
            # capped rather than gated. Fitting one is the real fix.
            return self._apply(
                Decision(
                    _clamp_magnitude(left, self.limits.reverse_duty_pct),
                    _clamp_magnitude(right, self.limits.reverse_duty_pct),
                    AckStatus.CLAMPED,
                )
            )

        if distance <= self.limits.stop_mm:
            if advancing:
                return self._apply(Decision(0, 0, AckStatus.REFUSED_OBSTACLE))
            # Rotation stays available inside the stop zone at escape duty --
            # you have to be able to turn out of a corner. The old firmware
            # ran rotation at full duty here with no gate at all.
            return self._apply(
                Decision(
                    _clamp_magnitude(left, self.limits.escape_duty_pct),
                    _clamp_magnitude(right, self.limits.escape_duty_pct),
                    AckStatus.CLAMPED,
                )
            )

        if distance <= self.limits.warn_mm and advancing:
            return self._apply(
                Decision(
                    _clamp_magnitude(left, self.limits.warn_duty_pct),
                    _clamp_magnitude(right, self.limits.warn_duty_pct),
                    AckStatus.CLAMPED,
                )
            )

        return self._apply(Decision(left, right, AckStatus.OK))

    def request_clear_fault(self) -> AckStatus:
        """Clear obstacle state, but only after re-reading the sensors.

        The old ``CLEARBLOCK`` cleared its flags blind, so ``CLEARBLOCK`` then
        ``FORWARD`` drove into the wall until the next sweep re-latched roughly
        50-140 ms later, at full duty.
        """
        if self.blind:
            return AckStatus.REFUSED_FAULT
        distance = self.min_distance_mm
        if distance is not None and distance <= self.limits.stop_mm:
            return AckStatus.REFUSED_OBSTACLE
        self._faults = Fault.NONE
        self._recompute_sensor_faults()
        return AckStatus.OK

    def tick(self, now_ms: int) -> Decision:
        """Enforce the motion lease. Call every loop iteration.

        If no valid frame has arrived within ``command_timeout_ms``, the motors
        brake and ``COMM_LOST`` is raised. This is what makes a dead Pi, an
        unplugged cable or a stopped ``uart.service`` safe rather than fatal.
        """
        expired = (
            self._last_frame_ms is None
            or (now_ms - self._last_frame_ms) > self.limits.command_timeout_ms
        )
        if expired and self._applied != (0, 0):
            self._faults |= Fault.COMM_LOST
            return self._apply(Decision(0, 0, AckStatus.REFUSED_FAULT))
        if expired:
            self._faults |= Fault.COMM_LOST
        return Decision(self._applied[0], self._applied[1], AckStatus.OK)

    def _apply(self, decision: Decision) -> Decision:
        self._applied = (decision.left, decision.right)
        return decision
