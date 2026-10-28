#pragma once
#include <Arduino.h>
#include <hardware/gpio.h>
#include <hardware/sync.h>

// HX711 load-cell ADC, channel A at gain 128. DT goes low when a conversion is
// ready (10 per second on most boards, 80 with RATE high). Reading clocks out
// 24 bits plus one extra pulse that selects channel A/128 for the next
// conversion. SCK held high for more than 60 us powers the chip down, so the
// whole read runs with interrupts masked.
class Hx711 {
  public:
    void begin(uint sck, uint dt) {
        sck_ = sck;
        dt_ = dt;
        gpio_init(sck_);
        gpio_set_dir(sck_, GPIO_OUT);
        gpio_put(sck_, 0);
        gpio_init(dt_);
        gpio_set_dir(dt_, GPIO_IN);
        gpio_pull_up(dt_);
    }

    bool ready() const { return !gpio_get(dt_); }

    int32_t read() {
        uint32_t v = 0;
        uint32_t irq = save_and_disable_interrupts();
        for (int i = 0; i < 25; i++) {
            gpio_put(sck_, 1);
            busy_wait_us_32(1);
            if (i < 24) v = (v << 1) | (uint32_t)gpio_get(dt_);
            gpio_put(sck_, 0);
            busy_wait_us_32(1);
        }
        restore_interrupts(irq);
        return (int32_t)(v << 8) >> 8;   // sign-extend 24 bits
    }

  private:
    uint sck_ = 0, dt_ = 0;
};
