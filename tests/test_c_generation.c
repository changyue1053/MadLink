#include "madlink_c.h"
#include <assert.h>
#include <stdio.h>
struct host { uint64_t generation; int ready, inject, fail_poll; ml_wire_event_v1 event; };
static void begin(void* u,const char* endpoint,uint64_t generation) {
    struct host* h=u;(void)endpoint;h->generation=generation;h->ready=1;
}
static void stop(void* u) { (void)u; }
static uint64_t zero(void* u) { (void)u;return 0; }
static int32_t write_blocked(void* u,const uint8_t* b,uint64_t n) { (void)u;(void)b;(void)n;return ML_WRITE_BLOCKED; }
static int32_t poll_host(void* u,ml_wire_event_v1* e) {
    struct host* h=u;
    if (h->fail_poll) { h->fail_poll=0;return -1; }
    if (h->inject) { h->inject=0;*e=h->event;return 1; }
    if (h->ready) { h->ready=0;e->kind=ML_WIRE_CONNECTED;e->generation=h->generation;return 1; }
    return 0;
}
int main(void) {
    struct host h={0};ml_client* c=NULL;uint64_t old,id=0;
    ml_config_v1 cfg={sizeof(cfg),ML_ABI_V1,16,16,64,100,10,100,1};
    ml_host_v1 host={sizeof(host),ML_ABI_V1,&h,begin,stop,poll_host,write_blocked,zero,zero};
    assert(ml_create_v1(&cfg,&host,&c)==ML_OK);
    assert(ml_connect_v1(c,"old")==ML_OK && ml_tick_v1(c)==ML_OK);old=h.generation;
    assert(ml_close_v1(c)==ML_OK && ml_connect_v1(c,"new")==ML_OK && ml_tick_v1(c)==ML_OK);
    for (int scenario=0;scenario<3;scenario++) {
        h.event.kind=scenario==2 ? 999u : ML_WIRE_RECEIVED;
        h.event.generation=old;h.event.data=NULL;h.event.data_size=scenario==0 ? UINT64_MAX : 1;
        h.inject=1;assert(ml_tick_v1(c)==ML_OK);
        assert(ml_send_v1(c,NULL,0,100,&id)==ML_OK);assert(ml_cancel_v1(c,id)==ML_OK);
    }
    /* Malformed current-generation events must still fail the live connection. */
    h.event.generation=h.generation;h.inject=1;assert(ml_tick_v1(c)==ML_OK);
    assert(ml_send_v1(c,NULL,0,100,&id)==ML_INVALID_STATE);
    assert(ml_close_v1(c)==ML_OK && ml_connect_v1(c,"again")==ML_OK && ml_tick_v1(c)==ML_OK);
    h.fail_poll=1;assert(ml_tick_v1(c)==ML_OK);
    assert(ml_send_v1(c,NULL,0,100,&id)==ML_INVALID_STATE);
    ml_destroy_v1(c);puts("PASS: C ABI stale malformed events are isolated across reconnect");return 0;
}
