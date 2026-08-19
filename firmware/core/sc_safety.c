/*
 * Smart Car motion-safety state machine -- portable core.
 * Transliteration of src/uart/safety.py. Keep the two in step.
 * Copyright 2026 Kamal Bura
 * SPDX-License-Identifier: Apache-2.0
 */
#include "sc_safety.h"

#include <stddef.h>

void sc_limits_defaults(sc_limits_t *limits)
{
    if (limits == NULL) {
        return;
    }
    limits->stop_mm = 100u;
    limits->warn_mm = 200u;
    limits->escape_duty = 30;
    limits->warn_duty = 50;
    limits->reverse_duty = 30;
    limits->command_timeout_ms = SC_COMMAND_TIMEOUT_MS;
}

void sc_safety_init(sc_safety_t *s, const sc_limits_t *limits)
{
    uint8_t i;

    if (s == NULL) {
        return;
    }
    if (limits != NULL) {
        s->limits = *limits;
    } else {
        sc_limits_defaults(&s->limits);
    }
    for (i = 0u; i < 3u; i++) {
        s->timeouts[i] = 0u;
        s->distance_mm[i] = SC_DISTANCE_FAULT;
    }
    s->faults = SC_FAULT_NONE;
    s->applied_left = 0;
    s->applied_right = 0;
    s->last_frame_ms = 0u;
    s->have_frame = false;
}

/* Limit speed without changing direction. */
static int8_t sc__clamp_mag(int8_t value, int8_t ceiling)
{
    if (value > ceiling) {
        return ceiling;
    }
    if (value < (int8_t)(-ceiling)) {
        return (int8_t)(-ceiling);
    }
    return value;
}

static void sc__recompute_sensor_faults(sc_safety_t *s)
{
    static const uint16_t bits[3] = {
        SC_FAULT_SENSOR_1, SC_FAULT_SENSOR_2, SC_FAULT_SENSOR_3
    };
    uint8_t i;
    bool all_lost = true;

    for (i = 0u; i < 3u; i++) {
        if (s->distance_mm[i] == SC_DISTANCE_FAULT) {
            s->faults |= bits[i];
        } else {
            s->faults &= (uint16_t)(~bits[i]);
            all_lost = false;
        }
    }
    if (all_lost) {
        s->faults |= SC_FAULT_ALL_SENSORS_LOST;
    } else {
        s->faults &= (uint16_t)(~SC_FAULT_ALL_SENSORS_LOST);
    }
}

void sc_safety_update_sensors(sc_safety_t *s, const uint16_t readings_mm[3])
{
    uint8_t i;

    if ((s == NULL) || (readings_mm == NULL)) {
        return;
    }
    for (i = 0u; i < 3u; i++) {
        if (readings_mm[i] == SC_DISTANCE_FAULT) {
            if (s->timeouts[i] < 0xFFu) {
                s->timeouts[i]++;
            }
            if (s->timeouts[i] >= SC_SENSOR_FAULT_THRESHOLD) {
                s->distance_mm[i] = SC_DISTANCE_FAULT;
            }
        } else {
            s->timeouts[i] = 0u;
            s->distance_mm[i] = readings_mm[i];
        }
    }
    sc__recompute_sensor_faults(s);
}

void sc_safety_on_valid_frame(sc_safety_t *s, uint32_t now_ms)
{
    if (s == NULL) {
        return;
    }
    s->last_frame_ms = now_ms;
    s->have_frame = true;
    /* Comms are demonstrably back. The stop the dropout caused still stands --
     * duty stays where tick() left it -- but the operator should not have to
     * clear a fault that has already resolved itself. */
    s->faults &= (uint16_t)(~SC_FAULT_COMM_LOST);
}

bool sc_safety_blind(const sc_safety_t *s)
{
    uint8_t i;

    if (s == NULL) {
        return true;
    }
    for (i = 0u; i < 3u; i++) {
        if (s->distance_mm[i] != SC_DISTANCE_FAULT) {
            return false;
        }
    }
    return true;
}

uint16_t sc_safety_min_distance(const sc_safety_t *s)
{
    uint16_t best = SC_DISTANCE_FAULT;
    uint8_t i;

    if (s == NULL) {
        return SC_DISTANCE_FAULT;
    }
    for (i = 0u; i < 3u; i++) {
        if (s->distance_mm[i] == SC_DISTANCE_FAULT) {
            continue;
        }
        if ((best == SC_DISTANCE_FAULT) || (s->distance_mm[i] < best)) {
            best = s->distance_mm[i];
        }
    }
    return best;
}

static sc_decision_t sc__apply(sc_safety_t *s, int8_t left, int8_t right,
                               sc_ack_status_t status)
{
    sc_decision_t d;

    s->applied_left = left;
    s->applied_right = right;
    d.left = left;
    d.right = right;
    d.status = status;
    return d;
}

sc_decision_t sc_safety_request_drive(sc_safety_t *s, int8_t left, int8_t right)
{
    uint16_t distance;
    bool advancing;
    bool reversing;

    left = sc__clamp_mag(left, 100);
    right = sc__clamp_mag(right, 100);

    if ((left == 0) && (right == 0)) {
        return sc__apply(s, 0, 0, SC_ACK_OK);
    }

    /* Blindness is treated as an obstacle at zero distance. The original
     * firmware did the opposite: three timed-out sensors produced a sentinel
     * 9999 that read as clear road and re-enabled the motors. */
    distance = sc_safety_blind(s) ? 0u : sc_safety_min_distance(s);

    advancing = (left > 0) && (right > 0);
    reversing = (left < 0) && (right < 0);

    if (reversing) {
        /* No rear sensor on this chassis, so reverse is permanently capped
         * rather than gated. Fitting one is the real fix. */
        return sc__apply(s,
                         sc__clamp_mag(left, s->limits.reverse_duty),
                         sc__clamp_mag(right, s->limits.reverse_duty),
                         SC_ACK_CLAMPED);
    }

    if (distance <= s->limits.stop_mm) {
        if (advancing) {
            return sc__apply(s, 0, 0, SC_ACK_REFUSED_OBSTACLE);
        }
        /* Rotation stays available inside the stop zone at escape duty -- you
         * have to be able to turn out of a corner. The old firmware ran
         * rotation at full duty here with no gate at all. */
        return sc__apply(s,
                         sc__clamp_mag(left, s->limits.escape_duty),
                         sc__clamp_mag(right, s->limits.escape_duty),
                         SC_ACK_CLAMPED);
    }

    if ((distance <= s->limits.warn_mm) && advancing) {
        return sc__apply(s,
                         sc__clamp_mag(left, s->limits.warn_duty),
                         sc__clamp_mag(right, s->limits.warn_duty),
                         SC_ACK_CLAMPED);
    }

    return sc__apply(s, left, right, SC_ACK_OK);
}

sc_ack_status_t sc_safety_request_clear_fault(sc_safety_t *s)
{
    uint16_t distance;

    if (s == NULL) {
        return SC_ACK_REFUSED_FAULT;
    }
    /* The old CLEARBLOCK cleared its flags blind, so CLEARBLOCK then FORWARD
     * drove into the wall until the next sweep re-latched 50-140 ms later, at
     * full duty. */
    if (sc_safety_blind(s)) {
        return SC_ACK_REFUSED_FAULT;
    }
    distance = sc_safety_min_distance(s);
    if (distance <= s->limits.stop_mm) {
        return SC_ACK_REFUSED_OBSTACLE;
    }
    s->faults = SC_FAULT_NONE;
    sc__recompute_sensor_faults(s);
    return SC_ACK_OK;
}

sc_decision_t sc_safety_tick(sc_safety_t *s, uint32_t now_ms)
{
    sc_decision_t d;
    bool expired;

    /* Unsigned subtraction keeps this correct across the uint32 ms wrap. */
    expired = (!s->have_frame) ||
              ((uint32_t)(now_ms - s->last_frame_ms) > s->limits.command_timeout_ms);

    if (expired) {
        s->faults |= SC_FAULT_COMM_LOST;
        if ((s->applied_left != 0) || (s->applied_right != 0)) {
            /* This is what makes an unplugged cable, a crashed orchestrator
             * and `systemctl stop uart` safe rather than fatal: they all reach
             * the MCU as the same thing, silence. */
            return sc__apply(s, 0, 0, SC_ACK_REFUSED_FAULT);
        }
    }

    d.left = s->applied_left;
    d.right = s->applied_right;
    d.status = SC_ACK_OK;
    return d;
}

uint8_t sc_safety_flags(const sc_safety_t *s)
{
    uint8_t flags = 0u;
    uint16_t distance;

    if (s == NULL) {
        return 0u;
    }
    flags |= SC_FLAG_ARMED;
    if ((s->applied_left != 0) || (s->applied_right != 0)) {
        flags |= SC_FLAG_MOVING;
    }
    distance = sc_safety_blind(s) ? 0u : sc_safety_min_distance(s);
    if (distance <= s->limits.stop_mm) {
        flags |= SC_FLAG_OBSTACLE;
    }
    if (distance <= s->limits.warn_mm) {
        flags |= SC_FLAG_WARNING;
    }
    return flags;
}
