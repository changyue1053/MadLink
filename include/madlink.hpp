#pragma once
#include <cstddef>
#include <cstdint>
#include <deque>
#include <optional>
#include <string>
#include <vector>

namespace madlink {
using Bytes = std::vector<std::uint8_t>;
enum class State { idle, connecting, connected, backoff, closed };
enum class Error { none, invalid_state, invalid_config, queue_full, timeout, transport, cancelled };
enum class EventKind { state, received, written, failed };
struct Event {
    EventKind kind;
    State state;
    Error error = Error::none;
    std::uint64_t operation = 0;
    Bytes data{};
};
struct WireEvent {
    enum class Kind { connected, received, disconnected } kind;
    std::uint64_t generation;
    Bytes data{};
};
enum class WriteResult { accepted, blocked, failed };
// All calls belong to one owner thread. Adapters must be nonblocking and not
// reenter Client. accepted means locally accepted, NEVER a business ACK.
struct Transport {
    virtual ~Transport() = default;
    virtual void connect(const std::string& endpoint, std::uint64_t generation) noexcept = 0;
    virtual void close() noexcept = 0;
    virtual std::optional<WireEvent> poll() = 0;
    virtual WriteResult write(const Bytes&) noexcept = 0;
};
struct Clock { virtual ~Clock() = default; virtual std::uint64_t now_ms() const noexcept = 0; };
struct Random { virtual ~Random() = default; virtual std::uint64_t next() noexcept = 0; };
struct TelemetrySink {
    virtual ~TelemetrySink() = default;
    // Metadata only. Must be nonblocking, noexcept, and must not reenter Client.
    virtual void state_changed(State) noexcept = 0;
};
struct Config {
    std::size_t max_messages = 16;
    // Logical payload size only, NOT a vector capacity / allocator / RSS cap.
    std::size_t max_bytes = 65536;
    std::size_t max_events = 64;
    std::uint64_t connect_timeout_ms = 5000;
    std::uint64_t retry_base_ms = 100;
    std::uint64_t retry_cap_ms = 5000;
    unsigned max_retries = 3;
};
struct SendResult { Error error; std::uint64_t operation; };
class Client {
public:
    // Borrowed dependencies must outlive Client; no process-global state.
    Client(Transport&, Clock&, Random&, Config = {}, TelemetrySink* = nullptr);
    ~Client();
    Client(const Client&) = delete;
    Client& operator=(const Client&) = delete;
    Error connect(std::string endpoint);
    SendResult send(Bytes, std::uint64_t deadline_ms);
    bool cancel(std::uint64_t operation);
    void close();
    void tick();
    std::optional<Event> next_event();
    State state() const noexcept { return state_; }
    std::size_t queued_bytes() const noexcept { return bytes_; }
    std::uint64_t dropped_events() const noexcept { return dropped_events_; }
private:
    struct Pending { std::uint64_t id, deadline; Bytes data; };
    Transport& transport_;
    Clock& clock_;
    Random& random_;
    Config config_;
    TelemetrySink* sink_;
    State state_ = State::idle;
    std::string endpoint_;
    std::uint64_t generation_ = 0, next_id_ = 1, started_ = 0;
    std::uint64_t retry_at_ = 0, dropped_events_ = 0;
    unsigned retries_ = 0;
    std::size_t bytes_ = 0;
    std::deque<Pending> pending_;
    std::deque<Event> events_;
    void emit(Event);
    void transition(State);
    void begin();
    void fail_pending(Error);
    void disconnect(Error);
};
} // namespace madlink
