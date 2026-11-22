#include "madlink.hpp"
#include <cstdlib>
#include <iostream>
#include <new>
// Separate executable: fault injection affects only this test process.
static bool fail_allocation = false;
void* operator new(std::size_t size) {
    if (fail_allocation) throw std::bad_alloc();
    if (auto p = std::malloc(size ? size : 1)) return p;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
struct Clock : madlink::Clock { std::uint64_t now_ms() const noexcept override { return 0; } };
struct Random : madlink::Random { std::uint64_t next() noexcept override { return 0; } };
struct Wire : madlink::Transport {
    std::uint64_t generation = 0; bool ready = false;
    bool accept_and_fail_event_allocation = false;
    unsigned accepted = 0;
    void connect(const std::string&, std::uint64_t g) noexcept override { generation = g; ready = true; }
    void close() noexcept override {}
    std::optional<madlink::WireEvent> poll() override {
        if (!ready) return {};
        ready = false;
        return madlink::WireEvent{madlink::WireEvent::Kind::connected, generation, {}};
    }
    madlink::WriteResult write(const madlink::Bytes&) noexcept override {
        if (!accept_and_fail_event_allocation) return madlink::WriteResult::blocked;
        ++accepted;
        fail_allocation = true;
        return madlink::WriteResult::accepted;
    }
};
int send_insertion_failure() {
    Clock clock; Random random; Wire wire; madlink::Config cfg;
    cfg.max_messages = 2048; cfg.max_bytes = 2048;
    madlink::Client client(wire, clock, random, cfg);
    client.connect("test"); client.tick();
    bool saw_failure = false;
    for (unsigned i = 0; i < 2048; ++i) {
        madlink::Bytes payload{1};
        const auto before = client.queued_bytes();
        fail_allocation = true;
        try { client.send(std::move(payload), 100); }
        catch (const std::bad_alloc&) { saw_failure = true; }
        fail_allocation = false;
        if (saw_failure) {
            if (client.queued_bytes() != before) {
                std::cerr << "FAIL: allocation failure corrupted queued byte accounting\n";
                return 1;
            }
            break;
        }
    }
    if (!saw_failure) return 2;
    client.close();
    if (client.queued_bytes() != 0) return 3;
    std::cout << "PASS: send allocation failure preserves byte accounting\n";
    return 0;
}
int accepted_write_event_failure() {
    Clock clock; Random random; Wire wire;
    madlink::Client client(wire, clock, random);
    client.connect("test"); client.tick();
    wire.accept_and_fail_event_allocation = true;
    bool saw_failure = false;
    for (unsigned i = 0; i < 2048; ++i) {
        if (client.send({1}, 100).error != madlink::Error::none) return 4;
        try { client.tick(); }
        catch (const std::bad_alloc&) { saw_failure = true; }
        fail_allocation = false;
        if (saw_failure) {
            const auto accepted = wire.accepted;
            // Restore allocation and retry tick, as an embedding caller may do.
            wire.accept_and_fail_event_allocation = false;
            if (client.queued_bytes() != 0) {
                std::cerr << "FAIL: accepted write remains queued after event allocation failure\n";
                return 5;
            }
            wire.accept_and_fail_event_allocation = true;
            client.tick();
            fail_allocation = false;
            if (wire.accepted != accepted) return 6;
            break;
        }
    }
    if (!saw_failure) return 7;
    std::cout << "PASS: event allocation failure cannot replay an accepted write\n";
    return 0;
}
int main() {
    const auto first = send_insertion_failure();
    return first ? first : accepted_write_event_failure();
}
