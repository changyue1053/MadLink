#include <madlink_c.h>
#include <madlink_madobs/queued_observer.hpp>
#include <madobs/runtime.h>
#include <atomic>
#include <cstdint>
#include <iostream>
#include <stdexcept>

namespace {
void check(bool ok, const char* label) { if (!ok) throw std::runtime_error(label); }
using Queue = madlink::madobs_adapter::QueuedObserver;
struct Capture {
    const madobs_privacy_policy_v1* policy;
    std::atomic<unsigned> batches{0}, invalid{0};
};
// No sockets, file exporter or remote endpoint. This is a local test sink only.
// The runtime may invoke this on its worker; do not touch the owner-thread queue.
void consume(void* user, uint8_t, uint64_t, const uint8_t* bytes, size_t size,
             madobs_send_done_fn done, void* done_context) {
    auto& c = *static_cast<Capture*>(user);
    const bool safe = madobs_check_private_batch(bytes, size, c.policy) == MADOBS_PRIVATE_BATCH_OK;
    c.batches.fetch_add(1);
    if (!safe) c.invalid.fetch_add(1);
    done(done_context, safe ? 1 : 0); // Local discard acknowledgment, NOT delivery.
}
struct Runtime {
    madobs_handle_t h = 0;
    ~Runtime() { if (h) { (void)madobs_stop(h); (void)madobs_destroy(h); } }
};
struct Link {
    ml_client* h = nullptr;
    ~Link() { ml_destroy_v1(h); }
};
struct Host { uint64_t generation=0; bool ready=false; };
void connect_host(void* u, const char*, uint64_t generation) {
    auto& h=*static_cast<Host*>(u);h.generation=generation;h.ready=true;
}
void close_host(void*) {}
int32_t poll_host(void* u, ml_wire_event_v1* event) {
    auto& h=*static_cast<Host*>(u);if (!h.ready) return 0;
    h.ready=false;event->kind=ML_WIRE_CONNECTED;event->generation=h.generation;return 1;
}
int32_t write_host(void*, const uint8_t*, uint64_t) { return ML_WRITE_ACCEPTED; }
uint64_t zero(void*) { return 0; }
}
int main(int argc, char** argv) {
    if (argc != 2) return 2; // Fresh WAL directory supplied by the disposable driver.
    try {
        Capture capture{&Queue::policy()};
        Runtime runtime;
        runtime.h=madobs_create(argv[1], consume, &capture);
        check(runtime.h!=0, "runtime create");
        check(madobs_start(runtime.h)==MADOBS_OK, "runtime start");
        madobs_observer_binding_v1 binding{};madobs_observer_v1 observer{};
        check(madobs_observer_for_runtime(runtime.h,&binding,&observer)==MADOBS_OK, "real runtime observer");
        Queue queue(observer);
        Host host;
        Link link;
        ml_config_v1 config{sizeof(config),ML_ABI_V1,16,1024,64,100,10,100,1};
        ml_host_v1 api{sizeof(api),ML_ABI_V1,&host,connect_host,close_host,poll_host,write_host,zero,zero};
        check(ml_create_v1(&config,&api,&link.h)==ML_OK, "installed MadLink create");
        check(ml_connect_v1(link.h,"synthetic-not-exported")==ML_OK, "link connect");
        check(ml_tick_v1(link.h)==ML_OK && ml_close_v1(link.h)==ML_OK, "link lifecycle");
        ml_event_v1 event{};event.struct_size=sizeof(event);event.abi_version=ML_ABI_V1;
        unsigned states=0;
        const uint32_t expected[]={ML_CONNECTING,ML_CONNECTED,ML_CLOSED};
        ml_status status;
        while ((status=ml_next_event_v1(link.h,&event))==ML_OK) {
            if (event.kind!=ML_EVENT_STATE) continue;
            check(states<3 && event.state==expected[states], "finite state sequence");
            ++states;queue.enqueue_state(event.state);
        }
        check(status==ML_EMPTY && states==3 && queue.pending()==3, "queued states");
        madobs_generic_stats_v1 stats{};
        check(madobs_get_generic_stats(runtime.h,&stats)==MADOBS_OK && stats.enqueued==0, "no implicit drain");
        check(queue.drain(32)==3 && queue.stats().callback_invoked==3, "explicit callback drain");
        check(madobs_get_generic_stats(runtime.h,&stats)==MADOBS_OK && stats.enqueued==3, "actual runtime admission");
        // Owner-thread producers are now quiescent; stop synchronously joins/drains.
        check(madobs_stop(runtime.h)==MADOBS_OK, "runtime stop");
        check(madobs_get_generic_stats(runtime.h,&stats)==MADOBS_OK && stats.enqueued==3 &&
              stats.drained==3 && stats.queue_dropped==0 && stats.wal_dropped==0, "actual runtime drain/drop stats");
        check(capture.batches.load()>0 && capture.invalid.load()==0, "non-vacuous private batch validation");
        // Sequential negative probe only: callback invocation is not admission.
        queue.enqueue_state(ML_CLOSED);check(queue.drain(1)==1, "post-stop observer probe");
        check(queue.stats().callback_invoked==4, "observer invocation semantics");
        check(madobs_get_generic_stats(runtime.h,&stats)==MADOBS_OK && stats.enqueued==3 && stats.drained==3,
              "stopped runtime rejects observer admission");
        madobs_event_v1 probe{};probe.struct_size=sizeof(probe);probe.abi_version=MADOBS_ABI_VERSION;
        check(madobs_emit_generic_event(runtime.h,&probe)==MADOBS_E_BAD_STATE, "explicit stopped admission status");
        check(madobs_destroy(runtime.h)==MADOBS_OK, "runtime destroy");runtime.h=0;
        std::cout << "PASS: installed MadLink states -> real installed MadObs runtime admission/drain; local batch validation only\n";
    } catch (const std::exception& e) { std::cerr << "FAIL: " << e.what() << '\n';return 1; }
}
