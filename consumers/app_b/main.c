#include "madlink_c.h"
#include <assert.h>
#include <stdio.h>
struct host { uint64_t generation; int stage, closes; };
static void begin(void* u,const char* e,uint64_t g) { struct host* h=u; (void)e; h->generation=g; h->stage=1; }
static void stop(void* u) { ((struct host*)u)->closes++; }
static int32_t receive(void* u,ml_wire_event_v1* e) {
    static const uint8_t bytes[]={7,0,9}; struct host* h=u;
    e->generation=h->generation;
    if (h->stage==1) { h->stage=2; e->kind=ML_WIRE_CONNECTED; return 1; }
    if (h->stage==2) { h->stage=3; e->kind=ML_WIRE_RECEIVED; e->data=bytes; e->data_size=3; return 1; }
    return 0;
}
static int32_t blocked(void* u,const uint8_t* b,uint64_t n) { (void)u;(void)b;(void)n;return ML_WRITE_BLOCKED; }
static uint64_t zero(void* u) { (void)u;return 0; }
int main(void) {
    struct host a={0},b={0}; ml_client *first=NULL,*second=NULL; uint64_t id=0; int received=0;
    ml_config_v1 cfg={sizeof(cfg),ML_ABI_V1,2,32,64,100,10,100,1};
    ml_host_v1 host={sizeof(host),ML_ABI_V1,&a,begin,stop,receive,blocked,zero,zero};
    ml_event_v1 e={0}; e.struct_size=sizeof(e);e.abi_version=ML_ABI_V1;
    assert(ml_tick_v1(NULL)==ML_INVALID_ARGUMENT);
    cfg.abi_version=2; assert(ml_create_v1(&cfg,&host,&first)==ML_ABI_MISMATCH && !first);
    cfg.abi_version=1; assert(ml_create_v1(&cfg,&host,&first)==ML_OK);
    host.user=&b; assert(ml_create_v1(&cfg,&host,&second)==ML_OK);
    assert(ml_connect_v1(first,"first")==ML_OK && ml_connect_v1(second,"second")==ML_OK);
    assert(ml_tick_v1(first)==ML_OK && ml_tick_v1(second)==ML_OK);
    assert(ml_send_v1(first,NULL,0,100,&id)==ML_OK);
    assert(ml_cancel_v1(first,id)==ML_OK && ml_cancel_v1(first,id)==ML_NOT_FOUND);
    ml_destroy_v1(first); assert(a.closes==1 && b.closes==0);
    while (ml_next_event_v1(second,&e)==ML_OK) {
        if (e.kind==ML_EVENT_RECEIVED) { assert(e.data_size==3 && e.data[1]==0); received++; }
    }
    assert(received==1 && ml_tick_v1(second)==ML_OK);
    ml_destroy_v1(second); ml_destroy_v1(NULL); assert(b.closes==1);
    puts("PASS: independent C consumer B receive, cancellation and isolation"); return 0;
}
