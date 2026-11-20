#import <XCTest/XCTest.h>
#import <Network/Network.h>
#import <Security/Security.h>
#import <Security/SecProtocolOptions.h>
#import <Security/SecProtocolTypes.h>
#import <TargetConditionals.h>
#include <MadLink/madlink_c.h>
#include "LoopbackJob.inc"
#include <array>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>

#if !TARGET_OS_SIMULATOR || !defined(__arm64__)
#error This case requires native ARM64 iOS Simulator.
#endif

namespace {
using Clock = std::chrono::steady_clock;
using Bytes = std::array<uint8_t, 4>;
constexpr Bytes request{0, 255, 77, 76}, reply{76, 77, 255, 0};
constexpr char loopback[] = "127.0.0.1";
uint64_t milliseconds() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now().time_since_epoch()).count();
}

bool evaluate(SecTrustRef trust, SecCertificateRef anchor, CFStringRef ip) {
    if (!trust || !anchor) return false;
    const void* entries[] = {anchor};
    CFArrayRef anchors = CFArrayCreate(nullptr, entries, 1, &kCFTypeArrayCallBacks);
    SecPolicyRef policy = SecPolicyCreateSSL(true, ip);
    const bool ok = anchors && policy &&
        SecTrustSetPolicies(trust, policy) == errSecSuccess &&
        SecTrustSetAnchorCertificates(trust, anchors) == errSecSuccess &&
        SecTrustSetAnchorCertificatesOnly(trust, true) == errSecSuccess &&
        SecTrustSetNetworkFetchAllowed(trust, false) == errSecSuccess &&
        SecTrustEvaluateWithError(trust, nullptr);
    if (policy) CFRelease(policy);
    if (anchors) CFRelease(anchors);
    return ok;
}

// To attribute rejection specifically to address identity rather than a broken
// fixture chain, the same peer leaf must pass with its known test-only IP.
bool alternate_identity(SecTrustRef offered, SecCertificateRef anchor) {
    if (!offered || !anchor) return false;
    CFArrayRef chain = SecTrustCopyCertificateChain(offered);
    if (!chain) return false;
    SecPolicyRef policy = SecPolicyCreateSSL(true, CFSTR("127.0.0.2"));
    SecTrustRef probe = nullptr;
    const bool match = policy &&
        SecTrustCreateWithCertificates(chain, policy, &probe) == errSecSuccess &&
        evaluate(probe, anchor, CFSTR("127.0.0.2"));
    if (probe) CFRelease(probe);
    if (policy) CFRelease(policy);
    CFRelease(chain);
    return match;
}

struct State {
    std::mutex mutex;
    dispatch_semaphore_t changed = dispatch_semaphore_create(0);
    bool open = false, ready_event = false, data_event = false, closed = false;
    bool disconnect_event = false, trust_ok = false, wrong_san = false, bad = false;
    bool sent = false;
    Bytes incoming{};
};

struct Adapter {
    std::shared_ptr<State> state = std::make_shared<State>();
    dispatch_queue_t callbacks = dispatch_queue_create("org.madlink.loopback.callback", DISPATCH_QUEUE_SERIAL);
    nw_connection_t connection = nullptr;
    uint64_t generation = 0;
    uint16_t port;
    bool wrong;
    Bytes borrowed{};
    explicit Adapter(uint16_t p, bool w) : port(p), wrong(w) {}
    ~Adapter() { close(); }

    void close() {
        if (connection) {
            nw_connection_set_state_changed_handler(connection, nullptr);
            nw_connection_cancel(connection);
            connection = nullptr;
        }
    }
    void connect(const char* endpoint, uint64_t next) {
        const auto s = state;
        if (!endpoint || std::strcmp(endpoint, "owned-fixture") != 0 || connection || generation != 0) {
            std::lock_guard<std::mutex> guard(s->mutex);
            s->bad = true;
            dispatch_semaphore_signal(s->changed);
            return;
        }
        generation = next;
        const auto listener = port;
        const bool deny = wrong;
        NSData* certificate = [NSData dataWithBytes:kRootDer length:sizeof(kRootDer)];
        const auto params = nw_parameters_create_secure_tcp(^(nw_protocol_options_t tls) {
            auto options = nw_tls_copy_sec_protocol_options(tls);
            sec_protocol_options_set_min_tls_protocol_version(options, tls_protocol_version_TLSv12);
            sec_protocol_options_set_verify_block(options, ^(sec_protocol_metadata_t, sec_trust_t value,
                                                               sec_protocol_verify_complete_t complete) {
                SecTrustRef trust = sec_trust_copy_ref(value);
                SecCertificateRef ca = SecCertificateCreateWithData(nullptr, (__bridge CFDataRef)certificate);
                const bool real = evaluate(trust, ca, CFSTR("127.0.0.1"));
                const bool wrong_name = deny && !real && alternate_identity(trust, ca);
                if (ca) CFRelease(ca);
                if (trust) CFRelease(trust);
                {
                    std::lock_guard<std::mutex> guard(s->mutex);
                    s->trust_ok = real;
                    s->wrong_san = wrong_name;
                }
                // The alternate evaluation supplies evidence only; it can
                // never admit a certificate rejected for the actual endpoint.
                complete(real);
                dispatch_semaphore_signal(s->changed);
            }, callbacks);
        }, NW_PARAMETERS_DEFAULT_CONFIGURATION);
        const auto stack = nw_parameters_copy_default_protocol_stack(params);
        nw_protocol_stack_prepend_application_protocol(stack, nw_ws_create_options(nw_ws_version_13));
        char digits[6]{};
        std::snprintf(digits, sizeof(digits), "%u", static_cast<unsigned>(listener));
        const auto host = nw_endpoint_create_host(loopback, digits);
        connection = nw_connection_create(host, params);
        if (!connection) {
            std::lock_guard<std::mutex> guard(s->mutex);
            s->bad = true;
            dispatch_semaphore_signal(s->changed);
            return;
        }
        const auto conn = connection;
        nw_connection_set_queue(conn, callbacks);
        nw_connection_set_state_changed_handler(conn, ^(nw_connection_state_t status, nw_error_t) {
            bool read = false;
            {
                std::lock_guard<std::mutex> guard(s->mutex);
                if (status == nw_connection_state_ready) {
                    if (s->open || s->closed || !s->trust_ok || deny) s->bad = true;
                    else {
                        s->open = s->ready_event = true;
                        read = true;
                    }
                } else if (status == nw_connection_state_failed || status == nw_connection_state_cancelled ||
                           (status == nw_connection_state_waiting && deny && s->wrong_san)) {
                    if (!s->closed) {
                        s->closed = s->disconnect_event = true;
                    }
                }
            }
            if (read) {
                nw_connection_receive_message(conn, ^(dispatch_data_t content, nw_content_context_t context,
                                                       bool complete, nw_error_t error) {
                    const void* bytes = nullptr;
                    size_t length = 0;
                    const auto map = content ? dispatch_data_create_map(content, &bytes, &length) : nullptr;
                    const auto ws = context ?
                        nw_content_context_copy_protocol_metadata(context, nw_protocol_copy_ws_definition()) : nullptr;
                    {
                        std::lock_guard<std::mutex> guard(s->mutex);
                        if (error || !complete || !map || !bytes || !ws || length != reply.size() ||
                            nw_ws_metadata_get_opcode(ws) != nw_ws_opcode_binary || s->data_event || !s->sent) {
                            s->bad = true;
                        } else {
                            std::memcpy(s->incoming.data(), bytes, length);
                            s->data_event = true;
                        }
                    }
                    dispatch_semaphore_signal(s->changed);
                });
            }
            dispatch_semaphore_signal(s->changed);
        });
        nw_connection_start(conn);
    }
    int poll(ml_wire_event_v1* event) {
        std::lock_guard<std::mutex> guard(state->mutex);
        if (state->bad) return -1;
        if (state->ready_event) {
            state->ready_event = false;
            *event = {ML_WIRE_CONNECTED, generation, nullptr, 0};
        } else if (state->data_event) {
            state->data_event = false;
            borrowed = state->incoming;
            *event = {ML_WIRE_RECEIVED, generation, borrowed.data(), borrowed.size()};
        } else if (state->disconnect_event) {
            state->disconnect_event = false;
            *event = {ML_WIRE_DISCONNECTED, generation, nullptr, 0};
        } else return 0;
        return 1;
    }
    int write(const uint8_t* bytes, uint64_t size) {
        {
            std::lock_guard<std::mutex> guard(state->mutex);
            if (!state->open || state->closed || state->bad || !bytes || size != request.size())
                return ML_WRITE_FAILED;
            if (state->sent) return ML_WRITE_BLOCKED;
            state->sent = true;
        }
        const auto copy = dispatch_data_create(bytes, size, callbacks, DISPATCH_DATA_DESTRUCTOR_DEFAULT);
        const auto tag = nw_ws_create_metadata(nw_ws_opcode_binary);
        const auto context = nw_content_context_create("madlink-binary");
        nw_content_context_set_metadata_for_protocol(context, tag);
        const auto s = state;
        nw_connection_send(connection, copy, context, true, ^(nw_error_t error) {
            if (error) {
                std::lock_guard<std::mutex> guard(s->mutex);
                s->bad = true;
            }
            dispatch_semaphore_signal(s->changed);
        });
        return ML_WRITE_ACCEPTED;
    }
};

bool exercise(uint16_t port, bool wrong) {
    Adapter adapter(port, wrong);
    ml_client* raw = nullptr;
    const ml_config_v1 config{sizeof(config), ML_ABI_V1, 1, 16, 16, 9000, 1, 1, 0};
    const ml_host_v1 host{
        sizeof(host), ML_ABI_V1, &adapter,
        [](void* p, const char* e, uint64_t g) { static_cast<Adapter*>(p)->connect(e, g); },
        [](void* p) { static_cast<Adapter*>(p)->close(); },
        [](void* p, ml_wire_event_v1* e) -> int32_t { return static_cast<Adapter*>(p)->poll(e); },
        [](void* p, const uint8_t* b, uint64_t n) -> int32_t { return static_cast<Adapter*>(p)->write(b, n); },
        [](void*) -> uint64_t { return milliseconds(); }, [](void*) -> uint64_t { return 0; }
    };
    if (ml_create_tracked_v1(&config, &host, 1, &raw) != ML_OK || !raw) return false;
    std::unique_ptr<ml_client, decltype(&ml_destroy_v1)> client(raw, ml_destroy_v1);
    if (ml_connect_v1(raw, "owned-fixture") != ML_OK) return false;
    const auto deadline = Clock::now() + std::chrono::seconds(8);
    bool connected = false, received = false, failed = false, completed = false, terminal = false;
    uint64_t operation = 0;
    while (Clock::now() < deadline) {
        if (ml_tick_v1(raw) != ML_OK) return false;
        bool advanced = false;
        for (;;) {
            ml_event_v1 event{};
            event.struct_size = sizeof(event);
            event.abi_version = ML_ABI_V1;
            const auto status = ml_next_event_v1(raw, &event);
            if (status == ML_EMPTY) break;
            if (status != ML_OK) return false;
            if (event.kind == ML_EVENT_STATE && event.state == ML_CONNECTED) {
                if (wrong || connected) return false;
                connected = true;
                if (ml_send_tracked_v1(raw, request.data(), request.size(), milliseconds() + 6000, &operation)
                        != ML_OK || !operation) return false;
                advanced = true;
            } else if (event.kind == ML_EVENT_RECEIVED) {
                if (wrong || !connected || received || event.data_size != reply.size() || !event.data ||
                    std::memcmp(event.data, reply.data(), reply.size()) != 0) return false;
                received = true;
            } else if (event.kind == ML_EVENT_STATE && event.state == ML_CLOSED) {
                if (!wrong || !failed || terminal) return false;
                terminal = true;
            } else if (event.kind == ML_EVENT_FAILED) {
                if (!wrong || failed || event.error != ML_TRANSPORT_ERROR || event.operation) return false;
                failed = true;
            }
        }
        ml_completion_v1 result{};
        result.struct_size = sizeof(result);
        result.abi_version = ML_ABI_V1;
        const auto status = ml_next_completion_v1(raw, &result);
        if (status == ML_OK) {
            if (wrong || completed || result.operation != operation ||
                result.outcome != ML_COMPLETION_LOCAL_ACCEPTED) return false;
            completed = true;
        } else if (status != ML_EMPTY) return false;
        if ((wrong && failed && terminal) || (!wrong && connected && received && completed)) {
            {
                std::lock_guard<std::mutex> guard(adapter.state->mutex);
                if (adapter.state->bad || (wrong ? (!adapter.state->wrong_san || adapter.state->open)
                                                 : (!adapter.state->trust_ok || !adapter.state->sent)))
                    return false;
            }
            if (!wrong) {
                // The tracked result above was consumed. Prove there is
                // no second receivable completion before declaring success.
                ml_completion_v1 extra{};
                extra.struct_size = sizeof(extra);
                extra.abi_version = ML_ABI_V1;
                if (ml_next_completion_v1(raw, &extra) != ML_EMPTY) return false;
            }
            return ml_close_v1(raw) == ML_OK;
        }
        if (!advanced) {
            const auto remaining = std::chrono::duration_cast<std::chrono::nanoseconds>(
                deadline - Clock::now()).count();
            if (remaining > 0) dispatch_semaphore_wait(adapter.state->changed, dispatch_time(DISPATCH_TIME_NOW, remaining));
        }
    }
    return false;
}
}  // namespace

@interface MadLinkWssTests : XCTestCase
@end
@implementation MadLinkWssTests
- (void)testInstalledAuthenticatedLoopbackWSS {
    NSBundle* app = [NSBundle mainBundle];
    NSBundle* tests = [NSBundle bundleForClass:[MadLinkWssTests class]];
    BOOL expected = [app.bundleIdentifier isEqualToString:@"org.madlink.preview.Demo"] &&
        [app.executablePath.lastPathComponent isEqualToString:@"Demo"] &&
        [tests.bundleIdentifier isEqualToString:@"org.madlink.preview.SmokeTests"] &&
        [tests.executablePath.lastPathComponent isEqualToString:@"SmokeTests"] &&
        [tests.bundlePath.lastPathComponent isEqualToString:@"SmokeTests.xctest"];
    XCTAssertTrue(expected, @"wss-product-identity");
    if (!expected) return;
    XCTAssertTrue(exercise(kValidPort, false), @"wss-positive");
    XCTAssertTrue(exercise(kWrongPort, true), @"wss-wrong-san");
}
@end
