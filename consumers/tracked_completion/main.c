#include "madlink_c.h"
#include <stdio.h>
#include <stdlib.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL: tracked check %d\n", __LINE__); exit(1); } } while (0)
typedef struct {
    uint64_t now, generation, stale, advance_to;
    unsigned starts, writes, accepted, closes, received;
    int ready, disconnect, mode;
} peer;
static void connect_peer(void* u, const char* endpoint, uint64_t generation) {
    peer* p=u; (void)endpoint; p->generation=generation; ++p->starts; p->ready=1;
}
static void close_peer(void* u) { ++((peer*)u)->closes; }
static int32_t poll_peer(void* u, ml_wire_event_v1* event) {
    peer* p=u; event->generation=p->generation;
    if (p->stale) { event->generation=p->stale; p->stale=0; event->kind=ML_WIRE_DISCONNECTED; return 1; }
    if (p->disconnect) { p->disconnect=0; event->kind=ML_WIRE_DISCONNECTED; return 1; }
    if (p->ready) { p->ready=0; event->kind=ML_WIRE_CONNECTED; return 1; }
    if (p->received) { --p->received; event->kind=ML_WIRE_RECEIVED; return 1; }
    return 0;
}
static int32_t write_peer(void* u, const uint8_t* data, uint64_t size) {
    peer* p=u; CHECK(size==1 && data!=NULL); ++p->writes;
    if (p->mode==ML_WRITE_ACCEPTED) {
        ++p->accepted;
        if (p->advance_to) { p->now=p->advance_to; p->advance_to=0; }
    }
    return p->mode;
}
static uint64_t now_peer(void* u) { return ((peer*)u)->now; }
static uint64_t random_peer(void* u) { (void)u; return 0; }
static const ml_config_v1 cfg={sizeof(cfg),ML_ABI_V1,8,16,2,100,10,10,2};
static ml_host_v1 host(peer* p) {
    const ml_host_v1 h={sizeof(h),ML_ABI_V1,p,connect_peer,close_peer,poll_peer,write_peer,now_peer,random_peer};
    return h;
}
static ml_client* open_client(peer* p, uint32_t capacity) {
    ml_host_v1 h=host(p); ml_client* c=NULL;
    CHECK(ml_create_tracked_v1(&cfg,&h,capacity,&c)==ML_OK && c!=NULL);
    CHECK(ml_connect_v1(c,"synthetic")==ML_OK && ml_tick_v1(c)==ML_OK);
    return c;
}
static uint64_t track(ml_client* c, uint64_t deadline, ml_status expected) {
    const uint8_t data=42; uint64_t id=99;
    CHECK(ml_send_tracked_v1(c,&data,1,deadline,&id)==expected);
    CHECK((id!=0)==(expected==ML_OK)); return id;
}
static void receive(ml_client* c, uint64_t id, uint32_t outcome) {
    ml_completion_v1 out={sizeof(out),ML_ABI_V1,0,0,17};
    CHECK(ml_next_completion_v1(c,&out)==ML_OK);
    CHECK(out.struct_size==sizeof(out) && out.abi_version==ML_ABI_V1);
    CHECK(out.operation==id && out.outcome==outcome && !out.reserved);
}
static void empty(ml_client* c) {
    ml_completion_v1 out={sizeof(out),ML_ABI_V1,7,8,9};
    CHECK(ml_next_completion_v1(c,&out)==ML_EMPTY);
    CHECK(out.operation==7 && out.outcome==8 && out.reserved==9);
}
int main(void) {
    peer a={0}, b={0}, old={0};
    ml_host_v1 h=host(&old);
    ml_client* c=NULL;
    CHECK(ml_create_tracked_v1(&cfg,&h,0,&c)==ML_INVALID_CONFIG && c==NULL);
    CHECK(ml_create_tracked_v1(&cfg,&h,ML_MAX_TRACKED_COMPLETIONS_V1+1,&c)==ML_INVALID_CONFIG && c==NULL);
    CHECK(ml_create_tracked_v1(&cfg,&h,ML_MAX_TRACKED_COMPLETIONS_V1,&c)==ML_OK);
    ml_destroy_v1(c);
    CHECK(ml_create_v1(&cfg,&h,&c)==ML_OK);
    track(c,100,ML_INVALID_STATE);
    ml_completion_v1 unsupported={sizeof(unsupported),ML_ABI_V1,7,8,9};
    CHECK(ml_next_completion_v1(c,&unsupported)==ML_INVALID_STATE && unsupported.operation==7);
    ml_destroy_v1(c);

    ml_client* x=open_client(&a,2);
    ml_client* y=open_client(&b,1);
    empty(x); empty(y);
    const uint64_t first=track(x,100,ML_OK), second=track(x,100,ML_OK);
    const uint64_t other=track(y,100,ML_OK);
    CHECK(first==other && second>first); // IDs are per handle, not process-global.
    track(x,100,ML_QUEUE_FULL); track(y,100,ML_QUEUE_FULL);
    CHECK(ml_tick_v1(x)==ML_OK && a.accepted==2 && b.accepted==0);
    a.received=19;
    CHECK(ml_tick_v1(x)==ML_OK && !a.received);
    ml_event_v1 z={sizeof(z),ML_ABI_V1,0,0,0,0,NULL,0};
    CHECK(ml_next_event_v1(x,&z)==ML_OK && z.kind==ML_EVENT_RECEIVED);
    CHECK(ml_next_event_v1(x,&z)==ML_OK && z.kind==ML_EVENT_RECEIVED);
    CHECK(ml_next_event_v1(x,&z)==ML_EMPTY); // All write diagnostics really evicted.
    ml_completion_v1 bad={sizeof(bad)-1,ML_ABI_V1,7,8,9};
    CHECK(ml_next_completion_v1(x,&bad)==ML_ABI_MISMATCH && bad.operation==7);
    track(x,100,ML_QUEUE_FULL); // Ready results, not just pending, reserve credit.
    const uint8_t legacy_byte=7; uint64_t legacy_id=0;
    CHECK(ml_send_v1(x,&legacy_byte,1,100,&legacy_id)==ML_OK && legacy_id==second+1);
    receive(x,first,ML_COMPLETION_LOCAL_ACCEPTED);
    const uint64_t cancelled=track(x,100,ML_OK); CHECK(cancelled==legacy_id+1);
    track(x,100,ML_QUEUE_FULL); // Exactly one freed credit.
    CHECK(ml_cancel_v1(x,cancelled)==ML_OK && ml_cancel_v1(x,cancelled)==ML_NOT_FOUND);
    receive(x,second,ML_COMPLETION_LOCAL_ACCEPTED);
    receive(x,cancelled,ML_COMPLETION_CANCELLED);
    CHECK(ml_tick_v1(x)==ML_OK && a.accepted==3); empty(x); // Legacy send never tracked.
    empty(y); CHECK(ml_tick_v1(y)==ML_OK && b.accepted==1);
    receive(y,other,ML_COMPLETION_LOCAL_ACCEPTED);

    a.mode=ML_WRITE_BLOCKED;
    const uint64_t expired=track(x,2,ML_OK);
    CHECK(ml_tick_v1(x)==ML_OK && a.writes==4);
    empty(x);
    a.now=2; CHECK(ml_tick_v1(x)==ML_OK && a.writes==4);
    receive(x,expired,ML_COMPLETION_DEADLINE);
    a.mode=ML_WRITE_ACCEPTED; a.advance_to=4;
    const uint64_t before_clock_jump=track(x,4,ML_OK), after_clock_jump=track(x,4,ML_OK);
    CHECK(ml_tick_v1(x)==ML_OK && a.writes==5);
    receive(x,before_clock_jump,ML_COMPLETION_LOCAL_ACCEPTED);
    receive(x,after_clock_jump,ML_COMPLETION_DEADLINE);
    track(x,4,ML_TIMEOUT); empty(x);

    const uint64_t old_generation=a.generation;
    const uint64_t transport_failed=track(x,100,ML_OK), pending=track(x,100,ML_OK);
    a.mode=ML_WRITE_FAILED; CHECK(ml_tick_v1(x)==ML_OK && a.writes==6);
    receive(x,transport_failed,ML_COMPLETION_TRANSPORT_UNKNOWN);
    receive(x,pending,ML_COMPLETION_TRANSPORT_UNKNOWN);
    a.now=9; a.stale=old_generation; a.mode=ML_WRITE_ACCEPTED;
    CHECK(ml_tick_v1(x)==ML_OK && a.starts==2 && a.writes==6 && a.generation!=old_generation);
    empty(x);
    const uint64_t disconnected=track(x,100,ML_OK);
    a.disconnect=1; CHECK(ml_tick_v1(x)==ML_OK && a.writes==6);
    receive(x,disconnected,ML_COMPLETION_TRANSPORT_UNKNOWN);
    a.now=14; CHECK(ml_tick_v1(x)==ML_OK && a.starts==3 && a.writes==6);
    const uint64_t closing=track(x,100,ML_OK);
    CHECK(ml_close_v1(x)==ML_OK && ml_close_v1(x)==ML_OK && a.writes==6);
    receive(x,closing,ML_COMPLETION_CANCELLED); empty(x);
    ml_destroy_v1(x);

    const uint64_t after_a_destroy=track(y,100,ML_OK);
    CHECK(ml_tick_v1(y)==ML_OK && b.accepted==2);
    receive(y,after_a_destroy,ML_COMPLETION_LOCAL_ACCEPTED); empty(y);
    ml_destroy_v1(y);
    puts("PASS: installed tracked C SDK capacity, terminal results, and handle isolation");
}
