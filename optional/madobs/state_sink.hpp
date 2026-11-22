#pragma once
#include "madlink.hpp"
#include "queued_observer.hpp"
namespace madlink::madobs_adapter {
// Both queue and this bridge must outlive the Core client that borrows this sink.
class StateSink final : public TelemetrySink {
public:
    explicit StateSink(QueuedObserver& queue) noexcept : queue_(queue) {}
    void state_changed(State state) noexcept override { queue_.enqueue_state(static_cast<std::uint32_t>(state)); }
private:
    QueuedObserver& queue_;
};
}
