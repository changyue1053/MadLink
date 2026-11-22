// Standalone two-client consumer. No curl linker wrappers or shared adapters.
#include "curl_transport.hpp"
#include <curl/curl.h>
#include <chrono>
#include <deque>
#include <iostream>
#include <stdexcept>
#include <thread>
using namespace madlink;
static void check(bool pass) { if (!pass) throw std::runtime_error("acceptance"); }
struct Monotonic final : Clock {
    uint64_t now_ms() const noexcept override {
        return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count());
    }
};
struct Zero final : Random { uint64_t next() noexcept override { return 0; } };
struct CurlLifetime {
    CurlLifetime() { check(curl_global_init(CURL_GLOBAL_DEFAULT)==CURLE_OK); }
    ~CurlLifetime() { curl_global_cleanup(); }
};
struct Session {
    Monotonic clock;
    Zero random;
    CurlTransport transport;
    Client client;
    std::deque<Event> expected;
    uint64_t last_operation=0;

    explicit Session(const char* ca)
        : transport({ca}), client(transport,clock,random,[] {Config c;c.max_retries=0;return c;}()) {}
    void connect(const std::string& url) {
        check(client.connect(url)==Error::none);
        expected.push_back({EventKind::state,State::connecting});
        expected.push_back({EventKind::state,State::connected});
    }
    uint64_t send(const Bytes& bytes) {
        const auto r=client.send(bytes,clock.now_ms()+3000);
        check(r.error==Error::none && r.operation>last_operation);
        return last_operation=r.operation;
    }
    void receive(const Bytes& bytes) {
        expected.push_back({EventKind::received,State::connected,Error::none,0,bytes});
    }
    void exchange(const Bytes& outbound,const Bytes& inbound) {
        expected.push_back({EventKind::written,State::connected,Error::none,send(outbound)});
        receive(inbound);
    }
    void close(uint64_t pending=0) {
        if (pending) expected.push_back({EventKind::failed,client.state(),Error::cancelled,pending});
        client.close();
        expected.push_back({EventKind::state,State::closed});
    }
    void tick() {
        client.tick();
        while (auto event=client.next_event()) {
            check(!expected.empty());
            const auto& e=expected.front();
            check(event->kind==e.kind && event->state==e.state && event->error==e.error &&
                  event->operation==e.operation && event->data==e.data);
            expected.pop_front();
        }
        check(!client.dropped_events());
    }
};
static std::string local_url(std::string port) {
    check(!port.empty() && port.size()<=5 && port.find_first_not_of("0123456789")==std::string::npos);
    const auto number=std::stoul(port);
    check(number>0 && number<=65535);
    return "wss://localhost:"+port+"/isolation";
}
int main(int argc,char** argv) {
    if (argc!=4) return 2;
    const char* stage="setup";
    try {
        const CurlLifetime curl;
        const auto url_a=local_url(argv[1]),url_b=local_url(argv[2]);
        check(url_a!=url_b);
        Session a(argv[3]),b(argv[3]);
        const auto pump=[&](bool wait_a=true) {
            const auto deadline=a.clock.now_ms()+4000;
            do {
                a.tick();
                b.tick();
                if ((!wait_a || a.expected.empty()) && b.expected.empty()) return;
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            } while (a.clock.now_ms()<deadline);
            check(false);
        };
        stage="initial";
        a.connect(url_a);b.connect(url_b);pump();
        a.exchange({'A',0,1},{'a',0,1});b.exchange({'B',0,1},{'b',0,1});pump();
        stage="reconnect";
        const auto stale=a.send({'A',0,99}); // Queue, explicitly close before any tick.
        a.close(stale);pump();
        check(!a.client.queued_bytes());
        a.connect(url_a);a.receive({'g','o'});
        b.exchange({'B',0,2},{'b',0,2});pump(false);
        check(a.client.state()==State::connecting);
        b.exchange({'B',0,4},{'b',0,4});pump();
        stage="fresh";
        a.exchange({'A',0,2},{'a',0,2});a.receive({'d','o','n','e'});pump();
        b.exchange({'B',0,3},{'b',0,3});pump();
        stage="shutdown";
        a.close();b.close();pump();
        check(a.client.state()==State::closed && b.client.state()==State::closed);
        std::cout<<"PASS: exact two-client Core events and continued B traffic\n";
        return 0;
    } catch (const std::exception&) {
        std::cerr<<"FAIL: WSS isolation client "<<stage<<'\n';
        return 1;
    }
}
