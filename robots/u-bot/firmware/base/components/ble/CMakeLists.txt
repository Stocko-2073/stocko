idf_component_register(SRCS "ble.c"
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES management bt esp_timer log drive battery sysinfo)
