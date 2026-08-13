/* Minimal host test harness. No dependencies -- this has to build with
 * whatever compiler is around. */
#ifndef SC_TEST_H
#define SC_TEST_H

#include <stdio.h>

extern int sc_test_checks;
extern int sc_test_failed;

#define SC_CHECK(cond)                                                        \
    do {                                                                      \
        sc_test_checks++;                                                     \
        if (!(cond)) {                                                        \
            sc_test_failed++;                                                 \
            printf("    FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);        \
        }                                                                     \
    } while (0)

#define SC_CHECK_EQ(actual, expected)                                         \
    do {                                                                      \
        long a_ = (long)(actual);                                             \
        long e_ = (long)(expected);                                           \
        sc_test_checks++;                                                     \
        if (a_ != e_) {                                                       \
            sc_test_failed++;                                                 \
            printf("    FAIL %s:%d  %s: got %ld, expected %ld\n",             \
                   __FILE__, __LINE__, #actual, a_, e_);                      \
        }                                                                     \
    } while (0)

#define SC_RUN(fn)                                                            \
    do {                                                                      \
        int before_ = sc_test_failed;                                         \
        fn();                                                                 \
        printf("  %-58s %s\n", #fn,                                           \
               (sc_test_failed == before_) ? "ok" : "FAILED");                \
    } while (0)

void run_protocol_tests(void);
void run_safety_tests(void);

#endif /* SC_TEST_H */
