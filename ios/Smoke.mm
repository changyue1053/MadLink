#import <Foundation/Foundation.h>
#import <MadLink/madlink_c.h>
struct Host { uint64_t generation=0; bool ready=false; unsigned writes=0; };
static void connectHost(void* p,const char*,uint64_t g) { auto& h=*static_cast<Host*>(p);h.generation=g;h.ready=true; }
static void closeHost(void*) {}
static int32_t pollHost(void* p,ml_wire_event_v1* e) { auto& h=*static_cast<Host*>(p);if(!h.ready)return 0;h.ready=false;e->kind=ML_WIRE_CONNECTED;e->generation=h.generation;return 1; }
static int32_t writeHost(void* p,const uint8_t*,uint64_t) { ++static_cast<Host*>(p)->writes;return ML_WRITE_ACCEPTED; }
static uint64_t zero(void*) { return 0; }
extern "C" int madlinkSmoke() {
 Host h;ml_client* c=nullptr;
 ml_config_v1 cfg{sizeof(cfg),ML_ABI_V1,16,1024,64,100,10,100,1};
 ml_host_v1 api{sizeof(api),ML_ABI_V1,&h,connectHost,closeHost,pollHost,writeHost,zero,zero};
 if(ml_create_v1(&cfg,&api,&c)!=ML_OK)return 1;
 uint64_t op=0;const uint8_t bytes[]={1,2,3};
 bool ok=ml_connect_v1(c,"synthetic-only")==ML_OK&&ml_tick_v1(c)==ML_OK&&
 ml_send_v1(c,bytes,3,100,&op)==ML_OK&&ml_tick_v1(c)==ML_OK&&h.writes==1;
 ml_event_v1 e{};e.struct_size=sizeof(e);e.abi_version=ML_ABI_V1;bool written=false;ml_status status;
 while((status=ml_next_event_v1(c,&e))==ML_OK)if(e.kind==ML_EVENT_WRITTEN&&e.operation==op)written=true;
 ok=ok&&written&&status==ML_EMPTY&&ml_close_v1(c)==ML_OK;ml_destroy_v1(c);return ok?0:2;
}
