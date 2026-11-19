#pragma once
#include <madobs/privacy.h>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace madlink::madobs_adapter {
// Provisional finite schema, not a globally registered identifier.
inline constexpr std::uint32_t sdk_id=0x4d4c, sdk_version=1, state_event=1, state_key=1;
struct Stats {
    std::uint64_t enqueued=0, overflow=0, invalid_state=0, reentrant=0;
    std::uint64_t callback_invoked=0, noop=0, rejected=0, callback_error=0;
};
class QueuedObserver {
public:
    static constexpr std::size_t capacity=32;
    // Copies descriptor; context remains borrowed. Owner-thread-only, no worker.
    explicit QueuedObserver(madobs_observer_v1 observer) noexcept : observer_(observer) {}
    QueuedObserver(const QueuedObserver&)=delete;
    QueuedObserver& operator=(const QueuedObserver&)=delete;
    ~QueuedObserver()=default; // Never flush/call host during destruction.
    void enqueue_state(std::uint32_t state) noexcept {
        if (draining_) { increment(stats_.reentrant);return; }
        if (state>4) { increment(stats_.invalid_state);return; }
        if (size_==capacity) { increment(stats_.overflow);return; }
        queue_[(head_+size_)%capacity]=state;++size_;increment(stats_.enqueued);
    }
    std::size_t drain(std::size_t budget) noexcept {
        if (draining_) { increment(stats_.reentrant);return 0; }
        draining_=true;
        std::size_t attempted=0;
        while (size_ && attempted<budget) {
            const auto state=queue_[head_];head_=(head_+1)%capacity;--size_;++attempted;
            // Remove before invoking foreign code: never retry ambiguous side effects.
            madobs_event_v1 event{};
            event.struct_size=sizeof(event);event.abi_version=MADOBS_ABI_VERSION;
            event.sdk_id=sdk_id;event.sdk_version=sdk_version;event.event_id=state_event;
            event.severity=1;event.attribute_count=1;
            event.attributes[0]={state_key,state};
            // No clock is sampled. monotonic_ns and all inactive slots stay zero.
            const auto result=madobs_observer_emit_private(&observer_,&policy(),&event);
            switch(result) {
            case MADOBS_EMITTED: increment(stats_.callback_invoked);break;
            case MADOBS_NOOP: increment(stats_.noop);break;
            case MADOBS_INVALID: increment(stats_.rejected);break;
            case MADOBS_CALLBACK_ERROR: increment(stats_.callback_error);break;
            default: increment(stats_.rejected);break;
            }
        }
        draining_=false;return attempted;
    }
    std::size_t pending() const noexcept { return size_; }
    Stats stats() const noexcept { return stats_; }
    static const madobs_privacy_policy_v1& policy() noexcept {
        static const madobs_event_rule_v1 rule=[] {
            madobs_event_rule_v1 r{};r.sdk_id=sdk_id;r.sdk_version=sdk_version;
            r.event_id=state_event;r.max_severity=1;r.attribute_count=1;
            r.attributes[0].key=state_key;r.attributes[0].value_count=5;
            for (std::uint32_t i=0;i<5;++i) r.attributes[0].values[i]=i;
            return r;
        }();
        static const madobs_privacy_policy_v1 p{sizeof(p),MADOBS_ABI_VERSION,1,&rule};
        return p;
    }
private:
    static void increment(std::uint64_t& n) noexcept { if (n!=std::numeric_limits<std::uint64_t>::max()) ++n; }
    madobs_observer_v1 observer_;
    std::array<std::uint32_t,capacity> queue_{};
    std::size_t head_=0,size_=0;
    bool draining_=false;
    Stats stats_{};
};
}
