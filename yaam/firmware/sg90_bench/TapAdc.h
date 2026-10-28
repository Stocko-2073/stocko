#pragma once
#include <Arduino.h>
#include <hardware/adc.h>
#include <hardware/dma.h>

#include "Link.h"

// The three servo taps (motor terminal A, motor terminal B, pot wiper on
// ADC0..2) plus the RP2040's temperature sensor (input 4), sampled round-robin
// by the free-running ADC and moved by DMA into a ring that never stops. The
// sample count since boot is the clock for these: sample i comes from input
// [0, 1, 2, 4][i % 4], and each TICK records the count at its start so the
// host can place every sample in time.
class TapAdc {
  public:
    static constexpr uint32_t RATE_HZ = 80000;      // all four inputs; 20 kS/s each
    static constexpr uint32_t RING_LOG2 = 13;       // bytes: 8 kB, 4096 samples, ~51 ms
    static constexpr uint32_t N = 1u << (RING_LOG2 - 1);

    void begin() {
        adc_init();
        adc_gpio_init(26);
        adc_gpio_init(27);
        adc_gpio_init(28);
        adc_set_temp_sensor_enabled(true);
        adc_run(false);
        adc_select_input(0);
        adc_set_round_robin(0b10111);
        adc_fifo_setup(true, true, 1, false, false);
        // A conversion takes 96 of the 48 MHz cycles; the divider sets the period.
        adc_set_clkdiv(48000000.0f / RATE_HZ - 1.0f);
        adc_fifo_drain();

        chan_ = dma_claim_unused_channel(true);
        dma_channel_config c = dma_channel_get_default_config(chan_);
        channel_config_set_transfer_data_size(&c, DMA_SIZE_16);
        channel_config_set_read_increment(&c, false);
        channel_config_set_write_increment(&c, true);
        channel_config_set_ring(&c, true, RING_LOG2);   // write address wraps; needs the alignment below
        channel_config_set_dreq(&c, DREQ_ADC);
        // The longest transfer the DMA allows: 2^32 samples is 15 hours at 80 kS/s.
        dma_channel_configure(chan_, &c, ring_, &adc_hw->fifo, 0xFFFFFFFFu, true);
        adc_run(true);
    }

    // Samples written so far. The DMA counts down from 2^32 - 1.
    uint32_t index() const { return 0xFFFFFFFFu - dma_hw->ch[chan_].transfer_count; }

    // Means (x16) of each input over the samples since the last call. The
    // newest sample is left for next time in case its write is still in flight.
    void means(uint16_t out[4], uint8_t &n) {
        uint32_t end = index() - 1;
        uint32_t sum[4] = {0, 0, 0, 0}, cnt[4] = {0, 0, 0, 0};
        uint32_t i = meanIdx_;
        if (end - i > N) i = end - N;   // fell more than a ring behind: keep the newest
        for (; i < end; i++) {
            uint32_t k = i & 3;
            sum[k] += ring_[i & (N - 1)];
            cnt[k]++;
        }
        meanIdx_ = end;
        n = (uint8_t)(cnt[0] < 255 ? cnt[0] : 255);
        for (int k = 0; k < 4; k++) out[k] = cnt[k] ? (uint16_t)((sum[k] * 16 + cnt[k] / 2) / cnt[k]) : 0xFFFF;
    }

    // Raw samples since the last call, as TAPS messages of up to 256 samples.
    void streamRaw(TxRing &ring) {
        uint32_t end = index() - 1;
        if (end - rawIdx_ > N) rawIdx_ = end - N;
        uint16_t chunk[256];
        while (rawIdx_ < end) {
            uint16_t n = (uint16_t)((end - rawIdx_) < 256 ? (end - rawIdx_) : 256);
            for (uint16_t j = 0; j < n; j++) chunk[j] = ring_[(rawIdx_ + j) & (N - 1)];
            proto::TapsHead h = {rawIdx_, n};
            ring.put2(proto::TAPS, &h, sizeof h, chunk, (uint16_t)(n * 2));
            rawIdx_ += n;
        }
    }

    // Start raw streaming from now rather than replaying the backlog.
    void skipRaw() { rawIdx_ = index() - 1; }

  private:
    static inline uint16_t ring_[N] __attribute__((aligned(1u << RING_LOG2)));
    int chan_ = -1;
    uint32_t meanIdx_ = 0;
    uint32_t rawIdx_ = 0;
};
