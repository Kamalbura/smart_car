/*
 * Smart Car motion MCU -- ESP32 application.
 *
 * The control loop never blocks. Echo timing runs off a GPIO interrupt, the
 * UART is read non-blocking, and the motion lease is evaluated every tick, so
 * a STOP is acted on within one 10 ms period rather than behind 90 ms of
 * pulseIn() plus a 50 ms delay().
 *
 * All motion policy lives in the portable core (sc_safety), which is verified
 * on the host by firmware/test and mirrored by src/uart/safety.py. This file
 * is only plumbing: it moves bytes and drives pins.
 *
 * Copyright 2025-2026 Bura Kamal. SPDX-License-Identifier: Apache-2.0
 */
#include <string.h>

#include "board.h"
#include "drv_actuators.h"
#include "drv_sonar.h"
#include "driver/uart.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_err.h"
#include "esp_idf_version.h"
#include "esp_log.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sc_protocol.h"
#include "sc_safety.h"

/* ADC_ATTEN_DB_11 was renamed ADC_ATTEN_DB_12 in IDF 5.2. Both are enum
 * constants rather than macros, so this must be a version test: an #ifndef
 * cannot see an enum and silently selects the deprecated name. */
#if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(5, 2, 0)
#define SC_ADC_ATTEN ADC_ATTEN_DB_11
#else
#define SC_ADC_ATTEN ADC_ATTEN_DB_12
#endif

#define FW_VERSION_MAJOR 1
#define FW_VERSION_MINOR 0

static const char *TAG = "smartcar";

static sc_safety_t  s_safety;
static sc_decoder_t s_decoder;
static uint8_t      s_tx_seq;
static uint16_t     s_last_faults;
static adc_oneshot_unit_handle_t s_adc;

static uint32_t now_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}

static void link_send(uint8_t type, const uint8_t *payload, uint8_t len)
{
    uint8_t frame[SC_MAX_FRAME];
    uint16_t n;

    s_tx_seq++;
    n = sc_frame_encode(frame, s_tx_seq, type, payload, len);
    if (n > 0u) {
        uart_write_bytes(BOARD_LINK_UART, frame, n);
    }
}

static void send_ack(uint8_t acked_seq, sc_ack_status_t status)
{
    uint8_t payload[2];
    payload[0] = acked_seq;
    payload[1] = (uint8_t)status;
    link_send(SC_EVT_ACK, payload, 2u);
}

static void send_fault(uint16_t faults)
{
    uint8_t payload[4];
    payload[0] = (uint8_t)(faults & 0xFFu);
    payload[1] = (uint8_t)((faults >> 8) & 0xFFu);
    payload[2] = 0u;
    payload[3] = 0u;
    link_send(SC_EVT_FAULT, payload, 4u);
}

static void send_boot(void)
{
    uint8_t payload[3];
    payload[0] = SC_PROTOCOL_VERSION;
    payload[1] = FW_VERSION_MAJOR;
    payload[2] = FW_VERSION_MINOR;
    link_send(SC_EVT_BOOT, payload, 3u);
}

static void send_telemetry(void)
{
    sc_telemetry_t t;
    uint8_t payload[SC_TELEMETRY_SIZE];
    uint16_t mm[BOARD_SONAR_COUNT];
    int adc_raw = 0;

    drv_sonar_read(mm);
    t.distance_mm[0] = mm[0];
    t.distance_mm[1] = mm[1];
    t.distance_mm[2] = mm[2];

    if (s_adc != NULL) {
        if (adc_oneshot_read(s_adc, BOARD_GAS_ADC_CHANNEL, &adc_raw) != ESP_OK) {
            adc_raw = 0;
        }
    }
    t.gas_raw = (uint16_t)adc_raw;
    t.servo_deg = drv_servo_get();
    /* Actual applied duty, not what was requested. The old firmware declared
     * leftMotorSpeed/rightMotorSpeed, never assigned them, and reported zeros
     * while the robot was moving. */
    t.duty_left = s_safety.applied_left;
    t.duty_right = s_safety.applied_right;
    t.flags = sc_safety_flags(&s_safety);
    t.faults = s_safety.faults;
    t.uptime_ms = now_ms();

    if (sc_telemetry_encode(&t, payload, SC_TELEMETRY_SIZE)) {
        link_send(SC_EVT_TELEMETRY, payload, SC_TELEMETRY_SIZE);
    }
}

static void handle_frame(const sc_frame_t *f)
{
    sc_ack_status_t status = SC_ACK_OK;
    sc_decision_t decision;
    sc_limits_t limits;

    switch (f->type) {
    case SC_CMD_DRIVE:
        if (f->payload_len != 2u) {
            status = SC_ACK_BAD_LENGTH;
            break;
        }
        decision = sc_safety_request_drive(&s_safety,
                                           (int8_t)f->payload[0],
                                           (int8_t)f->payload[1]);
        status = decision.status;
        break;

    case SC_CMD_STOP:
        (void)sc_safety_request_drive(&s_safety, 0, 0);
        break;

    case SC_CMD_KEEPALIVE:
        /* The lease was already renewed by the caller. A keepalive carries no
         * motion intent of its own, so it must never restart a robot the
         * deadman stopped. */
        break;

    case SC_CMD_SERVO:
        if (f->payload_len != 1u) {
            status = SC_ACK_BAD_LENGTH;
            break;
        }
        drv_servo_set(f->payload[0]);
        break;

    case SC_CMD_SET_LIMITS:
        if (f->payload_len != 4u) {
            status = SC_ACK_BAD_LENGTH;
            break;
        }
        limits = s_safety.limits;
        limits.stop_mm = (uint16_t)f->payload[0] |
                         (uint16_t)((uint16_t)f->payload[1] << 8);
        limits.warn_mm = (uint16_t)f->payload[2] |
                         (uint16_t)((uint16_t)f->payload[3] << 8);
        s_safety.limits = limits;
        break;

    case SC_CMD_CLEAR_FAULT:
        status = sc_safety_request_clear_fault(&s_safety);
        break;

    case SC_CMD_PING:
        break;

    default:
        status = SC_ACK_UNKNOWN_TYPE;
        break;
    }

    /* Every command is answered, including refusals. Silence must only ever
     * mean the link is broken. */
    send_ack(f->seq, status);
}

static void init_link(void)
{
    uart_config_t cfg = {
        .baud_rate = BOARD_LINK_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    ESP_ERROR_CHECK(uart_driver_install(BOARD_LINK_UART, 1024, 1024, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(BOARD_LINK_UART, &cfg));
    ESP_ERROR_CHECK(uart_set_pin(BOARD_LINK_UART, BOARD_LINK_TX, BOARD_LINK_RX,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
}

static void init_adc(void)
{
    adc_oneshot_unit_init_cfg_t unit_cfg = {
        .unit_id = BOARD_GAS_ADC_UNIT,
    };
    adc_oneshot_chan_cfg_t chan_cfg = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten    = SC_ADC_ATTEN,
    };

    if (adc_oneshot_new_unit(&unit_cfg, &s_adc) != ESP_OK) {
        ESP_LOGW(TAG, "ADC unavailable; gas readings will report 0");
        s_adc = NULL;
        return;
    }
    ESP_ERROR_CHECK(adc_oneshot_config_channel(s_adc, BOARD_GAS_ADC_CHANNEL,
                                               &chan_cfg));
}

static void init_watchdog(void)
{
    esp_task_wdt_config_t cfg = {
        .timeout_ms = BOARD_WDT_TIMEOUT_MS,
        .idle_core_mask = 0,
        .trigger_panic = true,
    };
    esp_err_t err = esp_task_wdt_init(&cfg);

    if (err == ESP_ERR_INVALID_STATE) {
        /* Already started from sdkconfig; adopt our timeout instead. */
        ESP_ERROR_CHECK(esp_task_wdt_reconfigure(&cfg));
    } else {
        ESP_ERROR_CHECK(err);
    }
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
}

void app_main(void)
{
    uint32_t last_telemetry;
    uint8_t rx[128];

    s_tx_seq = 0u;
    s_adc = NULL;

    sc_safety_init(&s_safety, NULL);
    sc_decoder_init(&s_decoder);
    s_last_faults = s_safety.faults;

    drv_actuators_init();
    drv_sonar_init();
    init_link();
    init_adc();
    init_watchdog();

    /* Announce the reset so the Pi can tell a brownout or watchdog bite from
     * mere silence -- the ASCII protocol could not distinguish them. */
    send_boot();
    ESP_LOGI(TAG, "smart_car MCU up, protocol v%d, fw %d.%d",
             SC_PROTOCOL_VERSION, FW_VERSION_MAJOR, FW_VERSION_MINOR);

    last_telemetry = now_ms();

    for (;;) {
        uint32_t t_now = now_ms();
        uint16_t sweep[BOARD_SONAR_COUNT];
        sc_decision_t decision;
        int n;

        n = uart_read_bytes(BOARD_LINK_UART, rx, sizeof(rx), 0);
        if (n > 0) {
            sc_frame_t frame;
            sc_decoder_push(&s_decoder, rx, (uint16_t)n);
            while (sc_decoder_next(&s_decoder, &frame)) {
                /* Any well-formed, CRC-valid frame renews the lease. */
                sc_safety_on_valid_frame(&s_safety, t_now);
                handle_frame(&frame);
            }
        }

        drv_sonar_tick();
        if (drv_sonar_sweep_ready(sweep)) {
            sc_safety_update_sensors(&s_safety, sweep);
        }

        /* The single point where policy becomes motion. */
        decision = sc_safety_tick(&s_safety, t_now);
        drv_motor_set(decision.left, decision.right);

        if (s_safety.faults != s_last_faults) {
            s_last_faults = s_safety.faults;
            send_fault(s_last_faults);
        }

        if ((uint32_t)(t_now - last_telemetry) >= BOARD_TELEMETRY_MS) {
            last_telemetry = t_now;
            send_telemetry();
        }

        /* Only petted on a completed cycle, so a hung loop bites. */
        esp_task_wdt_reset();
        vTaskDelay(pdMS_TO_TICKS(BOARD_LOOP_PERIOD_MS));
    }
}
