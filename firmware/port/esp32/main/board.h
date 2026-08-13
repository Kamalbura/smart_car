/*
 * ESP32 board map.
 *
 * Pin assignments are carried over unchanged from the working Arduino sketch
 * (src/uart/esp-code.ino) so existing wiring is untouched. What changed is
 * everything above the pins: real PWM instead of latched GPIO, non-blocking
 * echo timing instead of pulseIn(), and a framed protocol with a deadman.
 *
 * Copyright 2025-2026 Bura Kamal. SPDX-License-Identifier: Apache-2.0
 */
#ifndef BOARD_H
#define BOARD_H

#include "driver/gpio.h"
#include "driver/uart.h"
#include "hal/adc_types.h"

/* Ultrasonics, all front-facing. There is no rear sensor on this chassis,
 * which is why reverse is permanently speed-capped in sc_safety. */
#define BOARD_SONAR_COUNT     3
#define BOARD_SONAR1_TRIG     GPIO_NUM_4
#define BOARD_SONAR1_ECHO     GPIO_NUM_5
#define BOARD_SONAR2_TRIG     GPIO_NUM_18
#define BOARD_SONAR2_ECHO     GPIO_NUM_19
#define BOARD_SONAR3_TRIG     GPIO_NUM_21
#define BOARD_SONAR3_ECHO     GPIO_NUM_22

/* Gas sensor on GPIO34 = ADC1 channel 6. Input-only pin, no pull-ups.
 *
 * The fitted part is an MQ-3 (alcohol), not the MQ2 (smoke/LPG) that older
 * comments and the legacy ASCII protocol claim. Electrically identical here --
 * one analog output into one ADC pin -- but the response curves are for
 * different gases, so a threshold tuned for smoke means nothing against
 * alcohol. This firmware reports the raw count and never interprets it. */
#define BOARD_GAS_ADC_UNIT    ADC_UNIT_1
#define BOARD_GAS_ADC_CHANNEL ADC_CHANNEL_6

#define BOARD_SERVO_PIN       GPIO_NUM_23
#define BOARD_SERVO_MIN_DEG   0
#define BOARD_SERVO_MAX_DEG   180
#define BOARD_SERVO_HOME_DEG  90

/* H-bridge inputs. ENA/ENB are jumpered high on this board, so PWM is applied
 * to the direction pins directly. */
#define BOARD_MOTOR_L_IN1     GPIO_NUM_25
#define BOARD_MOTOR_L_IN2     GPIO_NUM_26
#define BOARD_MOTOR_R_IN1     GPIO_NUM_27
#define BOARD_MOTOR_R_IN2     GPIO_NUM_14

/* Link to the Raspberry Pi. UART0 stays free for the console so logging never
 * corrupts the protocol stream -- the old sketch shared one command buffer
 * between USB and the Pi, so a half-typed console command and a Pi command
 * concatenated into one garbage token. */
#define BOARD_LINK_UART       UART_NUM_2
#define BOARD_LINK_RX         GPIO_NUM_16
#define BOARD_LINK_TX         GPIO_NUM_17
#define BOARD_LINK_BAUD       115200

/* Control loop period. Fast enough that a STOP is acted on well inside the
 * 300 ms motion lease; the old loop spent up to 90 ms blocked in pulseIn()
 * before it even looked at the serial port. */
#define BOARD_LOOP_PERIOD_MS  10
#define BOARD_TELEMETRY_MS    50   /* 20 Hz, matching the previous firmware */

/* Bites if the control loop stops completing cycles. */
#define BOARD_WDT_TIMEOUT_MS  1000

#endif /* BOARD_H */
