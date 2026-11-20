# MadLink public-source slice A

Newly written, dependency-free C++17 prototype for a reusable connection core.
This is not recovered IMLink/MadLink code and does not claim compatibility with
any existing server or previous SDK. No private source or recovery package was
used. The default Core contains no wire protocol, credential handling or TLS.
An explicitly optional localhost-tested WSS experiment is described below.

## Run

    sh run-tests.sh
    EXTRA_CXXFLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer -g' sh run-tests.sh

Only an existing C++17 compiler is required; nothing is downloaded or installed.

## Contract

- Per-instance state; injected, borrowed transport, monotonic clock and randomness.
  Dependencies must outlive the client. One transport instance belongs to one client.
- Owner-thread-only API, including polling and destruction. **Not thread-safe.**
  Platform wrappers must serialize operations. No worker thread or scheduled task.
- Allocation exceptions may propagate. `send` preserves queue accounting when
  insertion allocation fails, but the API as a whole does not promise recovery from
  out-of-memory failures (for example diagnostic-event allocation). Production C ABI
  work must define exception containment and allocation-failure semantics.
  An accepted write is removed before its diagnostic event is allocated: if that
  allocation throws, a later tick will not replay it, but its `written` event may be
  lost. An exception from tick must not be interpreted as permission to resend.
- Transport methods and optional observation sink must be nonblocking and must not
  reenter the client. Slow observers are not isolated in this prototype.
- `tick()` processes bounded incoming events and pending writes. Clock values must
  never decrease. Call regularly; there is no hidden event loop.
- Endpoint is an opaque nonempty string passed to the adapter, not a protocol choice.
- Send is allowed only while connected. Deadline is absolute monotonic milliseconds.
  Bytes are copied/moved into a count- and logical-payload-size-bounded queue.
  `written` means the transport accepted
  the bytes locally, not peer delivery or business acknowledgment. Adapters accepting
  data must take ownership/copy it before returning. Retry never replays messages.
- Explicit close cancels pending sends, invalidates old generation events and stops
  retries. Close is idempotent. Reopen is explicit. A finite retry budget applies to
  the entire connection lifecycle until another explicit `connect` call.
- Destructor closes the transport without invoking telemetry or application callbacks.
  There are no async client callbacks to fire after destruction; events are polled.
- Diagnostic events are bounded; overflow drops the oldest and increments
  `dropped_events()`. Therefore events are **not** a reliable operation ledger or an
  inbound-message delivery guarantee. A production adapter needs receive backpressure
  and a non-dropping completion strategy before this can be used as an IM SDK.
- All byte limits refer to `vector::size()`, NOT capacity, allocation or process memory.
  A moved vector can retain capacity much greater than its logical payload size.
  `queued_bytes()` reports logical payload bytes only. There is no hard memory bound
  in this prototype, including event buffers, caller arguments and adapter buffers.
  Production hard memory limits require owned bounded buffers/allocators and receive
  backpressure. Receive size is checked after adapter delivery; a real parser must
  bound allocation before constructing a message.
- Send deadlines are checked immediately before each adapter write invocation. This
  does not guarantee remote receipt by that deadline or prevent time advancing inside
  an adapter call. Adapters must implement any stronger completion deadline semantics.
- Retry uses capped exponential equal-jitter delay. Timeout and cancellation do not
  imply a remote endpoint has undone any action.
- Telemetry is optional via an injected metadata-only sink; null means no telemetry.
  No MadObs dependency, exporter, credential, payload logging or telemetry network.

## Verified scope and remaining work

Tests cover local lifecycle, deadlines, cancellation, send bounds, stale generations,
retry exhaustion, no replay, receive limits, diagnostics overflow, instance isolation,
optional telemetry and destruction. Optional network testing is limited to the local
TLS fixture described below; mobile builds and production interoperability are untested.

Android JNI, Swift, ArkTS,
concurrency, production executors, durable completion, fuzzing, production network adapters,
MadObs runtime integration and business protocol plugins remain **unimplemented**.

## Versioned C ABI minimal slice

`include/madlink_c.h` exposes opaque handles, fixed-width status/constants, versioned
structures and `_v1` symbol names. `src/madlink_c.cpp` adapts host-provided callbacks
without exposing C++ types or ownership. This is an ABI stability strategy and initial
prototype, NOT a promise of already validated compatibility with future releases,
different architectures, calling conventions or mobile toolchains.

Run `sh run-c-abi-tests.sh`. It builds one `build/sdk/lib/libmadlink.a` and ships only
`madlink_c.h` in the SDK include directory. Two independent C11 translation units in
`consumers/app_a` and `consumers/app_b` link against that same archive, without including
the C++ header or compiling SDK sources in the consumer. A covers binary send lifecycle;
B covers receive, cancellation, version rejection and two-handle isolation. These are
native command-line consumers, not Android/iOS/HarmonyOS applications.

Host callback structures are copied; their user context and functions must remain valid
through destroy. Endpoint/write bytes are borrowed for the callback only. Poll event
data must remain valid until the next host callback; the bridge copies it. Returned
event bytes remain valid until the next `ml_next_event_v1` or destroy, even if empty.
Only the owner thread may call APIs/destroy. Callbacks may not reenter APIs, throw or
block. No background executor or application notification callbacks exist. Invalid or
freed pointer arguments cannot be validated: the caller must provide live handles,
readable buffers of the declared size, and structures with at least the version header.

Bridge exceptions become status codes; OOM/internal failure poisons the handle.
Legacy access then supports only destruction; the opt-in completion drain below
remains available. A separate allocation-injection executable checks
create OOM and send OOM containment/poisoning. This is containment, not broad recovery:
tick failure may follow side effects, and cannot justify resending. Host callbacks that
throw violate the contract and are not covered by this guarantee.

Diagnostics remain lossy as described above. The C slice does not solve durable
completion delivery, hard memory caps, transport security or real network interoperability.
First-party source is MIT licensed; see LICENSE and THIRD_PARTY_NOTICES.md.

## Optional tracked send results (installed C SDK)

Use `ml_create_tracked_v1` with 1–1024 result slots, then
`ml_send_tracked_v1`. Every successful tracked admission returns a per-handle ID
and reserves one slot until `ml_next_completion_v1` consumes its terminal result.
A full ledger returns `ML_QUEUE_FULL` without copying payload or assigning
an ID; draining one result frees one credit. If the handle exhausts unique IDs,
otherwise admissible sends also return `ML_QUEUE_FULL`, but draining cannot
restore ID capacity. Pending sends still obey the normal queue, size and
deadline limits. Legacy create/send and the lossy `ml_next_event_v1` stream are
unchanged. A legacy send also stays untracked on an opt-in handle.

A terminal result is local acceptance, cancellation (including explicit close),
deadline, or a conservative unknown after transport or handle failure. Local
acceptance is **not peer delivery**. An unknown result must not trigger blind
replay. Reconnect never replays a queued operation. Consume and copy result
metadata independent of the diagnostics; it contains no payload or user
context. Acknowledging a result only frees its slot, not network or business
state.

Use the same owner thread and never reenter from host callbacks. If a tracked
handle is poisoned, already-established results remain available, and other
accepted tracked operations settle as handle-fault unknown. Drain before
destroy; destroying the handle discards remaining results. There is no process
restart recovery, business acknowledgment, delivery promise, executor, platform
qualification or hard process-memory cap in this feature.

Run `python3 packaging/test-tracked-completions.py` and again with `--ubsan`.
The portable host gate removes a disposable producer, moves its installed
archive and public header, then independently builds the unchanged legacy C
consumer, adversarial tracked C consumer, and allocation-fault consumer against
that same archive. No tools are fetched and no transport traffic is sent.

## Optional local WSS experiment

An opt-in libcurl adapter and localhost TLS tests are now in `optional/curl` and
`tests/wss`. See `optional/curl/README.md` for accepted-buffer semantics, partial-frame
handling, licensing, verified tests and substantial remaining limitations. Run
`sh run-wss-tests.sh` explicitly; the default dependency-free builds are unchanged.

## Relocatable installed core C package

`sh packaging/install-core.sh ABS_PREFIX ABS_BUILD_DIR` assembles a local static core
SDK with only the C header, archive, relative-prefix pkg-config metadata and installed
contract documentation. It requires an existing GCC/Clang-style C++17 toolchain and ar;
it does not install any tools. Consumers compile C11 and link with the matching C++
driver. No curl/WSS or MadObs component is installed with this core package.

Run `python3 packaging/test-relocation.py` for stronger isolation evidence: a disposable
copy of this new producer builds/installs the package, the prefix moves to a path with
spaces, and that generated producer source/build tree is deleted before either consumer
is compiled. Each standalone consumer uses only its own main.c/Makefile and relocated
package metadata. Dependency files, package contents, file hashes, Linux dynamic
dependencies and command logs are recorded in ignored build evidence. Missing SDK
prefixes must fail instead of silently falling back to a globally installed package.

This is relocatable installation verified on native Linux, not universal binary
portability or validation on Android/iOS/HarmonyOS. Other compiler, OS and ABI targets
remain untested. First-party licensing does not change third-party dependency terms.

The host compiler gate is `python3 packaging/test-compiler-matrix.py`. It attempts
GCC→GCC, GCC→Clang, Clang→GCC and Clang→Clang using discovered existing tools. Each
executed direction independently repeats producer deletion, prefix relocation and
both standalone C consumer checks. It never installs tools. Exit 1 means a failing
executed case; exit 2 means incomplete coverage due to missing compilers, not a pass.
The current environment has GCC/G++ 14.2.0 but no discovered Clang pair, so only
GCC→GCC is verified. WSS and any future MadObs adapter are separate from this gate.

## Optional MadObs API-only stage

`optional/madobs` adds a bounded metadata queue and explicit drain through the exact
public MadObs 79fd8ced observer/privacy headers. It is not included in the default
installed core SDK. See its README for ownership, threading, rejection and privacy
contracts. `sh run-madobs-tests.sh MADOBS_API_PREFIX` verifies pinned header hashes
and runs Core and installed-C-consumer checks. This stage uses real public header
implementations with a test observer; official MadObs package installation and runtime
admission/WAL/exporter integration have not been tested or implemented here.

The previously researched public standards/platform references inform future adapters,
not implementation claims:
- https://www.rfc-editor.org/info/rfc6455/
- https://www.rfc-editor.org/info/rfc9846/
- https://opentelemetry.io/docs/specs/otel/library-guidelines/
- https://developer.android.com/ndk/guides/stable_apis
- https://www.swift.org/documentation/cxx-interop/
- https://developer.huawei.com/consumer/cn/doc/HarmonyOS-Guides/ndk-development-overview/

First-party source is licensed under MIT (LICENSE). No third-party source is vendored.
See THIRD_PARTY_NOTICES.md before packaging optional dependencies.
