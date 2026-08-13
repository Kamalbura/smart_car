/*
 * Smart Car link protocol, v1 -- portable core.
 * Copyright 2025-2026 Bura Kamal. SPDX-License-Identifier: Apache-2.0
 */
#include "sc_protocol.h"

#include <string.h>

uint16_t sc_crc16(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFFu;
    uint16_t i;
    uint8_t bit;

    for (i = 0u; i < len; i++) {
        crc ^= (uint16_t)((uint16_t)data[i] << 8);
        for (bit = 0u; bit < 8u; bit++) {
            if ((crc & 0x8000u) != 0u) {
                crc = (uint16_t)((uint16_t)(crc << 1) ^ 0x1021u);
            } else {
                crc = (uint16_t)(crc << 1);
            }
        }
    }
    return crc;
}

uint16_t sc_frame_encode(uint8_t *out, uint8_t seq, uint8_t type,
                         const uint8_t *payload, uint8_t payload_len)
{
    uint16_t crc;
    uint16_t total;

    if (out == NULL) {
        return 0u;
    }
    if (payload_len > SC_MAX_PAYLOAD) {
        return 0u;
    }
    if ((payload_len > 0u) && (payload == NULL)) {
        return 0u;
    }

    out[0] = SC_SOF;
    out[1] = (uint8_t)(payload_len + 2u); /* LEN covers SEQ + TYPE + PAYLOAD */
    out[2] = seq;
    out[3] = type;
    if (payload_len > 0u) {
        memcpy(&out[4], payload, payload_len);
    }

    /* CRC spans LEN, SEQ, TYPE and PAYLOAD -- everything but the SOF and the
     * CRC field itself. */
    crc = sc_crc16(&out[1], (uint16_t)(payload_len + 3u));
    out[4u + payload_len] = (uint8_t)(crc & 0xFFu);
    out[5u + payload_len] = (uint8_t)((crc >> 8) & 0xFFu);

    total = (uint16_t)payload_len + 6u;
    return total;
}

void sc_decoder_init(sc_decoder_t *d)
{
    if (d == NULL) {
        return;
    }
    d->len = 0u;
    d->crc_errors = 0u;
    d->resyncs = 0u;
    d->dropped_bytes = 0u;
}

/* Remove n bytes from the front. Used both for consuming a decoded frame and
 * for discarding junk; the caller decides whether that counts as dropped. */
static void sc__shift(sc_decoder_t *d, uint16_t n)
{
    if (n >= d->len) {
        d->len = 0u;
        return;
    }
    memmove(&d->buf[0], &d->buf[n], (size_t)(d->len - n));
    d->len = (uint16_t)(d->len - n);
}

static void sc__drop(sc_decoder_t *d, uint16_t n)
{
    d->dropped_bytes += n;
    sc__shift(d, n);
}

void sc_decoder_push(sc_decoder_t *d, const uint8_t *data, uint16_t len)
{
    uint16_t space;
    uint16_t overflow;

    if ((d == NULL) || (data == NULL) || (len == 0u)) {
        return;
    }

    /* A single push larger than the whole buffer can only keep its tail. */
    if (len >= SC_DECODER_BUFFER) {
        d->dropped_bytes += (uint32_t)(d->len) +
                            (uint32_t)(len - SC_DECODER_BUFFER);
        memcpy(&d->buf[0], &data[len - SC_DECODER_BUFFER], SC_DECODER_BUFFER);
        d->len = SC_DECODER_BUFFER;
        return;
    }

    space = (uint16_t)(SC_DECODER_BUFFER - d->len);
    if (len > space) {
        overflow = (uint16_t)(len - space);
        sc__drop(d, overflow);
    }
    memcpy(&d->buf[d->len], data, len);
    d->len = (uint16_t)(d->len + len);
}

bool sc_decoder_next(sc_decoder_t *d, sc_frame_t *out)
{
    uint16_t start;
    uint8_t  length;
    uint16_t total;
    uint16_t crc_calc;
    uint16_t crc_rx;

    if ((d == NULL) || (out == NULL)) {
        return false;
    }

    for (;;) {
        /* Scan to the next SOF, discarding anything ahead of it. */
        start = 0u;
        while ((start < d->len) && (d->buf[start] != SC_SOF)) {
            start++;
        }
        if (start > 0u) {
            sc__drop(d, start);
            d->resyncs++;
        }

        if (d->len < 2u) {
            return false; /* need SOF + LEN before the length is even known */
        }

        length = d->buf[1];
        /* LEN's own width bounds the upper end; only the floor needs checking.
         * An implausible length means that 0xA5 was payload, not a header. */
        if (length < 2u) {
            sc__drop(d, 1u);
            d->resyncs++;
            continue;
        }

        total = (uint16_t)length + 4u;
        if (d->len < total) {
            return false; /* frame still in flight */
        }

        crc_calc = sc_crc16(&d->buf[1], (uint16_t)(length + 1u));
        crc_rx = (uint16_t)d->buf[2u + length] |
                 (uint16_t)((uint16_t)d->buf[3u + length] << 8);
        if (crc_calc != crc_rx) {
            /* Discard only the SOF byte, never the whole candidate frame: a
             * genuine frame may begin inside the span we would have skipped. */
            d->crc_errors++;
            sc__drop(d, 1u);
            d->resyncs++;
            continue;
        }

        out->seq = d->buf[2];
        out->type = d->buf[3];
        out->payload_len = (uint8_t)(length - 2u);
        if (out->payload_len > 0u) {
            memcpy(out->payload, &d->buf[4], out->payload_len);
        }
        sc__shift(d, total); /* consumed, not dropped */
        return true;
    }
}

bool sc_telemetry_encode(const sc_telemetry_t *t, uint8_t *out, uint8_t out_len)
{
    if ((t == NULL) || (out == NULL) || (out_len != SC_TELEMETRY_SIZE)) {
        return false;
    }

    out[0]  = (uint8_t)(t->distance_mm[0] & 0xFFu);
    out[1]  = (uint8_t)((t->distance_mm[0] >> 8) & 0xFFu);
    out[2]  = (uint8_t)(t->distance_mm[1] & 0xFFu);
    out[3]  = (uint8_t)((t->distance_mm[1] >> 8) & 0xFFu);
    out[4]  = (uint8_t)(t->distance_mm[2] & 0xFFu);
    out[5]  = (uint8_t)((t->distance_mm[2] >> 8) & 0xFFu);
    out[6]  = (uint8_t)(t->gas_raw & 0xFFu);
    out[7]  = (uint8_t)((t->gas_raw >> 8) & 0xFFu);
    out[8]  = t->servo_deg;
    out[9]  = (uint8_t)t->duty_left;
    out[10] = (uint8_t)t->duty_right;
    out[11] = t->flags;
    out[12] = (uint8_t)(t->faults & 0xFFu);
    out[13] = (uint8_t)((t->faults >> 8) & 0xFFu);
    out[14] = (uint8_t)(t->uptime_ms & 0xFFu);
    out[15] = (uint8_t)((t->uptime_ms >> 8) & 0xFFu);
    out[16] = (uint8_t)((t->uptime_ms >> 16) & 0xFFu);
    out[17] = (uint8_t)((t->uptime_ms >> 24) & 0xFFu);
    return true;
}

bool sc_telemetry_decode(sc_telemetry_t *t, const uint8_t *in, uint8_t in_len)
{
    if ((t == NULL) || (in == NULL) || (in_len != SC_TELEMETRY_SIZE)) {
        return false;
    }

    t->distance_mm[0] = (uint16_t)in[0] | (uint16_t)((uint16_t)in[1] << 8);
    t->distance_mm[1] = (uint16_t)in[2] | (uint16_t)((uint16_t)in[3] << 8);
    t->distance_mm[2] = (uint16_t)in[4] | (uint16_t)((uint16_t)in[5] << 8);
    t->gas_raw        = (uint16_t)in[6] | (uint16_t)((uint16_t)in[7] << 8);
    t->servo_deg      = in[8];
    t->duty_left      = (int8_t)in[9];
    t->duty_right     = (int8_t)in[10];
    t->flags          = in[11];
    t->faults         = (uint16_t)in[12] | (uint16_t)((uint16_t)in[13] << 8);
    t->uptime_ms      = (uint32_t)in[14] |
                        ((uint32_t)in[15] << 8) |
                        ((uint32_t)in[16] << 16) |
                        ((uint32_t)in[17] << 24);
    return true;
}
