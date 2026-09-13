ARDUINO_CLI ?= arduino-cli
FQBN := esp32:esp32:XIAO_ESP32C6:CDCOnBoot=cdc
PORT ?= /dev/cu.usbmodem2101
BUILD := $(CURDIR)/build

.PHONY: compile upload monitor boards test
test:
	mkdir -p "$(BUILD)"
	$(CXX) -std=c++17 -Wall -Wextra -Werror -Itests tests/firmware_test.cpp -o "$(BUILD)/firmware_test"
	"$(BUILD)/firmware_test"
compile:
	$(ARDUINO_CLI) compile --fqbn $(FQBN) --build-path "$(BUILD)" xyza
upload: compile
	$(ARDUINO_CLI) upload --fqbn $(FQBN) --port $(PORT) --input-dir "$(BUILD)" xyza
monitor:
	$(ARDUINO_CLI) monitor --port $(PORT) --config baudrate=115200
boards:
	$(ARDUINO_CLI) board list
