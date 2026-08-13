/*
 * Motor and servo drivers (LEDC PWM).
 * Copyright 2025-2026 Bura Kamal. SPDX-License-Identifier: Apache-2.0
 */
#ifndef DRV_ACTUATORS_H
#define DRV_ACTUATORS_H

#include <stdint.h>

void drv_actuators_init(void);

/* Apply signed duty per side, -100..100. Zero brakes rather than coasts: a
 * safety stop has to actually stop, and coasting a loaded chassis takes
 * noticeably longer.
 *
 * The previous firmware had no PWM at all -- every motion ran at 100% duty and
 * "stop" was a coast -- so the speed argument it accepted was discarded. */
void drv_motor_set(int8_t left_pct, int8_t right_pct);

/* Force both sides to brake immediately, bypassing any ramping. */
void drv_motor_brake(void);

void drv_servo_set(uint8_t degrees);
uint8_t drv_servo_get(void);

#endif /* DRV_ACTUATORS_H */
