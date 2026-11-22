#include "madlink_c.h"
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <new>

#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL: tracked OOM check %d\n", __LINE__); std::exit(1); } } while (0)
static bool fail = false;
void* operator new(std::size_t size) {
    if (!fail) if (void* p = std::malloc(size ? size : 1)) return p;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
struct Peer {
    uint64_t generation=0;
    bool ready=false, accept_once=false;
    unsigned accepted=0, closes=0;
};
static void connect_peer(void* u, const char*, uint64_t generation) {
    auto& p=*static_cast<Peer*>(u); p.generation=generation; p.ready=true;
}
static void close_peer(void* u) { ++static_cast<Peer*>(u)->closes; }
static int32_t poll_peer(void* u, ml_wire_event_v1* event) {
    auto& p=*static_cast<Peer*>(u);
    if (!p.ready) return 0;
    p.ready=false; event->generation=p.generation; event->kind=ML_WIRE_CONNECTED; return 1;
}
static int32_t write_peer(void* u, const uint8_t*, uint64_t) {
    auto& p=*static_cast<Peer*>(u);
    if (!p.accept_once) return ML_WRITE_BLOCKED;
    p.accept_once=false; ++p.accepted; fail=true;
    return ML_WRITE_ACCEPTED;
}
static uint64_t zero(void*) { return 0; }
static ml_client* open_client(Peer& p, uint32_t capacity) {
    const ml_config_v1 cfg{sizeof(cfg),ML_ABI_V1,8,1024,32,100,10,10,1};
    const ml_host_v1 host{sizeof(host),ML_ABI_V1,&p,connect_peer,close_peer,poll_peer,write_peer,zero,zero};
    ml_client* c=nullptr;
    fail=true;
    CHECK(ml_create_tracked_v1(&cfg,&host,capacity,&c)==ML_OUT_OF_MEMORY && !c && p.closes==0);
    fail=false;
    CHECK(ml_create_tracked_v1(&cfg,&host,capacity,&c)==ML_OK);
    CHECK(ml_connect_v1(c,"synthetic")==ML_OK && ml_tick_v1(c)==ML_OK);
    return c;
}
static uint64_t submit(ml_client* c, ml_status expected) {
    const uint8_t data[8]={}; uint64_t id=99;
    CHECK(ml_send_tracked_v1(c,data,sizeof(data),100,&id)==expected);
    CHECK((id!=0)==(expected==ML_OK)); return id;
}
static void receive(ml_client* c, uint64_t id, uint32_t outcome) {
    ml_completion_v1 out{sizeof(out), ML_ABI_V1, 0, 0, 0};
    CHECK(ml_next_completion_v1(c,&out)==ML_OK && out.operation==id && out.outcome==outcome);
}
static void empty(ml_client* c) {
    ml_completion_v1 out{sizeof(out), ML_ABI_V1, 0, 0, 0};
    CHECK(ml_next_completion_v1(c,&out)==ML_EMPTY);
}
int main() {
    Peer full;
    ml_client* c=open_client(full,1);
    const auto old=submit(c,ML_OK);
    fail=true;
    submit(c,ML_QUEUE_FULL); // No payload allocation, no poisoning when full.
    empty(c);
    fail=false;
    CHECK(ml_cancel_v1(c,old)==ML_OK);
    receive(c,old,ML_COMPLETION_CANCELLED);
    ml_destroy_v1(c);

    Peer copy;
    c=open_client(copy,2);
    const auto pending=submit(c,ML_OK);
    fail=true;
    submit(c,ML_OUT_OF_MEMORY); // Rejected call has no receipt; accepted one does.
    CHECK(ml_tick_v1(c)==ML_POISONED);
    receive(c,pending,ML_COMPLETION_HANDLE_FAULT_UNKNOWN); empty(c);
    CHECK(!copy.accepted);
    fail=false;
    ml_destroy_v1(c);

    Peer diagnostic;
    c=open_client(diagnostic,2);
    bool caught=false;
    auto accepted=submit(c,ML_OK);
    for (unsigned i=0; i<2048; ++i) {
        const auto later=submit(c,ML_OK);
        diagnostic.accept_once=true;
        const ml_status status=ml_tick_v1(c);
        CHECK(diagnostic.accepted==i+1 && fail);
        receive(c,accepted,ML_COMPLETION_LOCAL_ACCEPTED); // Drain with allocations forbidden.
        if (status==ML_OUT_OF_MEMORY) {
            caught=true;
            // The previous acceptance stays exact; pending becomes explicitly unknown.
            receive(c,later,ML_COMPLETION_HANDLE_FAULT_UNKNOWN); empty(c);
            CHECK(ml_tick_v1(c)==ML_POISONED && ml_close_v1(c)==ML_POISONED &&
                  ml_cancel_v1(c,later)==ML_POISONED && diagnostic.accepted==i+1);
            fail=false;
            break;
        }
        CHECK(status==ML_OK);
        empty(c);
        fail=false;
        // Advance the existing pending operation instead of injecting extra
        // diagnostics which might always allocate outside the failure window.
        accepted=later;
    }
    CHECK(caught);
    ml_destroy_v1(c);
    CHECK(diagnostic.closes==1 && full.closes==1 && copy.closes==1);
    std::puts("PASS: installed tracked C ABI retains exact results through allocator failure and poison");
}
