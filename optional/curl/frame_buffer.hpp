#pragma once
#include "madlink.hpp"
#include <stdexcept>
namespace madlink::curl_detail {
// Payload-size bounded, not a hard allocator/RSS limit. One owned frame at a time.
struct FrameBuffer {
    Bytes bytes;
    std::size_t offset = 0;
    bool occupied = false;
    bool started = false;
    bool put(const Bytes& data, std::size_t limit) {
        if (occupied || data.size() > limit) return false;
        bytes = data; offset = 0; occupied = true; started = false; return true;
    }
    void clear() noexcept { bytes.clear(); offset = 0; occupied = false; started = false; }
    void consumed(std::size_t count, bool success) {
        if (!occupied || count > bytes.size() - offset) throw std::logic_error("invalid send progress");
        // libcurl's CURLE_AGAIN contract requires retrying identical data/length.
        if (!success) { if (count) throw std::logic_error("unexpected AGAIN progress"); return; }
        started = true;
        offset += count;
        if (offset == bytes.size()) clear(); // Includes a successful empty frame.
    }
};
}
