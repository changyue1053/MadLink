#include <madlink_c.h>
#include <madlink_madobs/queued_observer.hpp>
#include <cassert>
#include <iostream>
struct Host { uint64_t generation=0;bool ready=false; };
static void connect_host(void* u,const char*,uint64_t g) {auto& h=*static_cast<Host*>(u);h.generation=g;h.ready=true;}
static void close_host(void*) {}
static int32_t poll_host(void* u,ml_wire_event_v1* e) {auto& h=*static_cast<Host*>(u);if(!h.ready)return 0;h.ready=false;e->kind=ML_WIRE_CONNECTED;e->generation=h.generation;return 1;}
static int32_t write_host(void*,const uint8_t*,uint64_t) {return ML_WRITE_ACCEPTED;}
static uint64_t zero(void*) {return 0;}
static void observer(void* u,const madobs_event_v1* e) {
    ++*static_cast<unsigned*>(u);assert(e->monotonic_ns==0 && e->attribute_count==1 && e->attributes[0].enum_value<=4);
}
int main() {
    Host host;ml_client* c=nullptr;unsigned calls=0;
    madobs_observer_v1 obs{sizeof(obs),MADOBS_ABI_VERSION,&calls,observer};
    madlink::madobs_adapter::QueuedObserver queue(obs);
    ml_config_v1 cfg{sizeof(cfg),ML_ABI_V1,16,1024,64,100,10,100,1};
    ml_host_v1 api{sizeof(api),ML_ABI_V1,&host,connect_host,close_host,poll_host,write_host,zero,zero};
    assert(ml_create_v1(&cfg,&api,&c)==ML_OK && ml_connect_v1(c,"not-exported")==ML_OK && ml_tick_v1(c)==ML_OK && ml_close_v1(c)==ML_OK);
    ml_event_v1 event{};event.struct_size=sizeof(event);event.abi_version=ML_ABI_V1;
    while(ml_next_event_v1(c,&event)==ML_OK)if(event.kind==ML_EVENT_STATE)queue.enqueue_state(event.state);
    ml_destroy_v1(c);assert(calls==0 && queue.pending()==3);
    assert(queue.drain(32)==3 && calls==3 && queue.stats().callback_invoked==3);
    std::cout<<"PASS: installed core C SDK + staged pinned MadObs API + optional queue header consumer (no runtime)\n";
}
