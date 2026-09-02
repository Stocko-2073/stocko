idf_component_register(SRCS "battery.c"
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES esp_adc esp_driver_gpio esp_timer log settings)
