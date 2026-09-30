idf_component_register(SRCS "battery.c" "battery_model.c"
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES esp_adc esp_driver_gpio esp_timer log settings)
