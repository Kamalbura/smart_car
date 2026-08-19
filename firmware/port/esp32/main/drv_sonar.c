/*
 * Non-blocking HC-SR04 driver.
 * Copyright 2026 Kamal Bura
 * SPDX-License-Identifier: Apache-2.0
 */
#include "drv_sonar.h"

#include <stdint.h>

#include "driver/gpio.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "sc_protocol.h"

/* HC-SR04 tops out near 4 m. 4 m out and back is 8 m of travel, ~23.3 ms at
 * 343 m/s, so anything longer is a miss rather than a distant object. */
#define SONAR_MAX_ECHO_US   25000
#define SONAR_TIMEOUT_US    30000
#define SONAR_TRIG_US       10

typedef struct {
    gpio_num_t trig;
    gpio_num_t echo;
} sonar_pins_t;

static const sonar_pins_t s_pins[BOARD_SONAR_COUNT] = {
    { BOARD_SONAR1_TRIG, BOARD_SONAR1_ECHO },
    { BOARD_SONAR2_TRIG, BOARD_SONAR2_ECHO },
    { BOARD_SONAR3_TRIG, BOARD_SONAR3_ECHO },
};

static volatile int64_t s_rise_us[BOARD_SONAR_COUNT];
static volatile int64_t s_fall_us[BOARD_SONAR_COUNT];
static volatile bool    s_complete[BOARD_SONAR_COUNT];

static uint16_t s_last_mm[BOARD_SONAR_COUNT];
static int      s_active = -1;
static int      s_next = 0;
static int64_t  s_trigger_us = 0;
static bool     s_sweep_ready = false;

/* Deliberately not IRAM_ATTR: the ISR is registered without
 * ESP_INTR_FLAG_IRAM, so it may touch flash-resident constants. Entry latency
 * costs a few microseconds, which at ~58 us per centimetre of round trip is
 * well under one centimetre of error. */
static void echo_isr(void *arg)
{
    int idx = (int)(intptr_t)arg;
    int64_t now = esp_timer_get_time();

    if (gpio_get_level(s_pins[idx].echo) != 0) {
        s_rise_us[idx] = now;
    } else {
        s_fall_us[idx] = now;
        s_complete[idx] = true;
    }
}

void drv_sonar_init(void)
{
    gpio_config_t trig_cfg = {
        .pin_bit_mask = 0,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config_t echo_cfg = {
        .pin_bit_mask = 0,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_ANYEDGE,
    };
    int i;

    for (i = 0; i < BOARD_SONAR_COUNT; i++) {
        trig_cfg.pin_bit_mask |= (1ULL << s_pins[i].trig);
        echo_cfg.pin_bit_mask |= (1ULL << s_pins[i].echo);
        s_last_mm[i] = SC_DISTANCE_FAULT;
        s_complete[i] = false;
    }
    gpio_config(&trig_cfg);
    gpio_config(&echo_cfg);

    for (i = 0; i < BOARD_SONAR_COUNT; i++) {
        gpio_set_level(s_pins[i].trig, 0);
    }

    gpio_install_isr_service(0);
    for (i = 0; i < BOARD_SONAR_COUNT; i++) {
        gpio_isr_handler_add(s_pins[i].echo, echo_isr, (void *)(intptr_t)i);
    }
}

static void start_next(void)
{
    int idx = s_next;

    s_next++;
    if (s_next >= BOARD_SONAR_COUNT) {
        s_next = 0;
        s_sweep_ready = true; /* a full round of sensors has now been measured */
    }

    s_complete[idx] = false;
    s_rise_us[idx] = 0;
    s_fall_us[idx] = 0;

    gpio_set_level(s_pins[idx].trig, 1);
    esp_rom_delay_us(SONAR_TRIG_US);
    gpio_set_level(s_pins[idx].trig, 0);

    s_trigger_us = esp_timer_get_time();
    s_active = idx;
}

void drv_sonar_tick(void)
{
    int64_t now;
    int64_t width;
    int idx;

    if (s_active < 0) {
        start_next();
        return;
    }

    idx = s_active;
    now = esp_timer_get_time();

    if (s_complete[idx]) {
        width = s_fall_us[idx] - s_rise_us[idx];
        if ((width > 0) && (width < SONAR_MAX_ECHO_US)) {
            /* 343 m/s is 0.343 mm/us; halve it for the round trip. */
            s_last_mm[idx] = (uint16_t)((width * 343) / 2000);
        } else {
            s_last_mm[idx] = SC_DISTANCE_FAULT;
        }
        s_active = -1;
        return;
    }

    if ((now - s_trigger_us) > SONAR_TIMEOUT_US) {
        /* No echo. Reported as a fault, never as a large distance -- a missing
         * reading must not read as clear road. */
        s_last_mm[idx] = SC_DISTANCE_FAULT;
        s_active = -1;
    }
}

bool drv_sonar_sweep_ready(uint16_t out_mm[BOARD_SONAR_COUNT])
{
    int i;

    if (!s_sweep_ready) {
        return false;
    }
    s_sweep_ready = false;
    for (i = 0; i < BOARD_SONAR_COUNT; i++) {
        out_mm[i] = s_last_mm[i];
    }
    return true;
}

void drv_sonar_read(uint16_t out_mm[BOARD_SONAR_COUNT])
{
    int i;
    for (i = 0; i < BOARD_SONAR_COUNT; i++) {
        out_mm[i] = s_last_mm[i];
    }
}
