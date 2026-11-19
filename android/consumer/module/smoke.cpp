#include <jni.h>
#include <madlink_c.h>
namespace {
struct Host { uint64_t generation=0; bool ready=false; unsigned writes=0; };
void connect(void* u,const char*,uint64_t g) { auto& h=*static_cast<Host*>(u);h.generation=g;h.ready=true; }
void close(void*) {}
int32_t poll(void* u,ml_wire_event_v1* e) { auto& h=*static_cast<Host*>(u);if(!h.ready)return 0;h.ready=false;e->kind=ML_WIRE_CONNECTED;e->generation=h.generation;return 1; }
int32_t write(void* u,const uint8_t*,uint64_t) { ++static_cast<Host*>(u)->writes;return ML_WRITE_ACCEPTED; }
uint64_t zero(void*) { return 0; }
}
extern "C" JNIEXPORT jint JNICALL Java_org_madlink_preview_MainActivity_runSmoke(JNIEnv*,jclass) {
 Host h;ml_client* c=nullptr;
 ml_config_v1 cfg{sizeof(cfg),ML_ABI_V1,16,1024,64,100,10,100,1};
 ml_host_v1 api{sizeof(api),ML_ABI_V1,&h,connect,close,poll,write,zero,zero};
 if(ml_create_v1(&cfg,&api,&c)!=ML_OK)return 1;
 const uint8_t payload[]={1,2,3};uint64_t op=0;
 bool ok=ml_connect_v1(c,"synthetic-only")==ML_OK && ml_tick_v1(c)==ML_OK &&
   ml_send_v1(c,payload,sizeof(payload),100,&op)==ML_OK && ml_tick_v1(c)==ML_OK && h.writes==1;
 ml_event_v1 e{};e.struct_size=sizeof(e);e.abi_version=ML_ABI_V1;bool written=false;ml_status status;
 while((status=ml_next_event_v1(c,&e))==ML_OK)if(e.kind==ML_EVENT_WRITTEN&&e.operation==op)written=true;
 ok=ok&&status==ML_EMPTY&&written&&ml_close_v1(c)==ML_OK;
 ml_destroy_v1(c);return ok?0:2;
}
