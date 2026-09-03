# The drive stack: TMC2209 over UART, AS5600 encoders, the closed-loop servo,
# and the robot-frame layer with its control task. C++, exposed to the rest of
# the firmware through the C API in include/drive.h.
idf_component_register(SRCS "Tmc2209Uart.cpp" "I2cBus.cpp" "AS5600.cpp" "drive.cpp"
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES esp_driver_uart esp_driver_gpio esp_driver_i2c
                                     esp_timer esp_system freertos log settings)
