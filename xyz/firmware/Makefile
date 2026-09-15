ARDUINO_CLI ?= arduino-cli
NODE ?= node
FQBN := esp32:esp32:XIAO_ESP32C6:CDCOnBoot=cdc
PORT ?= /dev/cu.usbmodem2101
BUILD := $(CURDIR)/build

.PHONY: compile upload monitor boards test crash crash-dump crash-clear
test:
	mkdir -p "$(BUILD)"
	$(CXX) -std=c++17 -Wall -Wextra -Werror -Itests tests/firmware_test.cpp -o "$(BUILD)/firmware_test"
	"$(BUILD)/firmware_test"
	$(CXX) -std=c++17 -Wall -Wextra -Werror -Itests tests/web_control_test.cpp -o "$(BUILD)/web_control_test"
	"$(BUILD)/web_control_test"
	$(NODE) tests/web_page_test.js
compile:
	$(ARDUINO_CLI) compile --fqbn $(FQBN) --build-path "$(BUILD)" xyza
upload: compile
	$(ARDUINO_CLI) upload --fqbn $(FQBN) --port $(PORT) --input-dir "$(BUILD)" xyza
monitor:
	$(ARDUINO_CLI) monitor --port $(PORT) --config baudrate=115200
boards:
	$(ARDUINO_CLI) board list
crash:
	python3 tests/crash_dump.py --port $(PORT)
crash-dump:
	python3 tests/crash_dump.py dump --port $(PORT)
crash-clear:
	python3 tests/crash_dump.py clear --port $(PORT)
