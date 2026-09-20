idf_component_register(SRCS "management.c"
 INCLUDE_DIRS "include"
 PRIV_REQUIRES drive ulog sysinfo net settings esp_timer esp_system app_update espressif__cjson)
