/* Installed public C ABI only. Synthetic app-owned transports, no sockets/threads. */
#ifdef MADLINK_SESSION_XCTEST
#include <MadLink/madlink_c.h>
#else
#include "madlink_c.h"
#endif
#ifdef NDEBUG
#error "Runtime acceptance requires active assertions"
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct host {
    uint64_t generation, now;
    unsigned owner, connects, closes, accepted;
    int blocked;
    ml_wire_event_v1 input[8];
    unsigned read, count;
    uint8_t bytes[3];
};
static void queue(struct host* h, uint32_t kind, uint64_t generation) {
    assert(h->count < 8);
    h->input[h->count++] = (ml_wire_event_v1){kind,generation,h->bytes,3};
}
static void begin(void* raw,const char* endpoint,uint64_t generation) {
    struct host* h=raw;
    assert(strcmp(endpoint,h->owner==1 ? "app-a" : "app-b")==0);
    assert(generation>h->generation);
    h->generation=generation;h->connects++;
    queue(h,ML_WIRE_CONNECTED,generation);
}
static void stop(void* raw) { ((struct host*)raw)->closes++; }
static int32_t poll_event(void* raw,ml_wire_event_v1* event) {
    struct host* h=raw;
    if(h->read==h->count) { h->read=h->count=0;return 0; }
    *event=h->input[h->read++];return 1;
}
static int32_t write_bytes(void* raw,const uint8_t* bytes,uint64_t length) {
    struct host* h=raw;
    assert(length==3 && bytes[0]==h->owner && bytes[1]==0 && bytes[2]==255);
    if(h->blocked)return ML_WRITE_BLOCKED;
    h->accepted++;return ML_WRITE_ACCEPTED;
}
static uint64_t clock_ms(void* raw) { return ((struct host*)raw)->now; }
static uint64_t random_zero(void* raw) { (void)raw;return 0; }
static ml_client* create(struct host* h) {
    ml_client* c=NULL;
    ml_config_v1 cfg={sizeof(cfg),ML_ABI_V1,4,32,64,100,10,10,2};
    ml_host_v1 host={sizeof(host),ML_ABI_V1,h,begin,stop,poll_event,write_bytes,clock_ms,random_zero};
    assert(ml_create_v1(&cfg,&host,&c)==ML_OK && c);return c;
}
static ml_event_v1 next(ml_client* c,uint32_t kind) {
    ml_event_v1 e={0};e.struct_size=sizeof(e);e.abi_version=ML_ABI_V1;
    assert(ml_next_event_v1(c,&e)==ML_OK && e.kind==kind);return e;
}
static void empty(ml_client* c) {
    ml_event_v1 e={0};e.struct_size=sizeof(e);e.abi_version=ML_ABI_V1;
    assert(ml_next_event_v1(c,&e)==ML_EMPTY);
}
static void state(ml_client* c,uint32_t expected) { assert(next(c,ML_EVENT_STATE).state==expected); }
static uint64_t send(ml_client* c,struct host* h) {
    const uint8_t bytes[]={ (uint8_t)h->owner,0,255 };uint64_t id=0;
    assert(ml_send_v1(c,bytes,3,h->now+1000,&id)==ML_OK && id);return id;
}
static void written(ml_client* c,uint64_t id) {
    ml_event_v1 e=next(c,ML_EVENT_WRITTEN);assert(e.operation==id && e.error==ML_OK);
}
static void received(ml_client* c,const struct host* h) {
    ml_event_v1 e=next(c,ML_EVENT_RECEIVED);
    assert(e.data_size==3 && e.operation==0 && memcmp(e.data,h->bytes,3)==0);
}
int main(void) {
    struct host a={0},b={0};a.owner=1;b.owner=2;
    a.bytes[0]=1;a.bytes[2]=255;b.bytes[0]=2;b.bytes[2]=255;
    ml_client* first=create(&a);ml_client* second=create(&b);
    assert(ml_connect_v1(first,"app-a")==ML_OK && ml_connect_v1(second,"app-b")==ML_OK);
    assert(ml_tick_v1(first)==ML_OK && ml_tick_v1(second)==ML_OK);
    state(first,ML_CONNECTING);state(first,ML_CONNECTED);empty(first);
    state(second,ML_CONNECTING);state(second,ML_CONNECTED);empty(second);
    uint64_t previous_a=0,previous_b=0;
    for(unsigned cycle=0;cycle<32;cycle++) {
        uint64_t aid=send(first,&a),bid=send(second,&b);
        assert(aid>previous_a && bid>previous_b);previous_a=aid;previous_b=bid;
        /* Same per-instance IDs may legitimately collide; owner queues must not. */
        unsigned before_a=a.accepted,before_b=b.accepted;
        assert(ml_tick_v1(first)==ML_OK);written(first,aid);empty(first);empty(second);
        assert(a.accepted==before_a+1 && b.accepted==before_b);
        assert(ml_tick_v1(second)==ML_OK);written(second,bid);empty(second);
        queue(&a,ML_WIRE_RECEIVED,a.generation);queue(&b,ML_WIRE_RECEIVED,b.generation);
        assert(ml_tick_v1(second)==ML_OK);received(second,&b);empty(second);empty(first);
        assert(ml_tick_v1(first)==ML_OK);received(first,&a);empty(first);
        a.blocked=1;uint64_t pending=send(first,&a);previous_a=pending;
        assert(ml_tick_v1(first)==ML_OK);empty(first);assert(a.accepted==before_a+1);
        uint64_t old=a.generation;queue(&a,ML_WIRE_DISCONNECTED,old);
        assert(ml_tick_v1(first)==ML_OK);
        ml_event_v1 failure=next(first,ML_EVENT_FAILED);
        assert(failure.operation==pending && failure.error==ML_TRANSPORT_ERROR);
        failure=next(first,ML_EVENT_FAILED);assert(!failure.operation && failure.error==ML_TRANSPORT_ERROR);
        state(first,ML_BACKOFF);empty(first);empty(second);
        /* Retry is automatic and clock-driven; no sleep or real connection. */
        a.now+=4;assert(ml_tick_v1(first)==ML_OK);empty(first);
        queue(&a,ML_WIRE_RECEIVED,old);queue(&a,ML_WIRE_DISCONNECTED,old);
        a.now++;a.blocked=0;assert(ml_tick_v1(first)==ML_OK);
        state(first,ML_CONNECTING);state(first,ML_CONNECTED);empty(first);
        assert(a.generation>old && a.accepted==before_a+1);
        assert(ml_tick_v1(first)==ML_OK);empty(first); /* Failed message not replayed. */
        assert(ml_cancel_v1(first,pending)==ML_NOT_FOUND);
        aid=send(first,&a);assert(aid>previous_a);previous_a=aid;
        assert(ml_tick_v1(first)==ML_OK);written(first,aid);empty(first);
        /* Explicit reconnect resets retry budget while preserving per-handle IDs. */
        assert(ml_close_v1(first)==ML_OK);state(first,ML_CLOSED);empty(first);
        assert(ml_connect_v1(first,"app-a")==ML_OK && ml_tick_v1(first)==ML_OK);
        state(first,ML_CONNECTING);state(first,ML_CONNECTED);empty(first);
        assert(a.accepted==2*(cycle+1) && b.accepted==cycle+1);
    }
    /* Closing A cancels only its blocked operation; B remains live and writable. */
    a.blocked=1;uint64_t pending=send(first,&a);assert(ml_tick_v1(first)==ML_OK);
    unsigned b_closes=b.closes;assert(ml_close_v1(first)==ML_OK);
    ml_event_v1 failure=next(first,ML_EVENT_FAILED);
    assert(failure.operation==pending && failure.error==ML_CANCELLED);
    state(first,ML_CLOSED);empty(first);ml_destroy_v1(first);first=NULL;
    assert(a.closes==66 && b.closes==b_closes && b_closes==0);empty(second);
    uint64_t bid=send(second,&b);assert(ml_tick_v1(second)==ML_OK);written(second,bid);empty(second);
    assert(b.accepted==33 && a.accepted==64 && a.connects==65);
    assert(ml_close_v1(second)==ML_OK);state(second,ML_CLOSED);empty(second);
    ml_destroy_v1(second);assert(b.closes==2);
    puts("PASS: installed C consumer 32 two-instance recovery cycles, exact event isolation and no replay; synthetic transport only");
    return 0;
}
