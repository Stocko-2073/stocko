idf_component_register(SRCS "cmds.c"
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES console esp_system esp_timer log
                                     drive settings sysinfo battery ulog net ble)
