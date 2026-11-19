#pragma once
#include "madlink.hpp"
#include <memory>
namespace madlink {
// Optional target only. Caller owns curl_global_init/cleanup around ALL adapters.
// Owner-thread-only, like Core. WSS + binary messages only; no credentials/proxy.
class CurlTransport final : public Transport {
public:
    struct Options {
        std::string ca_file; // Empty = system trust store. Never disables validation.
        std::size_t max_message_bytes = 65536;
        std::uint64_t flush_timeout_ms = 5000; // Absolute local acceptance-to-flush cap.
    };
    explicit CurlTransport(Options);
    ~CurlTransport() override;
    void connect(const std::string&, std::uint64_t) noexcept override;
    void close() noexcept override;
    std::optional<WireEvent> poll() override;
    // accepted = copied to one local frame slot, NOT flushed/received/acknowledged.
    // blocked = slot occupied, NO bytes from this new message touched the network.
    WriteResult write(const Bytes&) noexcept override;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
