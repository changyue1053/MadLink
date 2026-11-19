#include "state_sink.hpp"
#include <cassert>
#include <iostream>
#include <stdexcept>
using namespace madlink;
using namespace madlink::madobs_adapter;
struct Capture { unsigned calls=0; bool throwing=false; QueuedObserver* queue=nullptr; };
static void capture(void* context,const madobs_event_v1* e) {
    auto& c=*static_cast<Capture*>(context);++c.calls;
    assert(e->monotonic_ns==0 && e->reserved==0 && e->sdk_id==sdk_id && e->attribute_count==1);
    assert(e->attributes[0].key==state_key && e->attributes[0].enum_value<=4);
    for (unsigned i=1;i<MADOBS_MAX_ATTRIBUTES;++i) assert(e->attributes[i].key==0 && e->attributes[i].enum_value==0);
    if(c.queue) { assert(c.queue->drain(10)==0);c.queue->enqueue_state(1); }
    if(c.throwing) throw std::runtime_error("deliberate contract-violating test callback");
}
struct Time final : Clock { uint64_t now_ms() const noexcept override { return 0; } };
struct Rand final : Random { uint64_t next() noexcept override { return 0; } };
struct Wire final : Transport {
    uint64_t generation=0;bool ready=false;unsigned writes=0;
    void connect(const std::string&,uint64_t g) noexcept override {generation=g;ready=true;}
    void close() noexcept override {}
    std::optional<WireEvent> poll() override {if(!ready)return {};ready=false;return WireEvent{WireEvent::Kind::connected,generation,{}};}
    WriteResult write(const Bytes&) noexcept override {++writes;return WriteResult::accepted;}
};
int main() {
    Capture c;madobs_observer_v1 observer{sizeof(observer),MADOBS_ABI_VERSION,&c,capture};
    QueuedObserver queue(observer);StateSink sink(queue);Time time;Rand random;Wire a,b;
    Client observed(a,time,random,{},&sink),plain(b,time,random);
    for(auto* client:{&observed,&plain}) { assert(client->connect("opaque-not-exported")==Error::none);client->tick();assert(client->send({7},100).error==Error::none);client->tick();client->close(); }
    assert(a.writes==b.writes && observed.state()==plain.state() && c.calls==0);
    assert(queue.pending()==3 && queue.drain(1)==1 && c.calls==1);
    c.throwing=true;assert(queue.drain(32)==2 && queue.stats().callback_error==2 && queue.pending()==0);
    assert(observed.state()==plain.state());c.throwing=false;
    for(unsigned i=0;i<40;++i)queue.enqueue_state(i%5);
    queue.enqueue_state(99);assert(queue.pending()==32 && queue.stats().overflow==8 && queue.stats().invalid_state==1);
    c.queue=&queue;assert(queue.drain(1)==1 && queue.stats().reentrant==2);c.queue=nullptr;
    queue.drain(100);assert(queue.pending()==0);
    auto invalid=observer;invalid.abi_version=99;QueuedObserver rejected(invalid);
    rejected.enqueue_state(1);rejected.drain(1);assert(rejected.stats().rejected==1);
    QueuedObserver noop(madobs_noop_observer());noop.enqueue_state(1);noop.drain(1);assert(noop.stats().noop==1);
    const auto before=c.calls;{QueuedObserver discarded(observer);discarded.enqueue_state(1);}assert(c.calls==before);
    std::cout<<"PASS: optional MadObs queue, finite privacy schema, rejection, callback error, no retry/noninterference\n";
}
