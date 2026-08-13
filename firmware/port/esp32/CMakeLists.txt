# ESP-IDF project for the Smart Car motion MCU.
#
#   cd firmware/port/esp32
#   idf.py set-target esp32
#   idf.py build
#   idf.py -p COMx flash monitor
#
# The portable core under firmware/core/ is shared with the host test build;
# run those first (see firmware/README.md) -- they cover the protocol and the
# motion-safety rules, which is everything that is dangerous to get wrong.

cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(smart_car_mcu)
