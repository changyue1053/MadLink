#include "curl_transport.hpp"
#include "frame_buffer.hpp"
#include <curl/curl.h>
#include <array>
#include <algorithm>
#include <chrono>
#include <limits>
#include <stdexcept>
#include <utility>
namespace madlink {
namespace {
std::uint64_t steady_ms() noexcept {
    return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}
}
struct CurlTransport::Impl {
    Options options;
    CURL* easy = nullptr;
    CURLM* multi = nullptr;
    bool attached = false, established = false, disconnected = false;
    std::uint64_t generation = 0;
    std::uint64_t accepted_at = 0;
    curl_detail::FrameBuffer outbound;
    Bytes inbound;
    explicit Impl(Options o) : options(std::move(o)) {
        if (!options.max_message_bytes || !options.flush_timeout_ms || options.max_message_bytes > static_cast<std::size_t>(std::numeric_limits<curl_off_t>::max()))
            throw std::invalid_argument("invalid curl message limit");
    }
    void reset() noexcept {
        if (attached) curl_multi_remove_handle(multi, easy);
        if (easy) curl_easy_cleanup(easy);
        if (multi) curl_multi_cleanup(multi);
        easy=nullptr;multi=nullptr;attached=false;established=false;disconnected=false;
        outbound.clear();inbound.clear();
    }
    void fail() noexcept { reset(); disconnected=true; }
    std::optional<WireEvent> failure() {
        fail();disconnected=false;
        return WireEvent{WireEvent::Kind::disconnected,generation,{}};
    }
};
CurlTransport::CurlTransport(Options o) : impl_(std::make_unique<Impl>(std::move(o))) {}
CurlTransport::~CurlTransport() { close(); }
void CurlTransport::close() noexcept { impl_->reset(); }
void CurlTransport::connect(const std::string& endpoint, std::uint64_t generation) noexcept {
    auto& p=*impl_;p.reset();p.generation=generation;
    // Restrict schemes even when a system libcurl supports unrelated protocols.
    if (endpoint.compare(0,6,"wss://") != 0) { p.fail();return; }
    p.easy=curl_easy_init();p.multi=curl_multi_init();
    if (!p.easy || !p.multi) { p.fail();return; }
    bool ok=true;
    auto set=[&](CURLoption key, auto value) { if (curl_easy_setopt(p.easy,key,value)!=CURLE_OK) ok=false; };
    set(CURLOPT_URL,endpoint.c_str());set(CURLOPT_PROTOCOLS_STR,"wss");
    set(CURLOPT_CONNECT_ONLY,2L);set(CURLOPT_HTTP_VERSION,CURL_HTTP_VERSION_1_1);
    set(CURLOPT_SSL_VERIFYPEER,1L);set(CURLOPT_SSL_VERIFYHOST,2L);
    set(CURLOPT_PROXY,"");set(CURLOPT_FOLLOWLOCATION,0L);set(CURLOPT_NOSIGNAL,1L);
    set(CURLOPT_DISALLOW_USERNAME_IN_URL,1L);
    set(CURLOPT_CONNECTTIMEOUT_MS,5000L);
    if (!p.options.ca_file.empty()) set(CURLOPT_CAINFO,p.options.ca_file.c_str());
    if (!ok || curl_multi_add_handle(p.multi,p.easy)!=CURLM_OK) { p.fail();return; }
    p.attached=true;
}
WriteResult CurlTransport::write(const Bytes& bytes) noexcept {
    auto& p=*impl_;
    if (!p.established || bytes.size()>p.options.max_message_bytes) return WriteResult::failed;
    if (p.outbound.occupied) return WriteResult::blocked;
    try { p.outbound.put(bytes,p.options.max_message_bytes); }
    catch (...) { p.fail();return WriteResult::failed; }
    p.accepted_at=steady_ms();
    return WriteResult::accepted;
}
std::optional<WireEvent> CurlTransport::poll() {
    auto& p=*impl_;
    if (p.disconnected) { p.disconnected=false;return WireEvent{WireEvent::Kind::disconnected,p.generation,{}}; }
    if (!p.easy) return {};
    if (!p.established) {
        int running=0;
        if (curl_multi_perform(p.multi,&running)!=CURLM_OK) return p.failure();
        int remaining=0;
        while (auto* info=curl_multi_info_read(p.multi,&remaining)) {
            if (info->msg!=CURLMSG_DONE) continue;
            long code=0;
            if (info->data.result!=CURLE_OK || curl_easy_getinfo(p.easy,CURLINFO_RESPONSE_CODE,&code)!=CURLE_OK || code!=101)
                return p.failure();
            p.established=true;
            return WireEvent{WireEvent::Kind::connected,p.generation,{}};
        }
        return {};
    }
    if (p.outbound.occupied) {
        // Independent of Core's pre-acceptance deadline. Bound full-duplex
        // starvation even if no send progress/peer-close read is possible.
        if (steady_ms()-p.accepted_at>=p.options.flush_timeout_ms) return p.failure();
        static const unsigned char empty=0;
        const auto remaining=p.outbound.bytes.size()-p.outbound.offset;
        const auto* data=remaining ? p.outbound.bytes.data()+p.outbound.offset : &empty;
        size_t sent=0;
        // Explicit single-frame chunking: first call declares full frame size;
        // later calls use zero fragsize. Never restart a frame for the remainder.
        // Cap each invocation so loopback tests exercise this path deterministically.
        const auto total=p.outbound.bytes.size();
        const auto frame_size=p.outbound.started ? 0 : static_cast<curl_off_t>(total);
        const auto flags=total ? CURLWS_BINARY|CURLWS_OFFSET : CURLWS_BINARY;
        const auto result=curl_ws_send(p.easy,data,std::min(remaining,std::size_t{4096}),&sent,frame_size,flags);
        if (result!=CURLE_OK && result!=CURLE_AGAIN) return p.failure();
        try { p.outbound.consumed(sent,result==CURLE_OK); }
        catch (...) { return p.failure(); }
        // recv may auto-send PONG. Never let that insert a control frame inside
        // a partially emitted frame's payload (control frames may interleave
        // between frames, not between chunks of the same frame).
        if (p.outbound.occupied) return {};
    }
    // Bounded per-poll work. Core also bounds calls per tick.
    std::array<unsigned char,4096> chunk{};
    for (unsigned i=0;i<16;++i) {
        size_t count=0;const curl_ws_frame* meta=nullptr;
        const auto result=curl_ws_recv(p.easy,chunk.data(),chunk.size(),&count,&meta);
        if (result==CURLE_AGAIN) return {};
        if (result!=CURLE_OK || !meta) return p.failure();
        const auto flags=meta->flags;
        if (flags&CURLWS_CLOSE) return p.failure();
        if (flags&(CURLWS_PING|CURLWS_PONG)) continue; // libcurl handles automatic PONG.
        if (!(flags&CURLWS_BINARY) || meta->bytesleft<0 || count>p.options.max_message_bytes-p.inbound.size())
            return p.failure();
        const auto budget=p.options.max_message_bytes-p.inbound.size()-count;
        if (static_cast<std::uint64_t>(meta->bytesleft)>budget) return p.failure();
        p.inbound.insert(p.inbound.end(),chunk.begin(),chunk.begin()+count);
        if (meta->bytesleft==0 && !(flags&CURLWS_CONT)) {
            Bytes message;message.swap(p.inbound);
            return WireEvent{WireEvent::Kind::received,p.generation,std::move(message)};
        }
    }
    return {};
}
}
