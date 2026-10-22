#pragma once
#include <stdint.h>

#include <functional>

// The host tests' only time source. The generated esp_timer.h stub reads it,
// and the vTaskDelay / esp_rom_delay_us stubs advance it, so micros(),
// millis(), delayMs() and pumpYield() in platform.h all run on this clock.
//
// It never moves by itself. On the chip time passes while code runs; here it
// passes only when something waits. That is what makes a blocking routine
// testable: calibrate()'s pumps sleep a tick between 1 ms samples, and each of
// those sleeps is an advance() that the hook turns into plant motion, exactly
// as the real wheel keeps turning while the control task sleeps.
struct FakeClock {
    // Called with the interval each advance() covers, after the clock has
    // moved. A plant steps itself through it here.
    using Hook = std::function<void(int64_t fromUs, int64_t toUs)>;

    static int64_t now() { return us_; }

    // Jump without running the hook: for starting a test at an awkward time,
    // e.g. just before micros() wraps. Nothing is simulated across a jump.
    static void set(int64_t us) { us_ = us; }

    static void advance(int64_t us) {
        if (us <= 0) return;
        int64_t from = us_;
        us_ += us;
        // A hook that waits (or calls something that does) still moves the
        // clock, but must not re-enter itself: the outer call already covers
        // the whole interval, and a nested one would step the plant twice.
        if (!hook_ || inHook_) return;
        inHook_ = true;
        hook_(from, us_);
        inHook_ = false;
    }

    static void setHook(Hook h) { hook_ = std::move(h); }
    static void clearHook() { hook_ = nullptr; }
    static bool hooked() { return (bool)hook_; }

  private:
    static inline int64_t us_ = 0;
    static inline Hook hook_;
    static inline bool inHook_ = false;
};
