# U-BOT base firmware. ESP-IDF v6.1, XIAO ESP32-C6.
cmake_minimum_required(VERSION 3.16)

# Every module lives in components/ so it can be built, read and replaced on
# its own. main/ is only the boot order.
set(EXTRA_COMPONENT_DIRS ${CMAKE_CURRENT_LIST_DIR}/components)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(ubot_base)
