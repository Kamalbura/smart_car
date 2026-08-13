/*
 * Motor and servo drivers (LEDC PWM).
 * Copyright 2025-2026 Bura Kamal. SPDX-License-Identifier: Apache-2.0
 */
#include "drv_actuators.h"

#include "board.h"
#include "driver/ledc.h"
#include "esp_err.h"

/* Motors: 20 kHz keeps the switching whine out of the audible band, which
 * matters because this robot listens for a wakeword. 8-bit resolution is ample
 * for a percentage. */
#define MOTOR_TIMER      LEDC_TIMER_0
#define MOTOR_FREQ_HZ    20000
#define MOTOR_RES        LEDC_TIMER_8_BIT
#define MOTOR_DUTY_MAX   255

/* Servo: standard 50 Hz frame. 14-bit resolution gives ~1.2 us of granularity
 * across the 20 ms period, comfortably finer than any hobby servo resolves. */
#define SERVO_TIMER      LEDC_TIMER_1
#define SERVO_FREQ_HZ    50
#define SERVO_RES        LEDC_TIMER_14_BIT
#define SERVO_PERIOD_US  20000
#define SERVO_MIN_US     500
#define SERVO_MAX_US     2500

#define CH_L_IN1         LEDC_CHANNEL_0
#define CH_L_IN2         LEDC_CHANNEL_1
#define CH_R_IN1         LEDC_CHANNEL_2
#define CH_R_IN2         LEDC_CHANNEL_3
#define CH_SERVO         LEDC_CHANNEL_4

#define MODE             LEDC_LOW_SPEED_MODE

static uint8_t s_servo_deg = BOARD_SERVO_HOME_DEG;

static void channel_init(ledc_channel_t channel, int gpio, ledc_timer_t timer)
{
    ledc_channel_config_t cfg = {
        .gpio_num   = gpio,
        .speed_mode = MODE,
        .channel    = channel,
        .intr_type  = LEDC_INTR_DISABLE,
        .timer_sel  = timer,
        .duty       = 0,
        .hpoint     = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&cfg));
}

static void set_duty(ledc_channel_t channel, uint32_t duty)
{
    ESP_ERROR_CHECK(ledc_set_duty(MODE, channel, duty));
    ESP_ERROR_CHECK(ledc_update_duty(MODE, channel));
}

void drv_actuators_init(void)
{
    ledc_timer_config_t motor_timer = {
        .speed_mode      = MODE,
        .duty_resolution = MOTOR_RES,
        .timer_num       = MOTOR_TIMER,
        .freq_hz         = MOTOR_FREQ_HZ,
        .clk_cfg         = LEDC_AUTO_CLK,
    };
    ledc_timer_config_t servo_timer = {
        .speed_mode      = MODE,
        .duty_resolution = SERVO_RES,
        .timer_num       = SERVO_TIMER,
        .freq_hz         = SERVO_FREQ_HZ,
        .clk_cfg         = LEDC_AUTO_CLK,
    };

    ESP_ERROR_CHECK(ledc_timer_config(&motor_timer));
    ESP_ERROR_CHECK(ledc_timer_config(&servo_timer));

    channel_init(CH_L_IN1, BOARD_MOTOR_L_IN1, MOTOR_TIMER);
    channel_init(CH_L_IN2, BOARD_MOTOR_L_IN2, MOTOR_TIMER);
    channel_init(CH_R_IN1, BOARD_MOTOR_R_IN1, MOTOR_TIMER);
    channel_init(CH_R_IN2, BOARD_MOTOR_R_IN2, MOTOR_TIMER);
    channel_init(CH_SERVO, BOARD_SERVO_PIN, SERVO_TIMER);

    drv_motor_brake();
    drv_servo_set(BOARD_SERVO_HOME_DEG);
}

/* One side of the H-bridge. Positive drives IN1 and holds IN2 low; negative
 * mirrors that; zero drives both high, which shorts the motor terminals and
 * brakes. */
static void side_set(ledc_channel_t in1, ledc_channel_t in2, int8_t pct)
{
    uint32_t duty;

    if (pct > 0) {
        duty = ((uint32_t)pct * MOTOR_DUTY_MAX) / 100u;
        set_duty(in1, duty);
        set_duty(in2, 0u);
    } else if (pct < 0) {
        duty = ((uint32_t)(-(int32_t)pct) * MOTOR_DUTY_MAX) / 100u;
        set_duty(in1, 0u);
        set_duty(in2, duty);
    } else {
        set_duty(in1, MOTOR_DUTY_MAX);
        set_duty(in2, MOTOR_DUTY_MAX);
    }
}

void drv_motor_set(int8_t left_pct, int8_t right_pct)
{
    if (left_pct > 100)  { left_pct = 100; }
    if (left_pct < -100) { left_pct = -100; }
    if (right_pct > 100)  { right_pct = 100; }
    if (right_pct < -100) { right_pct = -100; }

    side_set(CH_L_IN1, CH_L_IN2, left_pct);
    side_set(CH_R_IN1, CH_R_IN2, right_pct);
}

void drv_motor_brake(void)
{
    drv_motor_set(0, 0);
}

void drv_servo_set(uint8_t degrees)
{
    uint32_t pulse_us;
    uint32_t duty;

    if (degrees > BOARD_SERVO_MAX_DEG) {
        degrees = BOARD_SERVO_MAX_DEG;
    }
    s_servo_deg = degrees;

    pulse_us = SERVO_MIN_US +
               (((uint32_t)degrees * (SERVO_MAX_US - SERVO_MIN_US)) / 180u);
    duty = (pulse_us * ((1u << 14) - 1u)) / SERVO_PERIOD_US;
    set_duty(CH_SERVO, duty);
}

uint8_t drv_servo_get(void)
{
    return s_servo_deg;
}
