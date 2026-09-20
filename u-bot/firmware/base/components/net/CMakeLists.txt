idf_component_register(SRCS "wifi.c" "ws.c" "ota.c" "manage_ws.c"
                       INCLUDE_DIRS "include"
                       EMBED_TXTFILES "joystick.html"
                       PRIV_REQUIRES esp_wifi esp_netif esp_event esp_http_server esp_http_client
                                     bootloader_support esp_https_ota app_update esp_timer esp_system log mbedtls
                                     espressif__mdns espressif__cjson
                                     management drive settings sysinfo battery ulog)
