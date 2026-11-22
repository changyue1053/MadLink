#include "madlink.hpp"
#include <cstdlib>
#include <functional>
#include <iostream>
#include <stdexcept>
using namespace madlink;
#define CHECK(x) do { if (!(x)) { std::cerr << __LINE__ << ": " #x "\n"; std::exit(1); } } while (false)
struct FakeClock final : Clock {
    mutable std::uint64_t time = 0;
    std::uint64_t step = 0;
    std::uint64_t now_ms() const noexcept override { auto value = time; time += step; return value; }
};
struct FakeRandom final : Random { std::uint64_t next() noexcept override { return 0; } };
struct FakeTransport final : Transport {
    std::uint64_t generation = 0;
    unsigned opens = 0, closes = 0;
    WriteResult result = WriteResult::accepted;
    std::deque<WireEvent> inbound;
    std::vector<Bytes> written;
    std::function<void()> on_poll, on_write;
    void connect(const std::string&, std::uint64_t gen) noexcept override { generation = gen; ++opens; }
    void close() noexcept override { ++closes; }
    std::optional<WireEvent> poll() override {
        if (on_poll) on_poll();
        if (inbound.empty()) return std::nullopt;
        auto e = std::move(inbound.front()); inbound.pop_front(); return e;
    }
    WriteResult write(const Bytes& bytes) noexcept override {
        if (on_write) on_write();
        if (result == WriteResult::accepted) written.push_back(bytes);
        return result;
    }
    void event(WireEvent::Kind kind, Bytes bytes = {}) { inbound.push_back({kind, generation, std::move(bytes)}); }
};
struct Sink final : TelemetrySink {
    unsigned calls = 0;
    void state_changed(State) noexcept override { ++calls; }
};
void connected(Client& c, FakeTransport& t) {
    CHECK(c.connect("test-endpoint") == Error::none);
    t.event(WireEvent::Kind::connected); c.tick();
    CHECK(c.state() == State::connected);
}
void drain(Client& c) { while (c.next_event()) {} }
void lifecycle() {
    FakeClock clock; FakeRandom random; FakeTransport wire;
    {
        Client c(wire, clock, random);
        CHECK(c.send({1}, 10).error == Error::invalid_state);
        connected(c, wire);
        CHECK(c.connect("other") == Error::invalid_state);
        drain(c);
        auto op = c.send({0, 255, 7}, 100);
        CHECK(op.error == Error::none); c.tick();
        auto e = c.next_event(); CHECK(e && e->kind == EventKind::written && e->operation == op.operation);
        CHECK(wire.written == std::vector<Bytes>({{0, 255, 7}}));
        wire.event(WireEvent::Kind::received, {4, 0}); c.tick();
        e = c.next_event(); CHECK(e && e->data == Bytes({4, 0}));
        c.close(); const auto closes = wire.closes; c.close(); CHECK(wire.closes == closes);
        wire.event(WireEvent::Kind::connected); drain(c); c.tick();
        CHECK(c.state() == State::closed && !c.next_event());
    }
    CHECK(wire.closes == 2);
}
void cancellation_and_bounds() {
    FakeClock clock; FakeRandom random; FakeTransport wire;
    Config cfg; cfg.max_messages = 2; cfg.max_bytes = 3;
    Client c(wire, clock, random, cfg); connected(c, wire); drain(c);
    wire.result = WriteResult::blocked;
    auto a = c.send({1, 2}, 100); auto b = c.send({3}, 10);
    CHECK(c.send({}, 100).error == Error::queue_full);
    c.tick(); CHECK(c.queued_bytes() == 3);
    CHECK(c.cancel(a.operation)); CHECK(!c.cancel(a.operation));
    CHECK(c.queued_bytes() == 1);
    clock.time = 10; c.tick(); CHECK(c.queued_bytes() == 0);
    auto e = c.next_event(); CHECK(e && e->error == Error::cancelled && e->operation == a.operation);
    e = c.next_event(); CHECK(e && e->error == Error::timeout && e->operation == b.operation);
    CHECK(c.send({1, 2, 3, 4}, 100).error == Error::queue_full);
    CHECK(c.send({}, 10).error == Error::timeout);
}
void timeout_retry_stale_events() {
    FakeClock clock; FakeRandom random; FakeTransport wire;
    Config cfg; cfg.connect_timeout_ms = 10; cfg.max_retries = 1;
    Client c(wire, clock, random, cfg); CHECK(c.connect("x") == Error::none);
    const auto old = wire.generation;
    clock.time = 10; c.tick(); CHECK(c.state() == State::backoff);
    wire.inbound.push_back({WireEvent::Kind::connected, old, {}});
    clock.time = 59; c.tick(); CHECK(wire.opens == 1);
    clock.time = 60; c.tick(); CHECK(wire.opens == 2 && c.state() == State::connecting);
    wire.event(WireEvent::Kind::connected); c.tick(); CHECK(c.state() == State::connected);
    wire.result = WriteResult::blocked; CHECK(c.send({1}, 200).error == Error::none);
    wire.event(WireEvent::Kind::disconnected); c.tick();
    CHECK(c.state() == State::closed && c.queued_bytes() == 0 && wire.written.empty());
}
void close_during_connect_and_reopen() {
    FakeClock clock; FakeRandom random; FakeTransport wire; Client c(wire, clock, random);
    CHECK(c.connect("x") == Error::none); const auto old = wire.generation;
    c.close(); CHECK(c.connect("y") == Error::none);
    wire.inbound.push_back({WireEvent::Kind::connected, old, {}});
    c.tick(); CHECK(c.state() == State::connecting);
    wire.event(WireEvent::Kind::connected); c.tick(); CHECK(c.state() == State::connected);
}
void failures_and_no_replay() {
    FakeClock clock; FakeRandom random; FakeTransport wire;
    Client c(wire, clock, random); connected(c, wire);
    CHECK(c.send({8}, 1000).error == Error::none);
    wire.result = WriteResult::failed; c.tick(); CHECK(c.state() == State::backoff);
    CHECK(c.queued_bytes() == 0);
    clock.time = 50; c.tick(); wire.event(WireEvent::Kind::connected); c.tick();
    wire.result = WriteResult::accepted; c.tick(); CHECK(wire.written.empty());
    wire.event(WireEvent::Kind::received, Bytes(65537)); c.tick(); CHECK(c.state() == State::backoff);
}
void isolation_and_optional_sink() {
    FakeClock clock; FakeRandom random; FakeTransport a, b; Sink sink;
    unsigned calls = 0;
    {
        Client ca(a, clock, random, {}, &sink), cb(b, clock, random);
        connected(ca, a); connected(cb, b); ca.close();
        CHECK(cb.state() == State::connected);
        CHECK(cb.send({9}, 100).error == Error::none); cb.tick();
        CHECK(a.written.empty() && b.written.size() == 1);
        calls = sink.calls;
    }
    CHECK(sink.calls == calls); // Destruction does not invoke observers.
}
void diagnostics_and_config() {
    FakeClock clock; FakeRandom random; FakeTransport wire;
    Config cfg; cfg.max_events = 1;
    Client c(wire, clock, random, cfg); connected(c, wire);
    CHECK(c.dropped_events() == 1);
    auto e = c.next_event(); CHECK(e && e->state == State::connected && !c.next_event());
    cfg.max_bytes = 0; bool threw = false;
    try { Client invalid(wire, clock, random, cfg); } catch (const std::invalid_argument&) { threw = true; }
    CHECK(threw);
}
void advancing_clock_retry() {
    FakeClock clock; FakeRandom random; FakeTransport wire;
    Config cfg; cfg.connect_timeout_ms = 10;
    Client c(wire, clock, random, cfg); CHECK(c.connect("x") == Error::none);
    clock.time = 10; c.tick(); CHECK(c.state() == State::backoff);
    clock.time = 60; clock.step = 1;
    c.tick();
    CHECK(wire.opens == 2);
    CHECK(c.state() == State::connecting);
}
void poll_crosses_send_deadline() {
    FakeClock clock; FakeRandom random; FakeTransport wire;
    Client c(wire, clock, random); connected(c, wire); drain(c);
    auto op = c.send({1}, 10); CHECK(op.error == Error::none);
    wire.on_poll = [&] { clock.time = 10; };
    c.tick();
    CHECK(wire.written.empty());
    auto e = c.next_event();
    CHECK(e && e->kind == EventKind::failed && e->error == Error::timeout && e->operation == op.operation);
}
void prior_write_crosses_next_deadline() {
    FakeClock clock; FakeRandom random; FakeTransport wire;
    Client c(wire, clock, random); connected(c, wire); drain(c);
    CHECK(c.send({1}, 100).error == Error::none);
    auto op = c.send({2}, 10); CHECK(op.error == Error::none);
    wire.on_write = [&] { clock.time = 10; };
    c.tick();
    CHECK(wire.written == std::vector<Bytes>({{1}}));
    auto e = c.next_event(); CHECK(e && e->kind == EventKind::written);
    e = c.next_event(); CHECK(e && e->error == Error::timeout && e->operation == op.operation);
}
void byte_limits_are_logical_not_capacity() {
    FakeClock clock; FakeRandom random; FakeTransport wire;
    Config cfg; cfg.max_bytes = 1;
    Client c(wire, clock, random, cfg); connected(c, wire);
    Bytes payload; payload.reserve(1024 * 1024); payload.push_back(1);
    CHECK(payload.capacity() >= 1024 * 1024 && payload.size() == 1);
    wire.result = WriteResult::blocked;
    CHECK(c.send(std::move(payload), 100).error == Error::none);
    c.tick(); CHECK(c.queued_bytes() == 1);
    CHECK(c.send({2}, 100).error == Error::queue_full);
}
int main(int argc, char** argv) {
    if (argc == 2) {
        const std::string name = argv[1];
        if (name == "retry-clock") advancing_clock_retry();
        else if (name == "poll-deadline") poll_crosses_send_deadline();
        else if (name == "write-deadline") prior_write_crosses_next_deadline();
        else return 2;
        return 0;
    }
    lifecycle(); cancellation_and_bounds(); timeout_retry_stale_events();
    close_during_connect_and_reopen(); failures_and_no_replay();
    isolation_and_optional_sink(); diagnostics_and_config();
    advancing_clock_retry(); poll_crosses_send_deadline(); prior_write_crosses_next_deadline();
    byte_limits_are_logical_not_capacity();
    std::cout << "PASS: 11 deterministic lifecycle test groups\n";
}
