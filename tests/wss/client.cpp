#include "curl_transport.hpp"
#include "frame_buffer.hpp"
#include <curl/curl.h>
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <thread>
using namespace madlink;
// Test-only linker wrapper: handshake/TLS are real; send-side EAGAIN is forced.
static bool force_send_stall=false;
static unsigned stalled_send_calls=0;
static bool partial_then_stall=false;
static size_t real_prefix_bytes=0;
static const void* retry_pointer=nullptr;
static size_t retry_size=0;
static bool retry_contract_ok=true;
static bool saw_incomplete_old_message=false;
extern "C" CURLcode __real_curl_ws_recv(CURL*,void*,size_t,size_t*,const curl_ws_frame**);
extern "C" CURLcode __wrap_curl_ws_recv(CURL* c,void* b,size_t n,size_t* count,const curl_ws_frame** meta) {
    const auto result=__real_curl_ws_recv(c,b,n,count,meta);
    if (partial_then_stall && result==CURLE_OK && *meta && ((*meta)->flags&CURLWS_CONT) && *count==5) {
        const auto* data=static_cast<const uint8_t*>(b);
        if (Bytes(data,data+5)==Bytes({'S','T','A','L','E'})) saw_incomplete_old_message=true;
    }
    return result;
}
extern "C" CURLcode __real_curl_ws_send(CURL*,const void*,size_t,size_t*,curl_off_t,unsigned int);
extern "C" CURLcode __wrap_curl_ws_send(CURL* c,const void* b,size_t n,size_t* sent,curl_off_t total,unsigned int flags) {
    if (force_send_stall) {
        if (partial_then_stall) {
            if (!retry_pointer) { retry_pointer=b;retry_size=n; }
            if (retry_pointer!=b || retry_size!=n || total!=0) retry_contract_ok=false;
        }
        ++stalled_send_calls;*sent=0;return CURLE_AGAIN;
    }
    const auto result=__real_curl_ws_send(c,b,n,sent,total,flags);
    if (partial_then_stall && result==CURLE_OK && *sent>0) {
        real_prefix_bytes=*sent;force_send_stall=true;
    }
    return result;
}
static void check(bool ok,const char* message) { if (!ok) throw std::runtime_error(message); }
struct RealClock final : Clock {
    uint64_t now_ms() const noexcept override {
        return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count());
    }
};
struct RandomZero final : Random { uint64_t next() noexcept override { return 0; } };
static void reconnect_integration(const char* url,const char* ca) {
    CurlTransport transport({ca,65536,100});RealClock clock;RandomZero random;
    Config config;config.max_retries=1;config.retry_base_ms=10;config.retry_cap_ms=10;
    Client client(transport,clock,random,config);
    partial_then_stall=true;
    check(client.connect(url)==Error::none,"reconnect initial connect");
    Bytes old(32768);for (size_t i=0;i<old.size();++i) old[i]=static_cast<uint8_t>(i%251);
    const Bytes fresh={'f','r','e','s','h'};
    unsigned connections=0,written=0,backoffs=0;bool got_fresh=false;
    uint64_t first_accepted=0;
    const auto end=clock.now_ms()+5000;
    while (clock.now_ms()<end && client.state()!=State::closed) {
        client.tick();
        while (auto e=client.next_event()) {
            if (e->kind==EventKind::state && e->state==State::connected) {
                ++connections;
                if (connections==2) {
                    check(real_prefix_bytes>0 && real_prefix_bytes<old.size() && stalled_send_calls>0 && retry_contract_ok,"partial then AGAIN proven");
                    check(saw_incomplete_old_message,"old incomplete receive actually observed");
                    check(first_accepted && clock.now_ms()-first_accepted>=90 && clock.now_ms()-first_accepted<1500,"partial flush timeout bound");
                    partial_then_stall=false;force_send_stall=false;
                }
            }
            if (e->kind==EventKind::state && e->state==State::backoff) ++backoffs;
            if (e->kind==EventKind::written) { ++written;if (written==1) first_accepted=clock.now_ms(); }
            if (e->kind==EventKind::received) {
                if (connections==1 && e->data==Bytes({'s','t','a','r','t'}))
                    check(client.send(old,clock.now_ms()+2000).error==Error::none,"old send");
                else if (connections==2 && e->data==Bytes({'g','o'}))
                    check(client.send(fresh,clock.now_ms()+2000).error==Error::none,"fresh send");
                else if (connections==2 && e->data==fresh) got_fresh=true;
                else throw std::runtime_error("stale inbound bytes/event after reconnect");
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    check(connections==2 && written==2 && backoffs==1 && got_fresh && client.state()==State::closed,"reconnect/no replay lifecycle");
    std::cout << "PASS: real partial frame (" << real_prefix_bytes << " bytes), forced AGAIN timeout, real TLS reconnect with no stale buffers/replay\n";
}
static void core_integration(const char* url,const char* ca) {
    CurlTransport transport({ca,65536});RealClock clock;RandomZero random;
    Config config;config.max_retries=0;
    Client client(transport,clock,random,config);
    check(client.connect(url)==Error::none,"core connect");
    Bytes expected(32768);for (size_t i=0;i<expected.size();++i) expected[i]=static_cast<uint8_t>(i%251);
    bool wrote=false,fragment=false,echo=false;
    const auto end=clock.now_ms()+8000;
    while (clock.now_ms()<end && client.state()!=State::closed) {
        client.tick();
        while (auto event=client.next_event()) {
            if (event->kind==EventKind::state && event->state==State::connected)
                check(client.send(expected,clock.now_ms()+5000).error==Error::none,"core send");
            if (event->kind==EventKind::written) wrote=true;
            if (event->kind==EventKind::received) {
                if (event->data==expected) echo=true;
                if (event->data==Bytes({'a','b','c',0,'x','y','z'})) fragment=true;
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    check(wrote && fragment && echo && client.state()==State::closed,"core network lifecycle");
}
static void partial_progress_test() {
    curl_detail::FrameBuffer frame;
    check(frame.put({1,2,3,4},4),"buffer put");
    check(!frame.put({5},4),"occupied blocked");
    frame.consumed(1,true);check(frame.offset==1 && frame.occupied,"partial progress");
    frame.consumed(0,false);check(frame.offset==1,"AGAIN retains offset");
    frame.consumed(3,true);check(!frame.occupied,"frame done");
    check(frame.put({},4),"empty put");frame.consumed(0,true);check(!frame.occupied,"empty done");
}
int main(int argc,char** argv) {
    if (argc!=4) return 2;
    check(curl_global_init(CURL_GLOBAL_DEFAULT)==CURLE_OK,"global init");
    int exit_code=0;
    try {
        partial_progress_test();
        const std::string mode=argv[3];
        const bool stall=mode=="stall" || mode=="stall-close";
        force_send_stall=stall;
        if (mode=="reconnect") {
            reconnect_integration(argv[1],argv[2]);
        } else if (mode=="core") {
            core_integration(argv[1],argv[2]);
            std::cout << "PASS: Core plus optional WSS lifecycle\n";
        } else {
        CurlTransport transport({argv[2],65536,stall ? 100u : 5000u});
        transport.connect(argv[1],77);
        bool connected=false,fragment=false,echo=false,closed=false;
        auto accepted_time=std::chrono::steady_clock::now();
        Bytes expected(32768);for (size_t i=0;i<expected.size();++i) expected[i]=static_cast<uint8_t>(i%251);
        const auto end=std::chrono::steady_clock::now()+std::chrono::seconds(8);
        while (std::chrono::steady_clock::now()<end) {
            auto event=transport.poll();
            if (event) {
                check(event->generation==77,"generation");
                if (event->kind==WireEvent::Kind::connected) {
                    connected=true;
                    if (mode=="reject") throw std::runtime_error("certificate unexpectedly accepted");
                    if (mode=="normal" || stall) {
                        auto mutable_data=expected;
                        check(transport.write(mutable_data)==WriteResult::accepted,"local acceptance");
                        accepted_time=std::chrono::steady_clock::now();
                        mutable_data.assign(1,99);
                        check(transport.write({9})==WriteResult::blocked,"bounded slot blocks without send");
                    }
                } else if (event->kind==WireEvent::Kind::received) {
                    if (event->data==Bytes({'a','b','c',0,'x','y','z'})) fragment=true;
                    else if (event->data==expected) echo=true;
                    else throw std::runtime_error("unexpected received payload");
                } else { closed=true;break; }
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        check(closed,"timeout waiting for close/rejection");
        if (mode=="normal") check(connected && fragment && echo,"binary echo/fragment missing");
        if (mode=="oversize") check(connected && !echo,"oversize flow");
        if (stall) {
            check(connected && !echo && stalled_send_calls>0,"forced blocked send");
            const auto elapsed=std::chrono::steady_clock::now()-accepted_time;
            check(elapsed>=std::chrono::milliseconds(90) && elapsed<std::chrono::milliseconds(1500),"bounded local flush timeout");
            const auto calls=stalled_send_calls;
            check(!transport.poll() && stalled_send_calls==calls,"failed buffer not replayed");
            check(transport.write({1})==WriteResult::failed,"failed connection rejects new write");
        }
        transport.close();transport.close();
        check(!transport.poll(),"closed adapter silent");
        std::cout << "PASS: loopback WSS " << mode << "\n";
        }
    } catch (const std::exception& e) { std::cerr << "FAIL: " << e.what() << "\n";exit_code=1; }
    curl_global_cleanup();return exit_code;
}
