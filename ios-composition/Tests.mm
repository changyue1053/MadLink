#import <XCTest/XCTest.h>
#import <MadLink/madlink_c.h>
#include <madobs/runtime.h>
#include <madlink_madobs/queued_observer.hpp>
#include <atomic>
namespace {
using Queue=madlink::madobs_adapter::QueuedObserver;
struct Sink { std::atomic<unsigned> batches{0},invalid{0}; };
void consume(void* p,uint8_t,uint64_t,const uint8_t* bytes,size_t size,madobs_send_done_fn done,void* ctx) {
 auto& s=*static_cast<Sink*>(p);
 bool ok=madobs_check_private_batch(bytes,size,&Queue::policy())==MADOBS_PRIVATE_BATCH_OK;
 ++s.batches;if(!ok)++s.invalid;done(ctx,ok?1:0);
}
struct Owner { madobs_handle_t h=0; ~Owner(){if(h){madobs_stop(h);madobs_destroy(h);}} };
struct Link { ml_client* h=nullptr;~Link(){ml_destroy_v1(h);} };
struct Host { uint64_t generation=0;bool ready=false; };
void connectHost(void* p,const char*,uint64_t g){auto& h=*static_cast<Host*>(p);h.generation=g;h.ready=true;}
void closeHost(void*){}
int32_t pollHost(void* p,ml_wire_event_v1* e){auto& h=*static_cast<Host*>(p);if(!h.ready)return 0;h.ready=false;e->kind=ML_WIRE_CONNECTED;e->generation=h.generation;return 1;}
int32_t writeHost(void*,const uint8_t*,uint64_t){return ML_WRITE_ACCEPTED;}
uint64_t zero(void*){return 0;}
}
@interface MadLinkCompositionTests : XCTestCase
@end
@implementation MadLinkCompositionTests
- (void)testSyntheticStatesReachRealRuntime {
 NSURL* dir=[NSURL fileURLWithPath:[NSTemporaryDirectory() stringByAppendingPathComponent:[@"MadLinkSynthetic-" stringByAppendingString:NSUUID.UUID.UUIDString]]];
 NSError* error=nil;
 BOOL made=[NSFileManager.defaultManager createDirectoryAtURL:dir withIntermediateDirectories:NO attributes:nil error:&error];
 XCTAssertTrue(made);if(!made)return;
 @try {
  Sink sink;Owner owner;owner.h=madobs_create(dir.fileSystemRepresentation,consume,&sink);
  XCTAssertNotEqual(owner.h,(madobs_handle_t)0);if(!owner.h)return;
  auto started=madobs_start(owner.h);XCTAssertEqual(started,MADOBS_OK);if(started!=MADOBS_OK)return;
  madobs_observer_binding_v1 binding{};madobs_observer_v1 observer{};
  auto bound=madobs_observer_for_runtime(owner.h,&binding,&observer);XCTAssertEqual(bound,MADOBS_OK);if(bound!=MADOBS_OK)return;
  Queue queue(observer);Host host;Link link;
  ml_config_v1 config{sizeof(config),ML_ABI_V1,16,1024,64,100,10,100,1};
  ml_host_v1 api{sizeof(api),ML_ABI_V1,&host,connectHost,closeHost,pollHost,writeHost,zero,zero};
  auto created=ml_create_v1(&config,&api,&link.h);XCTAssertEqual(created,ML_OK);if(created!=ML_OK)return;
  XCTAssertEqual(ml_connect_v1(link.h,"synthetic-only"),ML_OK);
  XCTAssertEqual(ml_tick_v1(link.h),ML_OK);XCTAssertEqual(ml_close_v1(link.h),ML_OK);
  ml_event_v1 event{};event.struct_size=sizeof(event);event.abi_version=ML_ABI_V1;
  const uint32_t expected[]={ML_CONNECTING,ML_CONNECTED,ML_CLOSED};unsigned count=0;ml_status status;
  while((status=ml_next_event_v1(link.h,&event))==ML_OK){
   if(event.kind!=ML_EVENT_STATE)continue;
   XCTAssertLessThan(count,3u);if(count>=3)return;
   XCTAssertEqual(event.state,expected[count++]);queue.enqueue_state(event.state);
  }
  XCTAssertEqual(status,ML_EMPTY);XCTAssertEqual(count,3u);XCTAssertEqual(queue.pending(),3u);
  madobs_generic_stats_v1 stats{};
  XCTAssertEqual(madobs_get_generic_stats(owner.h,&stats),MADOBS_OK);XCTAssertEqual(stats.enqueued,(uint64_t)0);
  XCTAssertEqual(queue.drain(32),3u);XCTAssertEqual(queue.stats().callback_invoked,(uint64_t)3);
  // No active producers; synchronous stop joins runtime before inspecting sink.
  XCTAssertEqual(madobs_stop(owner.h),MADOBS_OK);
  XCTAssertEqual(madobs_get_generic_stats(owner.h,&stats),MADOBS_OK);
  XCTAssertEqual(stats.enqueued,(uint64_t)3);XCTAssertEqual(stats.drained,(uint64_t)3);
  XCTAssertEqual(stats.queue_dropped,(uint64_t)0);XCTAssertEqual(stats.wal_dropped,(uint64_t)0);
  XCTAssertGreaterThan(sink.batches.load(),0u);XCTAssertEqual(sink.invalid.load(),0u);
  queue.enqueue_state(ML_CLOSED);XCTAssertEqual(queue.drain(1),1u);
  XCTAssertEqual(queue.stats().callback_invoked,(uint64_t)4);
  XCTAssertEqual(madobs_get_generic_stats(owner.h,&stats),MADOBS_OK);XCTAssertEqual(stats.enqueued,(uint64_t)3);
  XCTAssertEqual(madobs_destroy(owner.h),MADOBS_OK);owner.h=0;
 } @finally { [NSFileManager.defaultManager removeItemAtURL:dir error:nil]; }
}
@end
