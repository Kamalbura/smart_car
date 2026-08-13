# The portable core is compiled straight into this component rather than
# vendored, so the ESP32 build and the host test build share one copy of the
# protocol and safety logic. A change that breaks the tests breaks the
# firmware too, which is the point.
set(SC_CORE "${CMAKE_CURRENT_LIST_DIR}/../../../core")

idf_component_register(
    SRCS
        "main.c"
        "drv_actuators.c"
        "drv_sonar.c"
        "${SC_CORE}/sc_protocol.c"
        "${SC_CORE}/sc_safety.c"
    INCLUDE_DIRS
        "."
        "${SC_CORE}/include"
    REQUIRES
        driver
        esp_adc
        esp_timer
        esp_system
)
