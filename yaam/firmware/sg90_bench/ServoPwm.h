#pragma once
#include <Arduino.h>
#include <hardware/clocks.h>
#include <hardware/gpio.h>
#include <hardware/irq.h>
#include <hardware/pwm.h>

#include "Link.h"

// Servo pulses from one hardware PWM slice counting 1 us ticks. The slice runs
// from boot to power-off; every wrap starts a frame. Both the compare level
// (the pulse width) and TOP (the frame period) are double-buffered and latch
// at the wrap, so the wrap interrupt always sets up the NEXT frame and the
// pulse on the wire was settled a whole frame earlier -- nothing ever changes
// mid-pulse, whatever USB or the sampler are doing.
//
// Between runs every frame carries the idle width (0 = no pulse, which leaves
// an analog servo limp). A run plays a preloaded schedule, one width per frame,
// then switches to its end width.
class ServoPwm {
  public:
    static constexpr uint32_t CAPACITY = 32768;
    static constexpr uint16_t MIN_US = 400;
    static constexpr uint16_t MAX_US = 2600;
    static constexpr uint16_t MIN_FRAME_US = 2700;   // longest pulse plus a gap

    void begin(TxRing &ring, uint pin, uint16_t frameUs) {
        ring_ = &ring;
        slice_ = pwm_gpio_to_slice_num(pin);
        chan_ = pwm_gpio_to_channel(pin);
        frameUs_ = frameUs;
        gpio_set_function(pin, GPIO_FUNC_PWM);
        pwm_config c = pwm_get_default_config();
        pwm_config_set_clkdiv(&c, (float)clock_get_hz(clk_sys) / 1e6f);
        pwm_config_set_wrap(&c, frameUs - 1);
        pwm_init(slice_, &c, false);
        pwm_set_chan_level(slice_, chan_, 0);
        self_ = this;
    }

    // Call on core 1: the wrap interrupt is serviced by the core that enables it.
    void start() {
        pwm_clear_irq(slice_);
        pwm_set_irq_enabled(slice_, true);
        irq_set_exclusive_handler(PWM_IRQ_WRAP, onWrapIrq);
        irq_set_enabled(PWM_IRQ_WRAP, true);
        pwm_set_enabled(slice_, true);
    }

    // --- commands from core 0 ---

    static bool validWidth(uint16_t us) { return us == 0 || (us >= MIN_US && us <= MAX_US); }
    bool running() const { return running_ || runRequest_; }

    uint8_t clearSchedule() {
        if (running()) return proto::ERR_BUSY;
        loaded_ = 0;
        return proto::OK;
    }

    uint8_t loadSchedule(uint32_t offset, const uint16_t *w, uint16_t n) {
        if (running()) return proto::ERR_BUSY;
        if (offset > loaded_ || offset + n > CAPACITY) return proto::ERR_RANGE;
        for (uint16_t i = 0; i < n; i++)
            if (!validWidth(w[i])) return proto::ERR_RANGE;
        memcpy(sched_ + offset, w, n * sizeof(uint16_t));
        if (offset + n > loaded_) loaded_ = offset + n;
        return proto::OK;
    }

    uint8_t run(uint32_t frames, uint16_t endUs) {
        if (running()) return proto::ERR_BUSY;
        if (!validWidth(endUs)) return proto::ERR_RANGE;
        if (frames == 0 || frames > loaded_) return frames ? proto::ERR_RANGE : proto::ERR_EMPTY;
        runFrames_ = frames;
        endUs_ = endUs;
        __dmb();
        runRequest_ = true;
        return proto::OK;
    }

    void stop() { stopRequest_ = true; }

    uint8_t setIdle(uint16_t us) {
        if (!validWidth(us)) return proto::ERR_RANGE;
        idleUs_ = us;
        return proto::OK;
    }

    uint8_t setFrame(uint16_t us) {
        if (running()) return proto::ERR_BUSY;
        if (us < MIN_FRAME_US) return proto::ERR_RANGE;
        pendingFrameUs_ = us;
        return proto::OK;
    }

    void setStreaming(bool on) { streaming_ = on; }

    uint16_t frameUs() const { return frameUs_; }
    uint16_t idleUs() const { return idleUs_; }
    uint32_t measuredFrameUs() const { return lastPeriodUs_; }

  private:
    static void onWrapIrq() { self_->onWrap(); }

    void onWrap() {
        pwm_clear_irq(slice_);
        uint32_t now = time_us_32();
        if (frame_) lastPeriodUs_ = now - lastWrapUs_;
        lastWrapUs_ = now;

        // The frame starting now carries what was written at the last wrap.
        if (streaming_) {
            proto::Frame f = {frame_, now, nextUs_, nextIdx_};
            ring_->put(proto::FRAME, &f, sizeof f);
        }
        if (finishing_) {
            proto::RunDone d = {now, sent_, stopped_};
            ring_->put(proto::RUN_DONE, &d, sizeof d);
            finishing_ = false;
        }
        frame_++;

        // Choose the frame after this one.
        if (runRequest_ && !running_) {
            running_ = true;
            runRequest_ = false;
            idx_ = 0;
            sent_ = 0;
            stopped_ = 0;
        }
        if (running_ && stopRequest_) stopped_ = 1;
        stopRequest_ = false;
        uint16_t w;
        int32_t idx;
        if (running_ && !stopped_ && idx_ < runFrames_) {
            w = sched_[idx_];
            idx = (int32_t)idx_++;
            sent_++;
        } else {
            if (running_) {
                running_ = false;
                idleUs_ = endUs_;
                finishing_ = true;
            }
            w = idleUs_;
            idx = -1;
        }
        pwm_set_chan_level(slice_, chan_, w);
        nextUs_ = w;
        nextIdx_ = idx;

        if (pendingFrameUs_ && !running_) {
            pwm_set_wrap(slice_, pendingFrameUs_ - 1);
            frameUs_ = pendingFrameUs_;
            pendingFrameUs_ = 0;
        }
    }

    static inline ServoPwm *self_ = nullptr;
    TxRing *ring_ = nullptr;
    uint slice_ = 0, chan_ = 0;

    uint16_t sched_[CAPACITY];
    volatile uint32_t loaded_ = 0;
    volatile uint32_t runFrames_ = 0;
    volatile uint16_t endUs_ = 0;
    volatile uint16_t idleUs_ = 0;
    volatile uint16_t frameUs_ = 20000;
    volatile uint16_t pendingFrameUs_ = 0;
    volatile bool runRequest_ = false;
    volatile bool stopRequest_ = false;
    volatile bool streaming_ = false;

    // Owned by the interrupt.
    volatile bool running_ = false;
    bool finishing_ = false;
    uint8_t stopped_ = 0;
    uint32_t idx_ = 0, sent_ = 0, frame_ = 0;
    uint16_t nextUs_ = 0;
    int32_t nextIdx_ = -1;
    uint32_t lastWrapUs_ = 0;
    volatile uint32_t lastPeriodUs_ = 0;
};
