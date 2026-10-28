#pragma once
#include <Arduino.h>
#include <hardware/sync.h>
#include <string.h>

#include "Protocol.h"

// CRC-16/CCITT-FALSE, table driven: the sample stream is ~200 kB/s and a
// bitwise CRC would cost core 1 a noticeable slice of every tick.
class Crc16 {
  public:
    Crc16() {
        for (int i = 0; i < 256; i++) {
            uint16_t c = (uint16_t)(i << 8);
            for (int j = 0; j < 8; j++) c = (c & 0x8000) ? (uint16_t)((c << 1) ^ 0x1021) : (uint16_t)(c << 1);
            table_[i] = c;
        }
    }
    uint16_t update(uint16_t c, const uint8_t *d, size_t n) const {
        while (n--) c = (uint16_t)((c << 8) ^ table_[(uint8_t)((c >> 8) ^ *d++)]);
        return c;
    }

  private:
    uint16_t table_[256];
};

extern const Crc16 crc16;

// Everything bound for the host goes through this ring as whole, framed
// messages. Core 1's sample loop, the PWM wrap interrupt (also on core 1) and
// core 0's command handling all produce; core 0 alone drains it to USB. A
// hardware spinlock serialises the producers, and spin_lock_blocking() masks
// interrupts on the calling core, so the wrap interrupt can't land inside a
// put() that core 1's loop is part way through. The consumer only reads `head_`,
// which moves after a whole message is in place, so USB always gets whole
// messages back to back.
class TxRing {
  public:
    static constexpr uint32_t SIZE = 1u << 16;
    static constexpr uint32_t MASK = SIZE - 1;

    void begin() { lock_ = spin_lock_init(spin_lock_claim_unused(true)); }

    bool put(uint8_t type, const void *payload, uint16_t len) {
        return put2(type, payload, len, nullptr, 0);
    }

    // A message whose payload comes in two pieces (a header and an array),
    // without staging it in a buffer first.
    bool put2(uint8_t type, const void *a, uint16_t na, const void *b, uint16_t nb) {
        uint16_t len = (uint16_t)(na + nb);
        uint8_t head[4] = {proto::SYNC, type, (uint8_t)len, (uint8_t)(len >> 8)};
        uint16_t c = crc16.update(0xFFFF, head + 1, 3);
        c = crc16.update(c, (const uint8_t *)a, na);
        c = crc16.update(c, (const uint8_t *)b, nb);
        uint8_t tail[2] = {(uint8_t)c, (uint8_t)(c >> 8)};

        uint32_t irq = spin_lock_blocking(lock_);
        uint32_t need = 6u + len;
        if (SIZE - (head_ - tail_) < need) {
            drops_++;
            spin_unlock(lock_, irq);
            return false;
        }
        uint32_t h = head_;
        copyIn(h, head, 4);
        copyIn(h + 4, a, na);
        copyIn(h + 4 + na, b, nb);
        copyIn(h + 4 + len, tail, 2);
        __dmb();
        head_ = h + need;
        spin_unlock(lock_, irq);
        return true;
    }

    // Core 0: hand as much as USB will take to `out`. Returns bytes sent.
    template <typename Out>
    uint32_t drain(Out &out) {
        uint32_t sent = 0;
        for (;;) {
            uint32_t h = head_;
            __dmb();
            uint32_t t = tail_;
            if (t == h) break;
            uint32_t idx = t & MASK;
            uint32_t n = h - t;
            if (n > SIZE - idx) n = SIZE - idx;
            int room = out.availableForWrite();
            if (room <= 0) break;
            if (n > (uint32_t)room) n = (uint32_t)room;
            size_t w = out.write(buf_ + idx, n);
            tail_ = t + (uint32_t)w;
            sent += (uint32_t)w;
            if (w < n) break;
        }
        return sent;
    }

    // Throw away anything not yet sent, e.g. when the host goes away.
    void flush() {
        uint32_t irq = spin_lock_blocking(lock_);
        tail_ = head_;
        spin_unlock(lock_, irq);
    }

    uint32_t drops() const { return drops_; }

  private:
    void copyIn(uint32_t pos, const void *src, uint32_t n) {
        if (!n) return;
        uint32_t idx = pos & MASK;
        uint32_t first = n < SIZE - idx ? n : SIZE - idx;
        memcpy(buf_ + idx, src, first);
        if (first < n) memcpy(buf_, (const uint8_t *)src + first, n - first);
    }

    uint8_t buf_[SIZE];
    volatile uint32_t head_ = 0;
    volatile uint32_t tail_ = 0;
    volatile uint32_t drops_ = 0;
    spin_lock_t *lock_ = nullptr;
};

// Reassembles host commands from the USB byte stream, one byte at a time.
class RxParser {
  public:
    // Returns true when a whole, CRC-checked message is ready in type()/payload().
    bool feed(uint8_t b) {
        switch (state_) {
            case SYNC:
                if (b == proto::SYNC) state_ = TYPE;
                break;
            case TYPE:
                type_ = b;
                state_ = LEN0;
                break;
            case LEN0:
                len_ = b;
                state_ = LEN1;
                break;
            case LEN1:
                len_ |= (uint16_t)b << 8;
                n_ = 0;
                if (len_ > proto::MAX_PAYLOAD) state_ = SYNC;
                else state_ = len_ ? DATA : CRC0;
                break;
            case DATA:
                buf_[n_++] = b;
                if (n_ == len_) state_ = CRC0;
                break;
            case CRC0:
                crc_ = b;
                state_ = CRC1;
                break;
            case CRC1: {
                crc_ |= (uint16_t)b << 8;
                state_ = SYNC;
                uint8_t head[3] = {type_, (uint8_t)len_, (uint8_t)(len_ >> 8)};
                uint16_t c = crc16.update(crc16.update(0xFFFF, head, 3), buf_, len_);
                if (c == crc_) return true;
                badCrc_++;
                break;
            }
        }
        return false;
    }

    uint8_t type() const { return type_; }
    const uint8_t *payload() const { return buf_; }
    uint16_t length() const { return len_; }
    uint32_t badCrc() const { return badCrc_; }

  private:
    enum State { SYNC, TYPE, LEN0, LEN1, DATA, CRC0, CRC1 } state_ = SYNC;
    uint8_t type_ = 0;
    uint16_t len_ = 0, n_ = 0, crc_ = 0;
    uint32_t badCrc_ = 0;
    uint8_t buf_[proto::MAX_PAYLOAD];
};
