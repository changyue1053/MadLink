#include "madlink.hpp"
#include <algorithm>
#include <limits>
#include <stdexcept>
#include <utility>

namespace madlink {
namespace {
std::uint64_t add_saturated(std::uint64_t a, std::uint64_t b) {
    return a > std::numeric_limits<std::uint64_t>::max() - b
        ? std::numeric_limits<std::uint64_t>::max() : a + b;
}
}
Client::Client(Transport& t, Clock& c, Random& r, Config config, TelemetrySink* sink)
    : transport_(t), clock_(c), random_(r), config_(config), sink_(sink) {
    if (!config.max_messages || !config.max_bytes || !config.max_events ||
        !config.connect_timeout_ms || !config.retry_base_ms ||
        config.retry_base_ms > config.retry_cap_ms)
        throw std::invalid_argument("invalid MadLink configuration");
}
Client::~Client() { transport_.close(); } // Never calls the observation sink.
void Client::emit(Event event) {
    if (events_.size() == config_.max_events) {
        ++dropped_events_; // Explicit diagnostic overflow, not an ACK ledger.
        events_.pop_front();
    }
    events_.push_back(std::move(event));
}
void Client::transition(State state) {
    state_ = state;
    emit({EventKind::state, state});
    if (sink_) sink_->state_changed(state);
}
void Client::begin() {
    ++generation_;
    started_ = clock_.now_ms();
    transition(State::connecting);
    transport_.connect(endpoint_, generation_);
}
Error Client::connect(std::string endpoint) {
    if (state_ != State::idle && state_ != State::closed) return Error::invalid_state;
    if (endpoint.empty()) return Error::invalid_config;
    endpoint_ = std::move(endpoint);
    retries_ = 0;
    begin();
    return Error::none;
}
SendResult Client::send(Bytes data, std::uint64_t deadline) {
    if (state_ != State::connected) return {Error::invalid_state, 0};
    if (deadline <= clock_.now_ms()) return {Error::timeout, 0};
    if (pending_.size() >= config_.max_messages || data.size() > config_.max_bytes - bytes_)
        return {Error::queue_full, 0};
    const auto id = next_id_;
    const auto size = data.size();
    pending_.push_back({id, deadline, std::move(data)});
    bytes_ += size; // Commit counters only after successful allocation/insertion.
    ++next_id_;
    return {Error::none, id};
}
bool Client::cancel(std::uint64_t id) {
    const auto p = std::find_if(pending_.begin(), pending_.end(),
        [id](const Pending& item) { return item.id == id; });
    if (p == pending_.end()) return false;
    bytes_ -= p->data.size();
    pending_.erase(p);
    emit({EventKind::failed, state_, Error::cancelled, id});
    return true;
}
void Client::fail_pending(Error error) {
    for (const auto& p : pending_) emit({EventKind::failed, state_, error, p.id});
    pending_.clear();
    bytes_ = 0;
}
void Client::close() {
    if (state_ == State::closed) return;
    ++generation_;
    transport_.close();
    fail_pending(Error::cancelled);
    transition(State::closed);
}
void Client::disconnect(Error error) {
    ++generation_; // Discard late events from the old connection attempt.
    transport_.close();
    fail_pending(error); // Never automatically replay application messages.
    emit({EventKind::failed, state_, error});
    if (retries_ >= config_.max_retries) { transition(State::closed); return; }
    auto delay = config_.retry_base_ms;
    for (unsigned i = 0; i < retries_ && delay < config_.retry_cap_ms; ++i)
        delay = std::min(add_saturated(delay, delay), config_.retry_cap_ms);
    ++retries_;
    // Equal jitter in [delay/2, delay], deterministic with injected Random.
    const auto lower = delay / 2;
    delay = lower + random_.next() % (delay - lower + 1);
    retry_at_ = add_saturated(clock_.now_ms(), delay);
    transition(State::backoff);
}
void Client::tick() {
    if (state_ == State::idle || state_ == State::closed) return;
    if (state_ == State::backoff) {
        if (clock_.now_ms() < retry_at_) return;
        begin();
    }
    const auto now = clock_.now_ms(); // Must be sampled after begin(), not before.
    if (state_ == State::connecting && now >= started_ &&
        now - started_ >= config_.connect_timeout_ms) {
        disconnect(Error::timeout);
        return;
    }
    // A bounded poll budget prevents a continuously readable adapter starving callers.
    for (std::size_t i = 0; i < 64; ++i) {
        auto event = transport_.poll();
        if (!event) break;
        if (event->generation != generation_) continue;
        if (event->kind == WireEvent::Kind::disconnected) {
            disconnect(Error::transport); return;
        }
        if (event->kind == WireEvent::Kind::connected && state_ == State::connecting)
            transition(State::connected);
        else if (event->kind == WireEvent::Kind::received && state_ == State::connected) {
            if (event->data.size() > config_.max_bytes) { disconnect(Error::transport); return; }
            emit({EventKind::received, state_, Error::none, 0, std::move(event->data)});
        }
    }
    if (state_ != State::connected) return;
    for (auto p = pending_.begin(); p != pending_.end();) {
        if (p->deadline <= clock_.now_ms()) {
            emit({EventKind::failed, state_, Error::timeout, p->id});
            bytes_ -= p->data.size();
            p = pending_.erase(p);
        } else ++p;
    }
    while (!pending_.empty()) {
        auto& p = pending_.front();
        // Polling, callbacks and earlier writes can consume time within one tick.
        // Revalidate immediately before handing each message to the adapter.
        if (p.deadline <= clock_.now_ms()) {
            emit({EventKind::failed, state_, Error::timeout, p.id});
            bytes_ -= p.data.size();
            pending_.pop_front();
            continue;
        }
        const auto result = transport_.write(p.data);
        if (result == WriteResult::blocked) break;
        if (result == WriteResult::failed) { disconnect(Error::transport); return; }
        // Transport acceptance is irreversible. Remove this operation before any
        // diagnostic allocation can throw, so a later tick cannot send it twice.
        const auto id = p.id;
        bytes_ -= p.data.size();
        pending_.pop_front();
        emit({EventKind::written, state_, Error::none, id});
    }
}
std::optional<Event> Client::next_event() {
    if (events_.empty()) return std::nullopt;
    auto event = std::move(events_.front());
    events_.pop_front();
    return event;
}
} // namespace madlink
