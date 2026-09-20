idf_component_register(SRCS "ulog.c"
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES log esp_ringbuf freertos esp_system)

target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=esp_panic_handler")
