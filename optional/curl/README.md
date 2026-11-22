# Optional WSS prototype

Opt in with `sh run-wss-tests.sh`. The existing default Core/C ABI build scripts do
not compile this target, link libcurl, or access any network. The optional target
uses the installed libcurl via pkg-config. No package download or installation.

## Semantics and limits

- Owner-thread-only, explicit polling, libcurl multi handshake (not easy_perform).
  The host must own curl_global_init/cleanup around all adapters. The adapter does
  not clean up libcurl process-global state owned by other components.
- Only WSS binary messages. No redirects, proxy inheritance, username/password URLs,
  text protocol, compression negotiation, business ACKs or application authentication.
  CA-file override selects a trust store; it does NOT turn off certificate or hostname
  verification. Empty CA-file uses system trust. No insecure verification switches.
- `accepted` means a complete message was copied to one adapter-owned outbound slot.
  Caller buffers may then be changed/freed. It does NOT mean network flush, peer receipt
  or business acknowledgment. `blocked` never sends any part of the newly offered data.
- Core's cancellation/deadline applies until local adapter acceptance. Once accepted,
  this adapter has no operation ID or per-message deadline. It may transmit later;
  closing discards buffered remainder. A partial remote write cannot be undone, and
  failures never authorize automatic replay. No strong delivery deadline is claimed.
- Each poll writes at most 4096 payload bytes using explicit CURLWS_OFFSET. The first
  call supplies the full frame size and later successful-progress calls use zero.
  CURLE_AGAIN retains the same buffer/length for retry; unexpected nonzero AGAIN progress
  fails closed. A successful empty frame is handled by a separate ordinary-frame call.
- Receive is deferred until an outbound frame is fully emitted: automatic PONG must
  not be inserted in the middle of that frame's payload. This sacrifices receive
  latency/full-duplex fairness during a stalled send. An independent absolute flush
  timeout (default 5000ms, must be nonzero) starts at local acceptance and is checked
  at each poll. It is not reset by partial progress; expiry closes the transport and
  discards the remainder without replay. It bounds starvation only when the caller
  keeps polling and is NOT a peer-delivery guarantee or a rollback of sent bytes.
- Receives use a fixed 4096-byte scratch buffer and at most 16 iterations per poll.
  Chunk/frame/fragment reassembly checks cumulative logical size before vector insert.
  Ping/Pong may appear between fragmented message frames. libcurl sends automatic PONG.
- Limits are payload sizes, not hard allocator/RSS caps. libcurl/TLS internal buffers
  are outside this accounting. Allocation failures during receive may propagate to
  C++ callers; the existing C bridge can contain exceptions when used with a host shim.
  No turnkey C ABI factory for this optional C++ adapter exists yet.
- Peer CLOSE causes connection teardown. Graceful close-response handshake, detailed
  error classification, readiness-based scheduling (instead of tick polling), proxy,
  mobile builds, certificate rotation, production reconnection semantics, and
  malformed protocol fuzzing remain unfinished. Do not market this as a production WS client.

## Verified localhost fixture

`tests/wss/loopback.py` uses Python's existing standard library and the installed
OpenSSL CLI. It generates a one-day self-signed localhost-only test certificate under
ignored build output, binds only 127.0.0.1, and launches the test client. No public
endpoint or user data is used. The fixture is not a production server.

Verified: 32KiB binary echo; one outbound frame emitted over multiple real libcurl
calls; copying/one-slot backpressure; fragmented inbound binary with interleaved PING
and verified PONG; inbound frame delivered in 1000-byte server writes; Core integration;
oversize rejection while server stays open until the client closes; wrong-host and
untrusted certificate rejection before an HTTP request. Internal partial-progress and
AGAIN state accounting are deterministic tests. Test-only linker wrapping also forces
CURLE_AGAIN while a real TLS peer sends inbound data or CLOSE, verifies 100ms flush
timeout (under 1500ms test bound), client-initiated teardown, and no subsequent replay.
Actual kernel-buffer saturation/short writes are **not forced/claimed verified**.
An additional two-session localhost regression now sends a real 4096-byte prefix of
a declared 32768-byte frame through libcurl/TLS, then forces continuous CURLE_AGAIN
for the remainder. It checks stable retry arguments and bounded timeout. The server
independently verifies that prefix, client-initiated teardown, silence after reconnect,
and only a newly requested `fresh` message on the new session. A real receive wrapper
observes the old incomplete `STALE` fragment before teardown; no old receive bytes are
joined to the fresh message. Core automatically reconnects once using the same adapter.
Thus real partial-frame progress plus **injected** AGAIN and real localhost TLS
reconnection are covered. Spontaneous OS-level partial writes/AGAIN, remote-network
faults and production reconnect semantics remain unverified.
The [unwrapped two-client fixture](../../tests/wss/ISOLATION.md) separately
checks real loopback WSS session isolation with no injected failures. Empty-frame
state accounting is tested, but empty-frame network interoperability is not.

During development, forced chunking exposed automatic PONG interleaving with unfinished
outbound data; deferring receive until frame completion fixed the real-loopback failure.
The certificate-negative fixture was corrected to allow server-side TLS completion
followed by client hostname rejection before HTTP, rather than requiring TLS handshake
failure on both ends. Certificate validation was never disabled.

## Dependency provenance / licensing (not distribution approval)

Observed local environment: libcurl 8.14.1, OpenSSL 3.5.7. libcurl's upstream license is
the `curl` license, NOT MIT; OpenSSL 3.x uses Apache-2.0. Preserve applicable copyright,
license and notice requirements. System libcurl also links other libraries, including
GnuTLS through its dependency graph. This is not a complete SBOM or license clearance.
No third-party implementation source is vendored. First-party adapter code is MIT;
third-party libraries retain their original terms. See ../../THIRD_PARTY_NOTICES.md.

Public implementation references:
- https://curl.se/libcurl/c/CURLOPT_CONNECT_ONLY.html
- https://curl.se/libcurl/c/curl_ws_send.html
- https://curl.se/libcurl/c/curl_ws_recv.html
- https://curl.se/docs/copyright.html
- https://openssl-library.org/source/license/index.html
