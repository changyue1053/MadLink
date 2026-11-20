#include "madlink_c.h"
#include "madlink.hpp"
#include <limits>
#include <memory>
#include <new>
#include <stdexcept>
namespace {
struct Adapter final : madlink::Transport, madlink::Clock, madlink::Random {
    ml_host_v1 host;
    uint64_t generation = 0, limit;
    Adapter(ml_host_v1 h, uint64_t l) : host(h), limit(l) {}
    void connect(const std::string& endpoint, uint64_t g) noexcept override {
        generation = g; host.connect(host.user, endpoint.c_str(), g);
    }
    void close() noexcept override { host.close(host.user); }
    std::optional<madlink::WireEvent> poll() override {
        ml_wire_event_v1 e{};
        const auto result = host.poll(host.user, &e);
        if (!result) return {};
        // A poll failure describes the adapter, not the possibly uninitialized event.
        if (result != 1)
            return madlink::WireEvent{madlink::WireEvent::Kind::disconnected, generation, {}};
        // Preserve stale generations for Core's filtering. Never inspect/copy their
        // payload or attribute malformed old data to the current connection.
        if (e.generation != generation || e.kind > ML_WIRE_DISCONNECTED ||
            e.data_size > limit || (e.data_size && !e.data))
            return madlink::WireEvent{madlink::WireEvent::Kind::disconnected, e.generation, {}};
        madlink::Bytes bytes;
        if (e.data_size) bytes.assign(e.data, e.data + static_cast<size_t>(e.data_size));
        return madlink::WireEvent{static_cast<madlink::WireEvent::Kind>(e.kind), e.generation, std::move(bytes)};
    }
    madlink::WriteResult write(const madlink::Bytes& bytes) noexcept override {
        const auto result = host.write(host.user, bytes.data(), bytes.size());
        if (result == ML_WRITE_ACCEPTED) return madlink::WriteResult::accepted;
        if (result == ML_WRITE_BLOCKED) return madlink::WriteResult::blocked;
        return madlink::WriteResult::failed;
    }
    uint64_t now_ms() const noexcept override { return host.now_ms(host.user); }
    uint64_t next() noexcept override { return host.random(host.user); }
};
}
struct ml_client {
    Adapter adapter;
    using Slot = madlink::Client::CompletionSlot;
    using Outcome = madlink::Client::Outcome;
    static_assert(static_cast<uint32_t>(Outcome::local_accepted) == ML_COMPLETION_LOCAL_ACCEPTED);
    static_assert(static_cast<uint32_t>(Outcome::cancelled) == ML_COMPLETION_CANCELLED);
    static_assert(static_cast<uint32_t>(Outcome::deadline) == ML_COMPLETION_DEADLINE);
    static_assert(static_cast<uint32_t>(Outcome::transport_unknown) == ML_COMPLETION_TRANSPORT_UNKNOWN);
    static_assert(static_cast<uint32_t>(Outcome::handle_fault_unknown) == ML_COMPLETION_HANDLE_FAULT_UNKNOWN);
    // Its size never changes. Slots must outlive core/its Pending records.
    std::vector<Slot> completions;
    madlink::Client core;
    madlink::Bytes event_bytes;
    bool poisoned = false;
    ml_client(ml_host_v1 host, madlink::Config config, uint32_t capacity)
        : adapter(host, config.max_bytes), completions(capacity), core(adapter, adapter, adapter, config) {
        core.tracking_enabled_ = capacity != 0;
    }
    auto submit(madlink::Bytes bytes, uint64_t deadline, Slot* slot) {
        return core.send_internal(std::move(bytes), deadline, slot);
    }
    void poison() noexcept {
        poisoned = true;
        for (auto& slot : completions)
            if (slot.operation && slot.outcome == Outcome::pending) slot.outcome = Outcome::handle_fault_unknown;
    }
};
namespace {
template<class F> ml_status protect(ml_client* c, F function) noexcept {
    if (!c) return ML_INVALID_ARGUMENT;
    if (c->poisoned) return ML_POISONED;
    try { return function(); }
    catch (const std::bad_alloc&) { c->poison(); return ML_OUT_OF_MEMORY; }
    catch (...) { c->poison(); return ML_INTERNAL_ERROR; }
}
template<class T> bool version(const T* p) {
    return p->abi_version == ML_ABI_V1 && p->struct_size >= sizeof(T);
}
ml_status create_client(const ml_config_v1* cfg, const ml_host_v1* host, uint32_t capacity, ml_client** out) {
    if (!out) return ML_INVALID_ARGUMENT;
    *out = nullptr;
    if (!cfg || !host) return ML_INVALID_ARGUMENT;
    if (!version(cfg) || !version(host)) return ML_ABI_MISMATCH;
    if (!host->connect || !host->close || !host->poll || !host->write || !host->now_ms || !host->random)
        return ML_INVALID_ARGUMENT;
    const auto max = std::numeric_limits<size_t>::max();
    if (cfg->max_messages > max || cfg->max_bytes > max || cfg->max_events > max) return ML_INVALID_CONFIG;
    try {
        madlink::Config config;
        config.max_messages = static_cast<size_t>(cfg->max_messages);
        config.max_bytes = static_cast<size_t>(cfg->max_bytes);
        config.max_events = static_cast<size_t>(cfg->max_events);
        config.connect_timeout_ms = cfg->connect_timeout_ms;
        config.retry_base_ms = cfg->retry_base_ms; config.retry_cap_ms = cfg->retry_cap_ms;
        config.max_retries = cfg->max_retries;
        *out = new ml_client(*host, config, capacity);
        return ML_OK;
    } catch (const std::bad_alloc&) { return ML_OUT_OF_MEMORY; }
    catch (const std::invalid_argument&) { return ML_INVALID_CONFIG; }
    catch (...) { return ML_INTERNAL_ERROR; }
}
}
extern "C" ml_status ml_create_v1(const ml_config_v1* cfg, const ml_host_v1* host, ml_client** out) {
    return create_client(cfg, host, 0, out);
}
extern "C" ml_status ml_create_tracked_v1(const ml_config_v1* cfg, const ml_host_v1* host,
                                           uint32_t capacity, ml_client** out) {
    if (!out) return ML_INVALID_ARGUMENT;
    *out = nullptr;
    if (!capacity || capacity > ML_MAX_TRACKED_COMPLETIONS_V1) return ML_INVALID_CONFIG;
    return create_client(cfg, host, capacity, out);
}
extern "C" ml_status ml_connect_v1(ml_client* c, const char* endpoint) {
    if (!endpoint) return ML_INVALID_ARGUMENT;
    return protect(c, [&]() -> ml_status { return static_cast<ml_status>(c->core.connect(endpoint)); });
}
extern "C" ml_status ml_send_v1(ml_client* c, const uint8_t* data, uint64_t size, uint64_t deadline, uint64_t* out) {
    if (!out) return ML_INVALID_ARGUMENT;
    *out = 0;
    if ((size && !data) || size > std::numeric_limits<size_t>::max()) return ML_INVALID_ARGUMENT;
    return protect(c, [&]() -> ml_status {
        if (size > c->adapter.limit) return ML_QUEUE_FULL;
        madlink::Bytes bytes;
        if (size) bytes.assign(data, data + static_cast<size_t>(size));
        auto result = c->core.send(std::move(bytes), deadline);
        *out = result.operation;
        return static_cast<ml_status>(result.error);
    });
}
extern "C" ml_status ml_tick_v1(ml_client* c) {
    return protect(c, [&]() -> ml_status { c->core.tick(); return ML_OK; });
}
extern "C" ml_status ml_close_v1(ml_client* c) {
    return protect(c, [&]() -> ml_status { c->core.close(); return ML_OK; });
}
extern "C" ml_status ml_cancel_v1(ml_client* c, uint64_t id) {
    return protect(c, [&]() -> ml_status { return c->core.cancel(id) ? ML_OK : ML_NOT_FOUND; });
}
extern "C" ml_status ml_next_event_v1(ml_client* c, ml_event_v1* out) {
    if (!out) return ML_INVALID_ARGUMENT;
    if (!version(out)) return ML_ABI_MISMATCH;
    return protect(c, [&]() -> ml_status {
        c->event_bytes.clear();
        *out = {}; out->struct_size = sizeof(*out); out->abi_version = ML_ABI_V1;
        auto event = c->core.next_event();
        if (!event) return ML_EMPTY;
        out->kind = static_cast<uint32_t>(event->kind); out->state = static_cast<uint32_t>(event->state);
        out->error = static_cast<ml_status>(event->error); out->operation = event->operation;
        c->event_bytes = std::move(event->data);
        out->data = c->event_bytes.data(); out->data_size = c->event_bytes.size();
        return ML_OK;
    });
}
extern "C" void ml_destroy_v1(ml_client* c) { delete c; }
extern "C" ml_status ml_send_tracked_v1(ml_client* c, const uint8_t* data, uint64_t size,
                                         uint64_t deadline, uint64_t* out) {
    if (!out) return ML_INVALID_ARGUMENT;
    *out = 0;
    if ((size && !data) || size > std::numeric_limits<size_t>::max()) return ML_INVALID_ARGUMENT;
    return protect(c, [&]() -> ml_status {
        if (c->completions.empty()) return ML_INVALID_STATE;
        if (size > c->adapter.limit) return ML_QUEUE_FULL;
        ml_client::Slot* slot = nullptr;
        for (auto& candidate : c->completions)
            if (!candidate.operation) { slot = &candidate; break; }
        if (!slot) return ML_QUEUE_FULL;
        // Owner-thread/non-reentrant: this free slot is reserved until core
        // accepts (sets operation), or this call unwinds/rejects (still free).
        madlink::Bytes bytes;
        if (size) bytes.assign(data, data + static_cast<size_t>(size));
        const auto result = c->submit(std::move(bytes), deadline, slot);
        *out = result.operation;
        return static_cast<ml_status>(result.error);
    });
}
extern "C" ml_status ml_next_completion_v1(ml_client* c, ml_completion_v1* out) {
    if (!c || !out) return ML_INVALID_ARGUMENT;
    if (!version(out)) return ML_ABI_MISMATCH;
    if (c->completions.empty()) return ML_INVALID_STATE;
    // Does not use protect: already-established terminal results are readable
    // even after poison, when no further core operations are allowed.
    ml_client::Slot* ready = nullptr;
    for (auto& slot : c->completions)
        if (slot.operation && slot.outcome != ml_client::Outcome::pending &&
            (!ready || slot.operation < ready->operation)) ready = &slot;
    if (!ready) return ML_EMPTY;
    *out = {sizeof(*out), ML_ABI_V1, ready->operation, static_cast<uint32_t>(ready->outcome), 0};
    *ready = {};
    return ML_OK;
}
