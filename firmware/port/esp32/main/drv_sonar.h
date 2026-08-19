/*
 * Non-blocking HC-SR04 driver.
 *
 * Echo width is captured by a GPIO edge interrupt rather than pulseIn(), so
 * the control loop is never blocked. The previous firmware spent up to 90 ms
 * per iteration inside three back-to-back blocking pulseIn() calls, before it
 * had even looked at the serial port for a STOP command.
 *
 * Sensors are triggered round-robin, one per slot, so a sensor never hears
 * another's ping. Firing them back-to-back is the usual source of phantom
 * short readings on a three-sensor array.
 *
* Copyright 2026 Kamal Bura
* SPDX-License-Identifier: Apache-2.0
 */
#ifndef DRV_SONAR_H
#define DRV_SONAR_H

#include <stdbool.h>
#include <stdint.h>

#include "board.h"

void drv_sonar_init(void);

/* Advance the round-robin. Call every control-loop tick. */
void drv_sonar_tick(void);

/* True once per completed sweep of all sensors, copying the results out.
 *
 * The safety layer must only be fed on a real sweep boundary: its
 * consecutive-timeout counter is what distinguishes a single scattered echo
 * from a genuinely dead sensor, and feeding it the same stale reading every
 * 10 ms would collapse that distinction. */
bool drv_sonar_sweep_ready(uint16_t out_mm[BOARD_SONAR_COUNT]);

/* Latest value per sensor, readable at any time (for telemetry).
 * SC_DISTANCE_FAULT means that sensor did not answer. */
void drv_sonar_read(uint16_t out_mm[BOARD_SONAR_COUNT]);

#endif /* DRV_SONAR_H */
