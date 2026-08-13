"""Conformance vectors for the motion-safety state machine.

Every test here is also the acceptance test for `firmware/src/safety.c`. If the
C transliteration disagrees with any of these, the MCU and the Pi have diverged
about when the robot is allowed to move.

Several cases are named for the original firmware defect they lock out.
"""
from __future__ import annotations

import pytest

from src.uart.protocol import AckStatus, Fault
from src.uart.safety import SENSOR_FAULT_THRESHOLD, SafetyLimits, SafetyState

CLEAR = [2000, 2000, 2000]
WARN = [150, 2000, 2000]
BLOCKED = [50, 2000, 2000]


@pytest.fixture
def state():
    s = SafetyState(SafetyLimits())
    s.update_sensors(CLEAR)
    s.on_valid_frame(0)
    return s


# ---------------------------------------------------------------------------
# Normal operation
# ---------------------------------------------------------------------------

def test_clear_road_allows_full_duty(state):
    d = state.request_drive(100, 100)
    assert (d.left, d.right, d.status) == (100, 100, AckStatus.OK)


def test_stop_is_always_accepted(state):
    state.update_sensors(BLOCKED)
    d = state.request_drive(0, 0)
    assert (d.left, d.right, d.status) == (0, 0, AckStatus.OK)


def test_duty_is_clamped_to_the_legal_range(state):
    d = state.request_drive(999, -999)
    assert abs(d.left) <= 100 and abs(d.right) <= 100


# ---------------------------------------------------------------------------
# Obstacle gating
# ---------------------------------------------------------------------------

def test_forward_is_refused_inside_the_stop_zone(state):
    state.update_sensors(BLOCKED)
    d = state.request_drive(100, 100)
    assert (d.left, d.right) == (0, 0)
    assert d.status is AckStatus.REFUSED_OBSTACLE


def test_forward_is_throttled_in_the_warning_band(state):
    state.update_sensors(WARN)
    d = state.request_drive(100, 100)
    assert d.status is AckStatus.CLAMPED
    assert d.left == state.limits.warn_duty_pct


def test_rotation_survives_inside_the_stop_zone_but_slowly(state):
    """You must be able to turn out of a corner.

    The old firmware consulted its obstacle flags only in the FORWARD branch,
    so rotation ran at full duty at zero distance. Gating it entirely would be
    equally wrong -- the robot would be trapped.
    """
    state.update_sensors(BLOCKED)
    d = state.request_drive(-100, 100)
    assert d.status is AckStatus.CLAMPED
    assert (d.left, d.right) == (-state.limits.escape_duty_pct, state.limits.escape_duty_pct)


def test_reverse_is_capped_even_on_a_clear_road(state):
    """There is no rear sensor, so reverse is blind at every distance."""
    d = state.request_drive(-100, -100)
    assert d.status is AckStatus.CLAMPED
    assert d.left == -state.limits.reverse_duty_pct


def test_reverse_is_permitted_inside_the_stop_zone(state):
    # The front sensors say blocked; backing away must remain possible.
    state.update_sensors(BLOCKED)
    d = state.request_drive(-100, -100)
    assert d.moving is True
    assert d.left < 0


# ---------------------------------------------------------------------------
# Sensors fail closed
# ---------------------------------------------------------------------------

def test_a_single_dropped_echo_is_tolerated(state):
    """One miss is normal on an HC-SR04; reacting to it makes the robot
    undriveable."""
    state.update_sensors([None, 2000, 2000])
    assert state.request_drive(100, 100).status is AckStatus.OK
    assert Fault.SENSOR_1 not in state.faults


def test_a_sensor_faults_after_repeated_timeouts(state):
    for _ in range(SENSOR_FAULT_THRESHOLD):
        state.update_sensors([None, 2000, 2000])
    assert Fault.SENSOR_1 in state.faults
    # The other two still see a clear road, so motion continues.
    assert state.request_drive(100, 100).status is AckStatus.OK


def test_a_recovered_sensor_clears_its_fault(state):
    for _ in range(SENSOR_FAULT_THRESHOLD):
        state.update_sensors([None, 2000, 2000])
    assert Fault.SENSOR_1 in state.faults
    state.update_sensors(CLEAR)
    assert Fault.SENSOR_1 not in state.faults


def test_total_sensor_loss_blocks_forward_motion(state):
    """The headline inversion: no reading used to mean clear road.

    Unplug all three sensors on the old firmware and minDist stayed 9999, which
    took the CLEAR branch and re-enabled the motors.
    """
    for _ in range(SENSOR_FAULT_THRESHOLD):
        state.update_sensors([None, None, None])

    assert state.blind is True
    assert Fault.ALL_SENSORS_LOST in state.faults
    d = state.request_drive(100, 100)
    assert (d.left, d.right) == (0, 0)
    assert d.status is AckStatus.REFUSED_OBSTACLE


def test_blind_still_allows_escape_manoeuvres(state):
    for _ in range(SENSOR_FAULT_THRESHOLD):
        state.update_sensors([None, None, None])
    assert state.request_drive(-100, 100).moving is True


# ---------------------------------------------------------------------------
# The motion lease
# ---------------------------------------------------------------------------

def test_motion_persists_while_the_lease_is_renewed(state):
    state.request_drive(100, 100)
    for now in range(0, 5000, 50):
        state.on_valid_frame(now)
        assert state.tick(now).moving is True


def test_motion_stops_when_the_lease_expires(state):
    state.request_drive(100, 100)
    state.on_valid_frame(1000)

    assert state.tick(1000 + state.limits.command_timeout_ms).moving is True
    d = state.tick(1000 + state.limits.command_timeout_ms + 1)

    assert (d.left, d.right) == (0, 0)
    assert Fault.COMM_LOST in state.faults


def test_lease_expiry_is_what_makes_a_dead_pi_safe(state):
    """Unplugged cable, crashed orchestrator, `systemctl stop uart` -- all
    reach the MCU as the same thing: silence."""
    state.request_drive(100, 100)
    state.on_valid_frame(0)
    # The Pi never speaks again.
    assert state.tick(10_000).moving is False


def test_comm_loss_clears_when_frames_return(state):
    state.request_drive(100, 100)
    state.on_valid_frame(0)
    state.tick(10_000)
    assert Fault.COMM_LOST in state.faults

    state.on_valid_frame(10_050)
    assert Fault.COMM_LOST not in state.faults


def test_recovered_comms_do_not_resume_motion_by_themselves(state):
    """A keepalive must never restart a robot the deadman stopped.

    Renewing the lease proves the link is back; it is not a motion command.
    """
    state.request_drive(100, 100)
    state.on_valid_frame(0)
    state.tick(10_000)

    state.on_valid_frame(10_050)
    assert state.tick(10_060).moving is False


def test_no_frame_ever_received_means_no_motion(state):
    fresh = SafetyState()
    fresh.update_sensors(CLEAR)
    fresh.request_drive(100, 100)
    assert fresh.tick(0).moving is False


# ---------------------------------------------------------------------------
# Clearing faults
# ---------------------------------------------------------------------------

def test_clear_fault_is_refused_while_an_obstacle_is_present(state):
    """The CLEARBLOCK bug: clearing blind, then driving into the wall."""
    state.update_sensors(BLOCKED)
    assert state.request_clear_fault() is AckStatus.REFUSED_OBSTACLE
    assert state.request_drive(100, 100).status is AckStatus.REFUSED_OBSTACLE


def test_clear_fault_is_refused_while_blind(state):
    for _ in range(SENSOR_FAULT_THRESHOLD):
        state.update_sensors([None, None, None])
    assert state.request_clear_fault() is AckStatus.REFUSED_FAULT


def test_clear_fault_succeeds_once_the_road_is_clear(state):
    state.update_sensors(BLOCKED)
    assert state.request_clear_fault() is AckStatus.REFUSED_OBSTACLE
    state.update_sensors(CLEAR)
    assert state.request_clear_fault() is AckStatus.OK
    assert state.faults == Fault.NONE
