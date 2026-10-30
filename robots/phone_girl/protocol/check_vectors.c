// Builds the golden frames of phone_girl.protocol.vectors() with the C header and
// prints them as hex, one "name hex" line each, for sim/tests/test_protocol.py.
#include <stdio.h>
#include <string.h>

#include "phone_girl_link.h"

static void print(const char *name, const void *data, size_t size) {
  printf("%s ", name);
  for (size_t i = 0; i < size; i++) printf("%02x", ((const uint8_t *)data)[i]);
  printf("\n");
}

int main(void) {
  pgl_state_t state = {.version = PGL_VERSION, .flags = PGL_TORQUE_ON | PGL_COMMAND_FRESH, .seq = 0xBEEF,
                       .read_us = 0x12345678, .command_seq = 0xBEEE, .command_latency = 163, .bus_mv = 3912,
                       .slot = 5, .temperature_c = -3, .hardware_error = 0x20, .bus_errors = 1};
  for (int i = 0; i < PGL_SERVOS; i++) {
    state.servos[i] = (pgl_servo_t){.position = -1000 + 117 * i, .velocity = (i % 2 ? -1 : 1) * 3 * i,
                                     .current = -500 + 61 * i, .pwm = -885 + 104 * i};
  }
  print("state", &state, sizeof state);

  pgl_command_t command = {.version = PGL_VERSION, .flags = PGL_HOLD, .seq = 0xBEEE, .state_seq = 0xBEED};
  for (int i = 0; i < PGL_SERVOS; i++) command.goals[i] = -2047 + 255 * i;
  print("command", &command, sizeof command);

  uint8_t buffer[64];
  pgl_capture_t *capture = (pgl_capture_t *)buffer;
  *capture = (pgl_capture_t){.version = PGL_VERSION, .slot = 3, .count = 4, .seq = 7, .start_us = 0xCAFEF00D,
                             .period_us = 1000};
  for (int i = 0; i < 4; i++) {
    capture->samples[i] = (pgl_sample_t){.goal = 10 * i, .position = 10 * i - 3, .velocity = -i,
                                         .current = 20 * i, .pwm = -50 * i};
  }
  print("capture", buffer, sizeof(pgl_capture_t) + 4 * sizeof(pgl_sample_t));

  struct __attribute__((packed)) {
    pgl_control_t head;
    pgl_safety_t safety;
  } control = {{PGL_SAFETY, 9}, {.hold_ms = 300, .after = 1, .freeze_ms = 2000}};
  print("control", &control, sizeof control);

  struct __attribute__((packed)) {
    pgl_reply_t head;
    int32_t offsets[PGL_SERVOS];
  } reply = {{PGL_CALIBRATE_HOME | 0x80, 4, PGL_OK}};
  for (int i = 0; i < PGL_SERVOS; i++) reply.offsets[i] = i - 8;
  print("reply", &reply, sizeof reply);
  printf("ports %d,%d,%d,%d,%d\n", PGL_STATE_PORT, PGL_COMMAND_PORT, PGL_CONTROL_PORT, PGL_INFO_PORT,
         PGL_CAPTURE_PORT);
  return 0;
}
