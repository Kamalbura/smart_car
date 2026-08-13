/*
 * Motion-safety conformance vectors.
 *
 * These mirror src/tests/test_uart_safety.py one-for-one. If the two suites
 * ever disagree, the MCU and the Pi have diverged about when the robot is
 * allowed to move, and the MCU wins -- so fix the C.
 *
 * Several cases are named for the original firmware defect they lock out.
 */
#include "sc_safety.h"
#include "sc_test.h"

static const uint16_t CLEAR[3]   = { 2000u, 2000u, 2000u };
static const uint16_t WARN[3]    = { 150u, 2000u, 2000u };
static const uint16_t BLOCKED[3] = { 50u, 2000u, 2000u };
static const uint16_t LOST[3]    = { SC_DISTANCE_FAULT, SC_DISTANCE_FAULT,
                                     SC_DISTANCE_FAULT };

static void fresh(sc_safety_t *s)
{
    sc_safety_init(s, NULL);
    sc_safety_update_sensors(s, CLEAR);
    sc_safety_on_valid_frame(s, 0u);
}

static bool moving(sc_decision_t d)
{
    return (d.left != 0) || (d.right != 0);
}

/* -- Normal operation --------------------------------------------------- */

static void test_clear_road_allows_full_duty(void)
{
    sc_safety_t s;
    sc_decision_t d;
    fresh(&s);
    d = sc_safety_request_drive(&s, 100, 100);
    SC_CHECK_EQ(d.left, 100);
    SC_CHECK_EQ(d.right, 100);
    SC_CHECK_EQ(d.status, SC_ACK_OK);
}

static void test_stop_is_always_accepted(void)
{
    sc_safety_t s;
    sc_decision_t d;
    fresh(&s);
    sc_safety_update_sensors(&s, BLOCKED);
    d = sc_safety_request_drive(&s, 0, 0);
    SC_CHECK(!moving(d));
    SC_CHECK_EQ(d.status, SC_ACK_OK);
}

/* -- Obstacle gating ---------------------------------------------------- */

static void test_forward_refused_inside_stop_zone(void)
{
    sc_safety_t s;
    sc_decision_t d;
    fresh(&s);
    sc_safety_update_sensors(&s, BLOCKED);
    d = sc_safety_request_drive(&s, 100, 100);
    SC_CHECK(!moving(d));
    SC_CHECK_EQ(d.status, SC_ACK_REFUSED_OBSTACLE);
}

static void test_forward_throttled_in_warning_band(void)
{
    sc_safety_t s;
    sc_decision_t d;
    fresh(&s);
    sc_safety_update_sensors(&s, WARN);
    d = sc_safety_request_drive(&s, 100, 100);
    SC_CHECK_EQ(d.status, SC_ACK_CLAMPED);
    SC_CHECK_EQ(d.left, s.limits.warn_duty);
}

static void test_rotation_survives_stop_zone_but_slowly(void)
{
    /* You must be able to turn out of a corner. The old firmware consulted its
     * obstacle flags only in the FORWARD branch, so rotation ran at full duty
     * at zero distance; gating it entirely would trap the robot instead. */
    sc_safety_t s;
    sc_decision_t d;
    fresh(&s);
    sc_safety_update_sensors(&s, BLOCKED);
    d = sc_safety_request_drive(&s, -100, 100);
    SC_CHECK_EQ(d.status, SC_ACK_CLAMPED);
    SC_CHECK_EQ(d.left, -s.limits.escape_duty);
    SC_CHECK_EQ(d.right, s.limits.escape_duty);
}

static void test_reverse_capped_even_on_clear_road(void)
{
    /* There is no rear sensor, so reverse is blind at every distance. */
    sc_safety_t s;
    sc_decision_t d;
    fresh(&s);
    d = sc_safety_request_drive(&s, -100, -100);
    SC_CHECK_EQ(d.status, SC_ACK_CLAMPED);
    SC_CHECK_EQ(d.left, -s.limits.reverse_duty);
}

static void test_reverse_permitted_inside_stop_zone(void)
{
    sc_safety_t s;
    sc_decision_t d;
    fresh(&s);
    sc_safety_update_sensors(&s, BLOCKED);
    d = sc_safety_request_drive(&s, -100, -100);
    SC_CHECK(moving(d));
    SC_CHECK(d.left < 0);
}

/* -- Sensors fail closed ------------------------------------------------ */

static void test_single_dropped_echo_is_tolerated(void)
{
    /* One miss is normal on an HC-SR04; reacting to it would make the robot
     * undriveable. */
    static const uint16_t one_miss[3] = { SC_DISTANCE_FAULT, 2000u, 2000u };
    sc_safety_t s;
    fresh(&s);
    sc_safety_update_sensors(&s, one_miss);
    SC_CHECK_EQ(sc_safety_request_drive(&s, 100, 100).status, SC_ACK_OK);
    SC_CHECK((s.faults & SC_FAULT_SENSOR_1) == 0u);
}

static void test_sensor_faults_after_repeated_timeouts(void)
{
    static const uint16_t one_miss[3] = { SC_DISTANCE_FAULT, 2000u, 2000u };
    sc_safety_t s;
    uint8_t i;
    fresh(&s);
    for (i = 0u; i < SC_SENSOR_FAULT_THRESHOLD; i++) {
        sc_safety_update_sensors(&s, one_miss);
    }
    SC_CHECK((s.faults & SC_FAULT_SENSOR_1) != 0u);
    /* The other two still see clear road, so motion continues. */
    SC_CHECK_EQ(sc_safety_request_drive(&s, 100, 100).status, SC_ACK_OK);
}

static void test_recovered_sensor_clears_its_fault(void)
{
    static const uint16_t one_miss[3] = { SC_DISTANCE_FAULT, 2000u, 2000u };
    sc_safety_t s;
    uint8_t i;
    fresh(&s);
    for (i = 0u; i < SC_SENSOR_FAULT_THRESHOLD; i++) {
        sc_safety_update_sensors(&s, one_miss);
    }
    SC_CHECK((s.faults & SC_FAULT_SENSOR_1) != 0u);
    sc_safety_update_sensors(&s, CLEAR);
    SC_CHECK((s.faults & SC_FAULT_SENSOR_1) == 0u);
}

static void test_total_sensor_loss_blocks_forward(void)
{
    /* The headline inversion: no reading used to mean clear road. Unplug all
     * three on the old firmware and minDist stayed 9999, which took the CLEAR
     * branch and re-enabled the motors. */
    sc_safety_t s;
    sc_decision_t d;
    uint8_t i;
    fresh(&s);
    for (i = 0u; i < SC_SENSOR_FAULT_THRESHOLD; i++) {
        sc_safety_update_sensors(&s, LOST);
    }
    SC_CHECK(sc_safety_blind(&s));
    SC_CHECK((s.faults & SC_FAULT_ALL_SENSORS_LOST) != 0u);
    d = sc_safety_request_drive(&s, 100, 100);
    SC_CHECK(!moving(d));
    SC_CHECK_EQ(d.status, SC_ACK_REFUSED_OBSTACLE);
}

static void test_blind_still_allows_escape(void)
{
    sc_safety_t s;
    uint8_t i;
    fresh(&s);
    for (i = 0u; i < SC_SENSOR_FAULT_THRESHOLD; i++) {
        sc_safety_update_sensors(&s, LOST);
    }
    SC_CHECK(moving(sc_safety_request_drive(&s, -100, 100)));
}

/* -- The motion lease --------------------------------------------------- */

static void test_motion_persists_while_lease_renewed(void)
{
    sc_safety_t s;
    uint32_t now;
    fresh(&s);
    sc_safety_request_drive(&s, 100, 100);
    for (now = 0u; now < 5000u; now += 50u) {
        sc_safety_on_valid_frame(&s, now);
        SC_CHECK(moving(sc_safety_tick(&s, now)));
    }
}

static void test_motion_stops_when_lease_expires(void)
{
    sc_safety_t s;
    sc_decision_t d;
    fresh(&s);
    sc_safety_request_drive(&s, 100, 100);
    sc_safety_on_valid_frame(&s, 1000u);

    SC_CHECK(moving(sc_safety_tick(&s, 1000u + s.limits.command_timeout_ms)));
    d = sc_safety_tick(&s, 1000u + s.limits.command_timeout_ms + 1u);
    SC_CHECK(!moving(d));
    SC_CHECK((s.faults & SC_FAULT_COMM_LOST) != 0u);
}

static void test_lease_expiry_makes_a_dead_pi_safe(void)
{
    /* Unplugged cable, crashed orchestrator, `systemctl stop uart` -- all
     * reach the MCU as the same thing: silence. */
    sc_safety_t s;
    fresh(&s);
    sc_safety_request_drive(&s, 100, 100);
    sc_safety_on_valid_frame(&s, 0u);
    SC_CHECK(!moving(sc_safety_tick(&s, 10000u)));
}

static void test_comm_loss_clears_when_frames_return(void)
{
    sc_safety_t s;
    fresh(&s);
    sc_safety_request_drive(&s, 100, 100);
    sc_safety_on_valid_frame(&s, 0u);
    sc_safety_tick(&s, 10000u);
    SC_CHECK((s.faults & SC_FAULT_COMM_LOST) != 0u);
    sc_safety_on_valid_frame(&s, 10050u);
    SC_CHECK((s.faults & SC_FAULT_COMM_LOST) == 0u);
}

static void test_recovered_comms_do_not_resume_motion(void)
{
    /* A keepalive must never restart a robot the deadman stopped. Renewing the
     * lease proves the link is back; it is not a motion command. */
    sc_safety_t s;
    fresh(&s);
    sc_safety_request_drive(&s, 100, 100);
    sc_safety_on_valid_frame(&s, 0u);
    sc_safety_tick(&s, 10000u);
    sc_safety_on_valid_frame(&s, 10050u);
    SC_CHECK(!moving(sc_safety_tick(&s, 10060u)));
}

static void test_no_frame_ever_received_means_no_motion(void)
{
    sc_safety_t s;
    sc_safety_init(&s, NULL);
    sc_safety_update_sensors(&s, CLEAR);
    sc_safety_request_drive(&s, 100, 100);
    SC_CHECK(!moving(sc_safety_tick(&s, 0u)));
}

static void test_lease_survives_the_millisecond_wrap(void)
{
    /* uint32 ms wraps every ~49.7 days. Unsigned subtraction must keep the
     * elapsed-time comparison correct across it, or the robot brakes at the
     * wrap -- or worse, never brakes again. */
    sc_safety_t s;
    fresh(&s);
    sc_safety_request_drive(&s, 100, 100);
    sc_safety_on_valid_frame(&s, 0xFFFFFF00u);
    SC_CHECK(moving(sc_safety_tick(&s, 0xFFFFFF00u + 100u)));  /* wraps */
    SC_CHECK(!moving(sc_safety_tick(&s, 0xFFFFFF00u + 500u)));
}

/* -- Clearing faults ---------------------------------------------------- */

static void test_clear_fault_refused_with_obstacle(void)
{
    /* The CLEARBLOCK bug: clearing blind, then driving into the wall. */
    sc_safety_t s;
    fresh(&s);
    sc_safety_update_sensors(&s, BLOCKED);
    SC_CHECK_EQ(sc_safety_request_clear_fault(&s), SC_ACK_REFUSED_OBSTACLE);
    SC_CHECK_EQ(sc_safety_request_drive(&s, 100, 100).status,
                SC_ACK_REFUSED_OBSTACLE);
}

static void test_clear_fault_refused_while_blind(void)
{
    sc_safety_t s;
    uint8_t i;
    fresh(&s);
    for (i = 0u; i < SC_SENSOR_FAULT_THRESHOLD; i++) {
        sc_safety_update_sensors(&s, LOST);
    }
    SC_CHECK_EQ(sc_safety_request_clear_fault(&s), SC_ACK_REFUSED_FAULT);
}

static void test_clear_fault_succeeds_once_clear(void)
{
    sc_safety_t s;
    fresh(&s);
    sc_safety_update_sensors(&s, BLOCKED);
    SC_CHECK_EQ(sc_safety_request_clear_fault(&s), SC_ACK_REFUSED_OBSTACLE);
    sc_safety_update_sensors(&s, CLEAR);
    SC_CHECK_EQ(sc_safety_request_clear_fault(&s), SC_ACK_OK);
    SC_CHECK_EQ(s.faults, SC_FAULT_NONE);
}

void run_safety_tests(void)
{
    SC_RUN(test_clear_road_allows_full_duty);
    SC_RUN(test_stop_is_always_accepted);
    SC_RUN(test_forward_refused_inside_stop_zone);
    SC_RUN(test_forward_throttled_in_warning_band);
    SC_RUN(test_rotation_survives_stop_zone_but_slowly);
    SC_RUN(test_reverse_capped_even_on_clear_road);
    SC_RUN(test_reverse_permitted_inside_stop_zone);
    SC_RUN(test_single_dropped_echo_is_tolerated);
    SC_RUN(test_sensor_faults_after_repeated_timeouts);
    SC_RUN(test_recovered_sensor_clears_its_fault);
    SC_RUN(test_total_sensor_loss_blocks_forward);
    SC_RUN(test_blind_still_allows_escape);
    SC_RUN(test_motion_persists_while_lease_renewed);
    SC_RUN(test_motion_stops_when_lease_expires);
    SC_RUN(test_lease_expiry_makes_a_dead_pi_safe);
    SC_RUN(test_comm_loss_clears_when_frames_return);
    SC_RUN(test_recovered_comms_do_not_resume_motion);
    SC_RUN(test_no_frame_ever_received_means_no_motion);
    SC_RUN(test_lease_survives_the_millisecond_wrap);
    SC_RUN(test_clear_fault_refused_with_obstacle);
    SC_RUN(test_clear_fault_refused_while_blind);
    SC_RUN(test_clear_fault_succeeds_once_clear);
}
