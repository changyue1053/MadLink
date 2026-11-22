#include "madlink_c.h"
#include <assert.h>
#include <stdio.h>
struct host { uint64_t generation; int ready, writes, closes; };
static void connect_cb(void* u, const char* endpoint, uint64_t g) {
    struct host* h=u; assert(endpoint[0]); h->generation=g; h->ready=1;
}
static void close_cb(void* u) { ((struct host*)u)->closes++; }
static int32_t poll_cb(void* u, ml_wire_event_v1* e) {
    struct host* h=u;
    if (!h->ready) return 0;
    h->ready=0; e->kind=ML_WIRE_CONNECTED; e->generation=h->generation; return 1;
}
static int32_t write_cb(void* u, const uint8_t* b, uint64_t n) {
    assert(n==3 && b[0]==0 && b[2]==255); ((struct host*)u)->writes++; return ML_WRITE_ACCEPTED;
}
static uint64_t zero(void* u) { (void)u; return 0; }
int main(void) {
    struct host h={0}; ml_client* c=NULL; uint64_t id=0; int written=0;
    ml_config_v1 cfg={sizeof(cfg),ML_ABI_V1,16,1024,64,100,10,100,2};
    ml_host_v1 host={sizeof(host),ML_ABI_V1,&h,connect_cb,close_cb,poll_cb,write_cb,zero,zero};
    ml_event_v1 event={0}; const uint8_t bytes[]={0,1,255};
    event.struct_size=sizeof(event); event.abi_version=ML_ABI_V1;
    assert(ml_create_v1(&cfg,&host,&c)==ML_OK);
    assert(ml_connect_v1(c,"app-a")==ML_OK && ml_tick_v1(c)==ML_OK);
    assert(ml_send_v1(c,bytes,sizeof(bytes),100,&id)==ML_OK && id);
    assert(ml_tick_v1(c)==ML_OK && h.writes==1);
    while (ml_next_event_v1(c,&event)==ML_OK)
        if (event.kind==ML_EVENT_WRITTEN && event.operation==id) written++;
    assert(written==1);
    assert(ml_close_v1(c)==ML_OK); ml_destroy_v1(c); assert(h.closes==2);
    puts("PASS: independent C consumer A send lifecycle"); return 0;
}
