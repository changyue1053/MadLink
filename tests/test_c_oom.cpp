#include "madlink_c.h"
#include <cstdlib>
#include <cstdio>
#include <new>
static bool fail = false;
void* operator new(std::size_t size) {
    if (fail) throw std::bad_alloc();
    if (void* p = std::malloc(size ? size : 1)) return p;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
struct Host { uint64_t generation=0; bool ready=false; unsigned closes=0, writes=0; bool accept=false; };
static void begin(void* u,const char*,uint64_t g) { auto& h=*static_cast<Host*>(u);h.generation=g;h.ready=true; }
static void close_host(void* u) { ++static_cast<Host*>(u)->closes; }
static int32_t poll(void* u,ml_wire_event_v1* e) {
    auto& h=*static_cast<Host*>(u); if (!h.ready) return 0;
    h.ready=false;e->kind=ML_WIRE_CONNECTED;e->generation=h.generation;return 1;
}
static int32_t write_host(void* u,const uint8_t*,uint64_t) {
    auto& h=*static_cast<Host*>(u);
    if (!h.accept) return ML_WRITE_BLOCKED;
    ++h.writes;fail=true;return ML_WRITE_ACCEPTED;
}
static uint64_t zero(void*) { return 0; }
int main() {
    Host h; ml_client* c=nullptr;
    ml_config_v1 cfg{sizeof(cfg),ML_ABI_V1,16,1024,64,100,10,100,2};
    ml_host_v1 host{sizeof(host),ML_ABI_V1,&h,begin,close_host,poll,write_host,zero,zero};
    fail=true;
    auto result=ml_create_v1(&cfg,&host,&c);
    fail=false;
    if (result!=ML_OUT_OF_MEMORY || c) return 1;
    if (ml_create_v1(&cfg,&host,&c)!=ML_OK || ml_connect_v1(c,"x")!=ML_OK || ml_tick_v1(c)!=ML_OK) return 2;
    uint8_t data[8]={}; uint64_t id=99;
    fail=true;
    result=ml_send_v1(c,data,8,100,&id);
    fail=false;
    if (result!=ML_OUT_OF_MEMORY || id!=0 || ml_tick_v1(c)!=ML_POISONED) return 3;
    ml_destroy_v1(c);
    if (h.closes!=1) return 4;
    std::puts("PASS: C ABI contains OOM and requires destruction of poisoned handle");
    h.accept=true;
    if (ml_create_v1(&cfg,&host,&c)!=ML_OK || ml_connect_v1(c,"again")!=ML_OK || ml_tick_v1(c)!=ML_OK) return 5;
    bool caught=false;
    for (unsigned i=0;i<2048;++i) {
        if (ml_send_v1(c,data,8,100,&id)!=ML_OK) return 6;
        const auto before=h.writes;
        result=ml_tick_v1(c);
        fail=false;
        if (result==ML_OUT_OF_MEMORY) {
            caught=true;
            if (h.writes!=before+1 || ml_tick_v1(c)!=ML_POISONED ||
                ml_close_v1(c)!=ML_POISONED || ml_cancel_v1(c,id)!=ML_POISONED) return 7;
            uint64_t another=99;
            if (ml_send_v1(c,data,8,100,&another)!=ML_POISONED || another!=0 || h.writes!=before+1) return 8;
            break;
        }
        if (result!=ML_OK) return 9;
    }
    if (!caught) return 10;
    ml_destroy_v1(c);if (h.closes!=2) return 11;
    std::puts("PASS: C ABI poisons after accepted write followed by diagnostic OOM, with no replay");
}
