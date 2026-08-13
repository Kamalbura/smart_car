# Host test build for the portable firmware core.
#
#   cmake -S firmware -B firmware/build -G Ninja
#   cmake --build firmware/build
#   firmware/build/sc_tests
#
# This builds for the development machine, not the target. It needs no ESP-IDF
# and no ARM toolchain -- just a C compiler, so the protocol and safety logic
# can be proven before it ever reaches hardware.
#
# The ESP32 firmware is a separate IDF project under port/esp32/ and reuses the
# same core/ sources unchanged.

cmake_minimum_required(VERSION 3.16)
project(smart_car_firmware_core C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(MSVC)
    add_compile_options(/W4)
else()
    # Deliberately strict: this code runs where a wrong implicit conversion
    # means the robot does not brake. -Werror is left off so a new compiler
    # version cannot block the build outright.
    add_compile_options(-Wall -Wextra -Wshadow -Wconversion -Wsign-conversion)
endif()

add_library(sc_core STATIC
    core/sc_protocol.c
    core/sc_safety.c
)
target_include_directories(sc_core PUBLIC core/include)

add_executable(sc_tests
    test/main.c
    test/test_protocol.c
    test/test_safety.c
)
target_link_libraries(sc_tests PRIVATE sc_core)
target_include_directories(sc_tests PRIVATE test)

enable_testing()
add_test(NAME sc_tests COMMAND sc_tests)
