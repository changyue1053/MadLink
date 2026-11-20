# Standalone Linux two-instance WSS runtime preview

Run explicitly from the checkout with:

```sh
python3 tests/wss/isolation.py
```

Requires an existing C++17 compiler, pkg-config, a WSS-enabled system libcurl
development package, OpenSSL CLI and Python 3 with TLS support. No downloads,
installs, new workflows or changes to the default Core package. The independent
C++ consumer compiles the unchanged Core and optional adapter translation units
and links system libcurl **without linker wrappers**. It is not a test of an
installed optional SDK, because the installed Core does not contain this adapter.

The test builds and generates an ephemeral self-signed localhost certificate/key
in a private temporary directory. Two separate TCP listeners bind only
127.0.0.1 on ephemeral ports. Each independently checks the real TLS/HTTP 101
exchange and exact masked WS binary frames with short synthetic data.
The client accepts only numeric ports and builds fixed localhost URLs. The
adapter still verifies the certificate and DNS hostname using that single
fixture CA. Timeouts cover build, subprocess, TLS, HTTP, frames, coordination,
and socket close; temporary files and sockets are disposed of on unwind.
There are no external endpoints or user credentials.

The consumer owns two separate Client/CurlTransport/clock/random sets, under
one curl global lifetime, interleaved on the same owner thread. Both exchange
distinct frames and validate their exact event sequences. A queues one message
and closes before ticking it; require its cancellation event and no bytes from
that message. On A's second TLS session the server reads the upgrade request
but withholds HTTP 101. B completes a full round-trip on its original
connection, and its post-receive confirmation unlocks A's upgrade. The client
also asserts A is still connecting when B completes that round-trip.
A's peer requires a silent window, authorizes one fresh send, checks the
exact fresh frame, then requires another silent window before sending a done
marker. B exchanges again after that proof, and both peers see client teardown.
The silent windows reject any bytes or premature close; they are bounded
observations, not a claim of all-time non-replay.

Local evidence: GCC 14.2.0, system libcurl 8.14.1 with OpenSSL 3.5.7,
OpenSSL CLI 3.5.7 and Python TLS OpenSSL 3.5.8. No third-party code or
credentials are copied into source. libcurl and OpenSSL retain their own
licenses; see the optional adapter README and THIRD_PARTY_NOTICES.md.

This is real Linux loopback TLS/WSS with synthetic peers. It does not establish
mobile or physical-device support, thread safety, graceful WS close handshake,
public endpoint interoperability, remote service delivery, kernel backpressure,
or release readiness. Core written events alone are local acceptance. The
fixture's server observations prove its own synchronous local frame exchanges.
