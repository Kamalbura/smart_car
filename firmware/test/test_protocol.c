/*
 * Frame integrity tests, including byte-exact golden vectors shared with the
 * Python implementation. If a golden vector fails, the MCU and the Pi have
 * diverged on the wire format and nothing else in this suite matters.
 *
 * Vectors were generated from src/uart/protocol.py and are duplicated in
 * firmware/PROTOCOL.md.
 */
#include <string.h>

#include "sc_protocol.h"
#include "sc_test.h"

static void expect_bytes(const uint8_t *actual, uint16_t actual_len,
                         const uint8_t *expected, uint16_t expected_len,
                         const char *label)
{
    uint16_t i;

    sc_test_checks++;
    if (actual_len != expected_len) {
        sc_test_failed++;
        printf("    FAIL %s: length %u, expected %u\n",
               label, (unsigned)actual_len, (unsigned)expected_len);
        return;
    }
    for (i = 0u; i < expected_len; i++) {
        if (actual[i] != expected[i]) {
            sc_test_failed++;
            printf("    FAIL %s: byte %u is 0x%02X, expected 0x%02X\n",
                   label, (unsigned)i, actual[i], expected[i]);
            return;
        }
    }
}

/* -- CRC ---------------------------------------------------------------- */

static void test_crc_check_value(void)
{
    /* The published CRC-16/CCITT-FALSE check value. Pins the algorithm across
     * both languages; if this drifts, every golden vector below is wrong. */
    SC_CHECK_EQ(sc_crc16((const uint8_t *)"123456789", 9u), 0x29B1);
}

/* -- Golden vectors ----------------------------------------------------- */

static void test_golden_cmd_stop(void)
{
    static const uint8_t want[] = { 0xA5, 0x02, 0x01, 0x02, 0x8F, 0xB1 };
    uint8_t out[SC_MAX_FRAME];
    uint16_t n = sc_frame_encode(out, 1u, SC_CMD_STOP, NULL, 0u);
    expect_bytes(out, n, want, sizeof(want), "CMD_STOP seq=1");
}

static void test_golden_cmd_drive_forward(void)
{
    static const uint8_t want[] = { 0xA5, 0x04, 0x01, 0x01, 0x46, 0x46, 0xE6, 0x56 };
    static const uint8_t payload[] = { 0x46, 0x46 }; /* +70, +70 */
    uint8_t out[SC_MAX_FRAME];
    uint16_t n = sc_frame_encode(out, 1u, SC_CMD_DRIVE, payload, 2u);
    expect_bytes(out, n, want, sizeof(want), "CMD_DRIVE fwd 70%");
}

static void test_golden_cmd_drive_left(void)
{
    /* Counter-rotation: left side reversed. -70 is 0xBA as int8. */
    static const uint8_t want[] = { 0xA5, 0x04, 0x01, 0x01, 0xBA, 0x46, 0x4A, 0x00 };
    static const uint8_t payload[] = { 0xBA, 0x46 };
    uint8_t out[SC_MAX_FRAME];
    uint16_t n = sc_frame_encode(out, 1u, SC_CMD_DRIVE, payload, 2u);
    expect_bytes(out, n, want, sizeof(want), "CMD_DRIVE left 70%");
}

static void test_golden_cmd_keepalive(void)
{
    static const uint8_t want[] = { 0xA5, 0x02, 0x01, 0x03, 0xAE, 0xA1 };
    uint8_t out[SC_MAX_FRAME];
    uint16_t n = sc_frame_encode(out, 1u, SC_CMD_KEEPALIVE, NULL, 0u);
    expect_bytes(out, n, want, sizeof(want), "CMD_KEEPALIVE seq=1");
}

static void test_golden_cmd_servo(void)
{
    static const uint8_t want[] = { 0xA5, 0x03, 0x01, 0x04, 0x5A, 0x57, 0x1F };
    static const uint8_t payload[] = { 90u };
    uint8_t out[SC_MAX_FRAME];
    uint16_t n = sc_frame_encode(out, 1u, SC_CMD_SERVO, payload, 1u);
    expect_bytes(out, n, want, sizeof(want), "CMD_SERVO angle=90");
}

static void test_golden_evt_ack(void)
{
    static const uint8_t want[] = { 0xA5, 0x04, 0x01, 0x82, 0x01, 0x00, 0xB5, 0x88 };
    static const uint8_t payload[] = { 1u, SC_ACK_OK };
    uint8_t out[SC_MAX_FRAME];
    uint16_t n = sc_frame_encode(out, 1u, SC_EVT_ACK, payload, 2u);
    expect_bytes(out, n, want, sizeof(want), "EVT_ACK ack(1,OK)");
}

static void test_golden_evt_telemetry(void)
{
    static const uint8_t want[] = {
        0xA5, 0x14, 0x01, 0x81,
        0xB0, 0x04, 0x20, 0x03, 0xD0, 0x07, 0x36, 0x01,
        0x5A, 0x00, 0x00, 0x08, 0x00, 0x00, 0x40, 0xE2, 0x01, 0x00,
        0xE9, 0x29
    };
    sc_telemetry_t t;
    uint8_t payload[SC_TELEMETRY_SIZE];
    uint8_t out[SC_MAX_FRAME];
    uint16_t n;

    t.distance_mm[0] = 1200u;
    t.distance_mm[1] = 800u;
    t.distance_mm[2] = 2000u;
    t.gas_raw = 310u;
    t.servo_deg = 90u;
    t.duty_left = 0;
    t.duty_right = 0;
    t.flags = SC_FLAG_ARMED;
    t.faults = SC_FAULT_NONE;
    t.uptime_ms = 123456u;

    SC_CHECK(sc_telemetry_encode(&t, payload, SC_TELEMETRY_SIZE));
    n = sc_frame_encode(out, 1u, SC_EVT_TELEMETRY, payload, SC_TELEMETRY_SIZE);
    expect_bytes(out, n, want, sizeof(want), "EVT_TELEMETRY");
}

/* -- Framing ------------------------------------------------------------ */

static void test_roundtrip(void)
{
    static const uint8_t payload[] = { 0x40, 0x40 };
    uint8_t out[SC_MAX_FRAME];
    sc_decoder_t dec;
    sc_frame_t frame;
    uint16_t n = sc_frame_encode(out, 7u, SC_CMD_DRIVE, payload, 2u);

    sc_decoder_init(&dec);
    sc_decoder_push(&dec, out, n);
    SC_CHECK(sc_decoder_next(&dec, &frame));
    SC_CHECK_EQ(frame.seq, 7);
    SC_CHECK_EQ(frame.type, SC_CMD_DRIVE);
    SC_CHECK_EQ(frame.payload_len, 2);
    SC_CHECK_EQ(frame.payload[0], 0x40);
    SC_CHECK(!sc_decoder_next(&dec, &frame));
}

static void test_byte_at_a_time(void)
{
    uint8_t out[SC_MAX_FRAME];
    sc_decoder_t dec;
    sc_frame_t frame;
    uint16_t n = sc_frame_encode(out, 3u, SC_CMD_PING, NULL, 0u);
    uint16_t i;
    int found = 0;

    sc_decoder_init(&dec);
    for (i = 0u; i < n; i++) {
        sc_decoder_push(&dec, &out[i], 1u);
        while (sc_decoder_next(&dec, &frame)) {
            found++;
        }
    }
    SC_CHECK_EQ(found, 1);
}

static void test_garbage_prefix_is_discarded(void)
{
    /* Opening the port mid-stream must not lose the next good frame. */
    static const uint8_t junk[] = { 0x00, 0x11, 0x22, 0x33 };
    uint8_t out[SC_MAX_FRAME];
    sc_decoder_t dec;
    sc_frame_t frame;
    uint16_t n = sc_frame_encode(out, 5u, SC_CMD_PING, NULL, 0u);

    sc_decoder_init(&dec);
    sc_decoder_push(&dec, junk, sizeof(junk));
    sc_decoder_push(&dec, out, n);
    SC_CHECK(sc_decoder_next(&dec, &frame));
    SC_CHECK_EQ(frame.seq, 5);
    SC_CHECK(dec.dropped_bytes > 0u);
}

static void test_sof_inside_payload_survives(void)
{
    static const uint8_t payload[] = { SC_SOF, SC_SOF, 0x02, SC_SOF };
    uint8_t out[SC_MAX_FRAME];
    sc_decoder_t dec;
    sc_frame_t frame;
    uint16_t n = sc_frame_encode(out, 9u, SC_EVT_TELEMETRY, payload, 4u);

    sc_decoder_init(&dec);
    sc_decoder_push(&dec, out, n);
    SC_CHECK(sc_decoder_next(&dec, &frame));
    SC_CHECK_EQ(frame.payload_len, 4);
    SC_CHECK_EQ(frame.payload[0], SC_SOF);
}

static void test_corrupted_crc_is_rejected(void)
{
    static const uint8_t payload[] = { 0x40, 0x40 };
    uint8_t out[SC_MAX_FRAME];
    sc_decoder_t dec;
    sc_frame_t frame;
    uint16_t n = sc_frame_encode(out, 1u, SC_CMD_DRIVE, payload, 2u);

    out[n - 1u] ^= 0xFFu;
    sc_decoder_init(&dec);
    sc_decoder_push(&dec, out, n);
    SC_CHECK(!sc_decoder_next(&dec, &frame));
    SC_CHECK_EQ(dec.crc_errors, 1);
}

static void test_recovers_after_a_corrupted_frame(void)
{
    /* The Python implementation had a bug here: discarding a bad frame ended
     * the scan, so one corruption hid every good frame behind it. */
    static const uint8_t payload[] = { 0x40, 0x40 };
    uint8_t bad[SC_MAX_FRAME];
    uint8_t good[SC_MAX_FRAME];
    sc_decoder_t dec;
    sc_frame_t frame;
    uint16_t nb = sc_frame_encode(bad, 1u, SC_CMD_DRIVE, payload, 2u);
    uint16_t ng = sc_frame_encode(good, 2u, SC_CMD_STOP, NULL, 0u);

    bad[nb - 1u] ^= 0xFFu;
    sc_decoder_init(&dec);
    sc_decoder_push(&dec, bad, nb);
    sc_decoder_push(&dec, good, ng);
    SC_CHECK(sc_decoder_next(&dec, &frame));
    SC_CHECK_EQ(frame.seq, 2);
}

static void test_implausible_length_does_not_wedge(void)
{
    /* A stray SOF followed by LEN=0 is not a header. The decoder must skip it
     * rather than waiting forever for a frame that will never arrive. */
    static const uint8_t junk[] = { SC_SOF, 0x00 };
    uint8_t out[SC_MAX_FRAME];
    sc_decoder_t dec;
    sc_frame_t frame;
    uint16_t n = sc_frame_encode(out, 6u, SC_CMD_PING, NULL, 0u);

    sc_decoder_init(&dec);
    sc_decoder_push(&dec, junk, sizeof(junk));
    sc_decoder_push(&dec, out, n);
    SC_CHECK(sc_decoder_next(&dec, &frame));
    SC_CHECK_EQ(frame.seq, 6);
}

static void test_truncated_frame_completes_later(void)
{
    static const uint8_t payload[] = { 0x01, 0x02 };
    uint8_t out[SC_MAX_FRAME];
    sc_decoder_t dec;
    sc_frame_t frame;
    uint16_t n = sc_frame_encode(out, 4u, SC_CMD_DRIVE, payload, 2u);

    sc_decoder_init(&dec);
    sc_decoder_push(&dec, out, 5u);
    SC_CHECK(!sc_decoder_next(&dec, &frame));
    sc_decoder_push(&dec, &out[5], (uint16_t)(n - 5u));
    SC_CHECK(sc_decoder_next(&dec, &frame));
    SC_CHECK_EQ(frame.seq, 4);
}

static void test_multiple_frames_in_one_push(void)
{
    uint8_t buf[SC_MAX_FRAME * 5u];
    uint16_t total = 0u;
    uint8_t i;
    sc_decoder_t dec;
    sc_frame_t frame;
    int count = 0;

    for (i = 0u; i < 5u; i++) {
        total = (uint16_t)(total +
                 sc_frame_encode(&buf[total], i, SC_CMD_KEEPALIVE, NULL, 0u));
    }
    sc_decoder_init(&dec);
    sc_decoder_push(&dec, buf, total);
    while (sc_decoder_next(&dec, &frame)) {
        SC_CHECK_EQ(frame.seq, count);
        count++;
    }
    SC_CHECK_EQ(count, 5);
}

static void test_buffer_is_bounded_against_noise(void)
{
    uint8_t noise[SC_DECODER_BUFFER];
    uint8_t out[SC_MAX_FRAME];
    sc_decoder_t dec;
    sc_frame_t frame;
    uint16_t n;
    int i;

    memset(noise, 0, sizeof(noise));
    sc_decoder_init(&dec);
    for (i = 0; i < 100; i++) {
        sc_decoder_push(&dec, noise, (uint16_t)sizeof(noise));
    }
    SC_CHECK(dec.len <= SC_DECODER_BUFFER);

    /* A good frame still decodes after all that. */
    n = sc_frame_encode(out, 1u, SC_CMD_PING, NULL, 0u);
    sc_decoder_push(&dec, out, n);
    while (sc_decoder_next(&dec, &frame)) {
        SC_CHECK_EQ(frame.type, SC_CMD_PING);
    }
}

static void test_payload_size_limits(void)
{
    uint8_t out[SC_MAX_FRAME];
    static uint8_t big[SC_MAX_PAYLOAD + 2u];

    /* The largest legal payload encodes; one byte more is refused rather than
     * silently truncated. */
    SC_CHECK_EQ(sc_frame_encode(out, 1u, SC_EVT_TELEMETRY, big, SC_MAX_PAYLOAD),
                SC_MAX_PAYLOAD + 6u);
    SC_CHECK_EQ(sc_frame_encode(out, 1u, SC_EVT_TELEMETRY, big,
                                (uint8_t)(SC_MAX_PAYLOAD + 1u)), 0);
}

/* -- Telemetry ---------------------------------------------------------- */

static void test_telemetry_roundtrip(void)
{
    sc_telemetry_t in;
    sc_telemetry_t out;
    uint8_t buf[SC_TELEMETRY_SIZE];

    in.distance_mm[0] = 1u;
    in.distance_mm[1] = SC_DISTANCE_FAULT;
    in.distance_mm[2] = 65534u;
    in.gas_raw = 4095u;
    in.servo_deg = 180u;
    in.duty_left = -100;   /* signed round-trip is the interesting part */
    in.duty_right = 100;
    in.flags = SC_FLAG_MOVING | SC_FLAG_ARMED;
    in.faults = SC_FAULT_COMM_LOST | SC_FAULT_SENSOR_2;
    in.uptime_ms = 0xDEADBEEFu;

    SC_CHECK(sc_telemetry_encode(&in, buf, SC_TELEMETRY_SIZE));
    SC_CHECK(sc_telemetry_decode(&out, buf, SC_TELEMETRY_SIZE));
    SC_CHECK_EQ(out.distance_mm[1], SC_DISTANCE_FAULT);
    SC_CHECK_EQ(out.duty_left, -100);
    SC_CHECK_EQ(out.duty_right, 100);
    SC_CHECK_EQ(out.faults, SC_FAULT_COMM_LOST | SC_FAULT_SENSOR_2);
    SC_CHECK_EQ(out.uptime_ms, (long)0xDEADBEEFu);
}

static void test_telemetry_rejects_wrong_size(void)
{
    sc_telemetry_t t;
    uint8_t buf[SC_TELEMETRY_SIZE];
    memset(&t, 0, sizeof(t));
    SC_CHECK(!sc_telemetry_encode(&t, buf, 17u));
    SC_CHECK(!sc_telemetry_decode(&t, buf, 19u));
}

void run_protocol_tests(void)
{
    SC_RUN(test_crc_check_value);
    SC_RUN(test_golden_cmd_stop);
    SC_RUN(test_golden_cmd_drive_forward);
    SC_RUN(test_golden_cmd_drive_left);
    SC_RUN(test_golden_cmd_keepalive);
    SC_RUN(test_golden_cmd_servo);
    SC_RUN(test_golden_evt_ack);
    SC_RUN(test_golden_evt_telemetry);
    SC_RUN(test_roundtrip);
    SC_RUN(test_byte_at_a_time);
    SC_RUN(test_garbage_prefix_is_discarded);
    SC_RUN(test_sof_inside_payload_survives);
    SC_RUN(test_corrupted_crc_is_rejected);
    SC_RUN(test_recovers_after_a_corrupted_frame);
    SC_RUN(test_implausible_length_does_not_wedge);
    SC_RUN(test_truncated_frame_completes_later);
    SC_RUN(test_multiple_frames_in_one_push);
    SC_RUN(test_buffer_is_bounded_against_noise);
    SC_RUN(test_payload_size_limits);
    SC_RUN(test_telemetry_roundtrip);
    SC_RUN(test_telemetry_rejects_wrong_size);
}
