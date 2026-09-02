idf_component_register(SRCS "main.c"
                       PRIV_REQUIRES nvs_flash app_update esp_timer
                                     settings ulog drive battery sysinfo
                                     console_cmds net ble)
