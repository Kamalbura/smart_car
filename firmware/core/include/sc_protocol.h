/*
 * Smart Car link protocol, v1 -- portable core.
 *
 * Wire format and rationale: firmware/PROTOCOL.md
 * Executable reference:      src/uart/protocol.py
 *
 * This file has no hardware, RTOS or libc-string dependencies beyond memcpy
 * and memmove, so it compiles unchanged for the host test build, ESP-IDF and
 * STM32. No dynamic allocation anywhere.
 *
* Copyright 2026 Kamal Bura
* SPDX-License-Identifier: Apache-2.0
 */
#ifndef SC_PROTOCOL_H
#define SC_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SC_SOF                    0xA5u
#define SC_PROTOCOL_VERSION       1u

/* LEN is one byte covering SEQ + TYPE + PAYLOAD, so the payload tops out at
 * 255 - 2, and a whole frame occupies payload + 6 bytes on the wire. */
#define SC_MAX_PAYLOAD            253u
#define SC_MAX_FRAME              (SC_MAX_PAYLOAD + 6u)

/* Sentinel distance meaning "this sensor did not answer". Deliberately large
 * so that a consumer which forgets to check it fails loud rather than reading
 * a plausibly small number and driving forward. */
#define SC_DISTANCE_FAULT         0xFFFFu

/* The MCU brakes if no valid frame arrives inside this window. The Pi sends a
 * keepalive at roughly 3x this rate while it intends motion to continue. */
#define SC_COMMAND_TIMEOUT_MS     300u
#define SC_KEEPALIVE_INTERVAL_MS  100u

/* The MCU only ever receives short commands, so its RX buffer needs no more
 * than a few frames of slack. Override at compile time if this core is reused
 * somewhere that receives telemetry. */
#ifndef SC_DECODER_BUFFER
#define SC_DECODER_BUFFER         128u
#endif

/* Message types. Commands (Pi -> MCU) are < 0x80, events (MCU -> Pi) >= 0x80. */
typedef enum {
    SC_CMD_DRIVE       = 0x01,
    SC_CMD_STOP        = 0x02,
    SC_CMD_KEEPALIVE   = 0x03,
    SC_CMD_SERVO       = 0x04,
    SC_CMD_SET_LIMITS  = 0x05,
    SC_CMD_CLEAR_FAULT = 0x06,
    SC_CMD_PING        = 0x07,

    SC_EVT_TELEMETRY   = 0x81,
    SC_EVT_ACK         = 0x82,
    SC_EVT_FAULT       = 0x83,
    SC_EVT_BOOT        = 0x84
} sc_msg_type_t;

/* A refused command is still ACKed, with the reason. Silence must only ever
 * mean "the link is broken", never "I chose not to". */
typedef enum {
    SC_ACK_OK               = 0x00,
    SC_ACK_BAD_LENGTH       = 0x01,
    SC_ACK_UNKNOWN_TYPE     = 0x02,
    SC_ACK_REFUSED_OBSTACLE = 0x03,
    SC_ACK_REFUSED_FAULT    = 0x04,
    SC_ACK_CLAMPED          = 0x05
} sc_ack_status_t;

/* Live state bits in telemetry. */
#define SC_FLAG_OBSTACLE   0x01u
#define SC_FLAG_WARNING    0x02u
#define SC_FLAG_MOVING     0x04u
#define SC_FLAG_ARMED      0x08u
#define SC_FLAG_SCANNING   0x10u

/* Fault bits. SENSOR_n and ALL_SENSORS_LOST track current sensor health;
 * COMM_LOST is raised when the motion lease expires and cleared by the next
 * valid frame. The remaining bits are reserved for hardware this chassis does
 * not yet carry. */
#define SC_FAULT_NONE             0x0000u
#define SC_FAULT_COMM_LOST        0x0001u
#define SC_FAULT_SENSOR_1         0x0002u
#define SC_FAULT_SENSOR_2         0x0004u
#define SC_FAULT_SENSOR_3         0x0008u
#define SC_FAULT_ALL_SENSORS_LOST 0x0010u
#define SC_FAULT_OVERCURRENT      0x0020u
#define SC_FAULT_LOW_BATTERY      0x0040u
#define SC_FAULT_MOTOR_FAULT      0x0080u

typedef struct {
    uint8_t seq;
    uint8_t type;
    uint8_t payload_len;
    uint8_t payload[SC_MAX_PAYLOAD];
} sc_frame_t;

typedef struct {
    uint8_t  buf[SC_DECODER_BUFFER];
    uint16_t len;
    uint32_t crc_errors;
    uint32_t resyncs;
    uint32_t dropped_bytes;
} sc_decoder_t;

/* Telemetry payload, 18 bytes little-endian. Field order and widths are fixed
 * by PROTOCOL.md; sc_telemetry_encode writes the packed form explicitly rather
 * than casting a struct, so host and target agree regardless of padding or
 * endianness. */
typedef struct {
    uint16_t distance_mm[3];
    uint16_t gas_raw;
    uint8_t  servo_deg;
    int8_t   duty_left;
    int8_t   duty_right;
    uint8_t  flags;
    uint16_t faults;
    uint32_t uptime_ms;
} sc_telemetry_t;

#define SC_TELEMETRY_SIZE 18u

/* CRC-16/CCITT-FALSE. poly 0x1021, init 0xFFFF, no reflection, no final XOR.
 * sc_crc16("123456789", 9) must equal 0x29B1. */
uint16_t sc_crc16(const uint8_t *data, uint16_t len);

/* Serialise one frame into out[], which must hold at least SC_MAX_FRAME bytes.
 * Returns the number of bytes written, or 0 if payload_len is out of range. */
uint16_t sc_frame_encode(uint8_t *out, uint8_t seq, uint8_t type,
                         const uint8_t *payload, uint8_t payload_len);

void sc_decoder_init(sc_decoder_t *d);

/* Append received bytes. Silently drops the oldest data if the buffer would
 * overflow, so a peer emitting noise forever cannot wedge the decoder. */
void sc_decoder_push(sc_decoder_t *d, const uint8_t *data, uint16_t len);

/* Pop one frame. Call repeatedly until it returns false:
 *
 *     sc_decoder_push(&dec, rx, n);
 *     while (sc_decoder_next(&dec, &frame)) { handle(&frame); }
 *
 * Resynchronisation is handled internally: an implausible length or a failed
 * CRC discards a single byte and rescans, so one corrupt frame cannot hide the
 * good frames queued behind it. */
bool sc_decoder_next(sc_decoder_t *d, sc_frame_t *out);

/* Pack/unpack the telemetry payload. Both return false on a length mismatch. */
bool sc_telemetry_encode(const sc_telemetry_t *t, uint8_t *out, uint8_t out_len);
bool sc_telemetry_decode(sc_telemetry_t *t, const uint8_t *in, uint8_t in_len);

#ifdef __cplusplus
}
#endif

#endif /* SC_PROTOCOL_H */
