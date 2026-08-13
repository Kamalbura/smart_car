/*
 * Host test runner for the portable firmware core.
 *
 *     cmake -S firmware -B firmware/build -G Ninja
 *     cmake --build firmware/build
 *     ./firmware/build/sc_tests
 *
 * These run on the development machine, not the target. They cover the two
 * pieces where a bug is dangerous rather than merely annoying: frame integrity
 * and the motion-safety rules. Register-level driver code is verified on the
 * bench instead.
 */
#include "sc_test.h"

int sc_test_checks = 0;
int sc_test_failed = 0;

int main(void)
{
    printf("protocol\n");
    run_protocol_tests();
    printf("safety\n");
    run_safety_tests();

    printf("\n%d checks, %d failed\n", sc_test_checks, sc_test_failed);
    if (sc_test_failed != 0) {
        printf("FAILED\n");
        return 1;
    }
    printf("OK\n");
    return 0;
}
