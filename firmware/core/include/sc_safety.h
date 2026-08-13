/*
 * Smart Car motion-safety state machine -- portable core.
 *
 * A direct transliteration of src/uart/safety.py, which is the tested
 * reference. Both are exercised by the same conformance vectors so the MCU and
 * the Pi cannot silently disagree about when the robot may move; see
 * src/tests/test_uart_safety.py and firmware/test/test_safety.c.
 *
 * Pure state machine: no I/O, no clock of its own, no allocation. Time is
 * passed in. Elapsed-time comparisons use unsigned subtraction, which stays
 * correct across the ~49.7 day uint32 millisecond wrap.
 *
 * This is the final authority on motion. The Pi's equivalent checks are
 * advisory only, because they are worthless in exactly the case that matters:
 * when the Pi is the component that failed.
 *
 * Copyright 2025-2026 Bura Kamal. SPDX-License-Identifier: Apache-2.0
 */
#ifndef SC_SAFETY_H
#define SC_SAFETY_H

#include <stdbool.h>
#include <stdint.h>

#include "sc_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Consecutive echo timeouts before a sensor is declared faulted. One dropped
 * echo is normal on an HC-SR04 -- soft or angled surfaces scatter the pulse --
 * so reacting to a single miss would make the robot undriveable. */
#define SC_SENSOR_FAULT_THRESHOLD 3u

typedef struct {
    uint16_t stop_mm;
    uint16_t warn_mm;
    int8_t   escape_duty;  /* manoeuvres that get us out of trouble */
    int8_t   warn_duty;    /* forward ceiling inside the warning band */
    int8_t   reverse_duty; /* no rear sensor exists: capped at all times */
    uint32_t command_timeout_ms;
} sc_limits_t;

typedef struct {
    int8_t          left;
    int8_t          right;
    sc_ack_status_t status;
} sc_decision_t;

typedef struct {
    sc_limits_t limits;
    uint8_t     timeouts[3];
    uint16_t    distance_mm[3]; /* SC_DISTANCE_FAULT when unusable */
    uint16_t    faults;
    int8_t      applied_left;
    int8_t      applied_right;
    uint32_t    last_frame_ms;
    bool        have_frame;
} sc_safety_t;

/* Defaults matching the thresholds the working ESP32 build used (10 cm stop,
 * 20 cm warn), expressed in millimetres. */
void sc_limits_defaults(sc_limits_t *limits);

void sc_safety_init(sc_safety_t *s, const sc_limits_t *limits);

/* Feed one sensor sweep. Use SC_DISTANCE_FAULT for an echo timeout. */
void sc_safety_update_sensors(sc_safety_t *s, const uint16_t readings_mm[3]);

/* Renew the motion lease. Any well-formed, CRC-valid frame counts. */
void sc_safety_on_valid_frame(sc_safety_t *s, uint32_t now_ms);

/* Evaluate a requested duty pair against the current sensor picture. */
sc_decision_t sc_safety_request_drive(sc_safety_t *s, int8_t left, int8_t right);

/* Clear obstacle state, but only after re-reading the sensors. */
sc_ack_status_t sc_safety_request_clear_fault(sc_safety_t *s);

/* Enforce the motion lease. Call every loop iteration. Returns the duty that
 * should now be applied to the motors. */
sc_decision_t sc_safety_tick(sc_safety_t *s, uint32_t now_ms);

/* True when every sensor is faulted. Treated as an obstacle, never as clear
 * road -- the inversion this whole module exists to prevent. */
bool sc_safety_blind(const sc_safety_t *s);

/* Closest working sensor. Returns SC_DISTANCE_FAULT when blind. */
uint16_t sc_safety_min_distance(const sc_safety_t *s);

/* Live flag bits for telemetry (SC_FLAG_*). */
uint8_t sc_safety_flags(const sc_safety_t *s);

#ifdef __cplusplus
}
#endif

#endif /* SC_SAFETY_H */
