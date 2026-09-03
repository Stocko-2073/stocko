#pragma once
// The serial console: a linenoise REPL over the XIAO's USB port, with every
// command the firmware understands. `help` lists them.
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t console_start(void);

#ifdef __cplusplus
}
#endif
