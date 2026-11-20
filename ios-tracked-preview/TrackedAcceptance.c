/* Bound send results are separate from the lossy diagnostics. No transport I/O. */
#ifdef MADLINK_TRACKED_XCTEST
#include <MadLink/madlink_c.h>
#else
#include "madlink_c.h"
#endif

#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)
struct peer { uint64_t generation; unsigned ready, received, accepted, fail; };
static void connect_peer(void* context, const char* endpoint, uint64_t generation) {
    struct peer* p=context; (void)endpoint; p->generation=generation; p->ready=1;
}
static void close_peer(void* context) { (void)context; }
static int32_t poll_peer(void* context, ml_wire_event_v1* event) {
    struct peer* p=context;
    event->generation=p->generation;
    if (p->ready) {
        p->ready=0; event->kind=ML_WIRE_CONNECTED; return 1;
    }
    if (p->received) {
        --p->received; event->kind=ML_WIRE_RECEIVED; return 1;
    }
    return 0;
}
static int32_t write_peer(void* context, const uint8_t* data, uint64_t size) {
    struct peer* p=context;
    if (size!=1 || !data || data[0]!=19 || p->fail) return ML_WRITE_FAILED;
    ++p->accepted; return ML_WRITE_ACCEPTED;
}
static uint64_t zero(void* context) { (void)context; return 0; }

static int scenario(ml_client* c, struct peer* p) {
    const uint8_t byte=19;
    uint64_t first=0, second=0, third=99;
    CHECK(ml_connect_v1(c,"synthetic")==ML_OK && ml_tick_v1(c)==ML_OK);
    CHECK(ml_send_tracked_v1(c,&byte,1,100,&first)==ML_OK && first);
    CHECK(ml_send_tracked_v1(c,&byte,1,100,&second)==ML_OK && second>first);
    CHECK(ml_send_tracked_v1(c,&byte,1,100,&third)==ML_QUEUE_FULL && !third);
    CHECK(ml_tick_v1(c)==ML_OK && p->accepted==2);
    p->received=9;
    CHECK(ml_tick_v1(c)==ML_OK && !p->received);
    ml_event_v1 event={sizeof(event),ML_ABI_V1,0,0,0,0,0,0};
    CHECK(ml_next_event_v1(c,&event)==ML_OK && event.kind==ML_EVENT_RECEIVED);
    CHECK(ml_next_event_v1(c,&event)==ML_OK && event.kind==ML_EVENT_RECEIVED);
    CHECK(ml_next_event_v1(c,&event)==ML_EMPTY); /* all successful write diagnostics evicted */
    CHECK(ml_send_tracked_v1(c,&byte,1,100,&third)==ML_QUEUE_FULL && !third);
    ml_completion_v1 out={sizeof(out),ML_ABI_V1,0,0,0};
    CHECK(ml_next_completion_v1(c,&out)==ML_OK && out.operation==first &&
          out.outcome==ML_COMPLETION_LOCAL_ACCEPTED);
    CHECK(ml_send_tracked_v1(c,&byte,1,100,&third)==ML_OK && third>second);
    CHECK(ml_cancel_v1(c,third)==ML_OK && ml_cancel_v1(c,third)==ML_NOT_FOUND);
    CHECK(ml_next_completion_v1(c,&out)==ML_OK && out.operation==second &&
          out.outcome==ML_COMPLETION_LOCAL_ACCEPTED);
    CHECK(ml_next_completion_v1(c,&out)==ML_OK && out.operation==third &&
          out.outcome==ML_COMPLETION_CANCELLED);
    CHECK(ml_next_completion_v1(c,&out)==ML_EMPTY);
    uint64_t uncertain=0;
    CHECK(ml_send_tracked_v1(c,&byte,1,100,&uncertain)==ML_OK && uncertain>third);
    p->fail=1;
    CHECK(ml_tick_v1(c)==ML_OK && p->accepted==2);
    CHECK(ml_next_completion_v1(c,&out)==ML_OK && out.operation==uncertain &&
          out.outcome==ML_COMPLETION_TRANSPORT_UNKNOWN);
    CHECK(ml_next_completion_v1(c,&out)==ML_EMPTY);
    CHECK(ml_close_v1(c)==ML_OK);
    return 0;
}

int madlinkTrackedAcceptance(void) {
    struct peer p={0};
    ml_client* c=0;
    const ml_config_v1 config={sizeof(config),ML_ABI_V1,8,16,2,100,10,20,1};
    const ml_host_v1 host={sizeof(host),ML_ABI_V1,&p,connect_peer,close_peer,poll_peer,write_peer,zero,zero};
    CHECK(ml_create_tracked_v1(&config,&host,2,&c)==ML_OK && c);
    const int result=scenario(c,&p);
    ml_destroy_v1(c);
    return result;
}
