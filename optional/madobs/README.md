# Optional MadObs API-only queue adapter (stage 1)

Public dependency verified through GitHub connector on 2026-11-19:
https://github.com/changyue1053/MadObs/tree/79fd8ced44a18bca574598ff683cd706ded16a60
Repository visibility was `public`; the full commit was independently resolved.
Only public `PUBLIC_API.md`, CMake layout and two API headers were consulted, not
legacy runtime/private implementation sources. Exact public header blob IDs:

- observer.h: 2fd8c8cc81b2e38569c2b2ce3cd5fec03ffcf001
- privacy.h: 178de015b9854fe8aa84e9cf470f3de599c2a356

The headers are not vendored or added to MadLink's default installed package.
`sh run-madobs-tests.sh MADOBS_API_PREFIX` requires a prepared prefix holding these
exact headers and verifies their blob identities before compiling. It does not fetch,
install tools, link the MadObs runtime or publish anything. Here the public headers
were staged locally from connector-returned bytes and verified, not installed using
upstream CMake: CMake is unavailable. The test honestly labels this API-only staging.

## Contract

- Core's optional StateSink only enqueues finite state integers into 32 inline slots.
  No allocation, clock, IO or host callback occurs on this path. Full queue drops the
  newest observation and increments a saturating counter; invalid state is rejected.
- Explicit `drain(budget)` removes each event before invoking the public privacy helper.
  Callback rejection/error/noop is counted and never retried. `callback_invoked` means
  exactly that: upstream MADOBS_EMITTED is NOT admission, persistence or export success.
  A raw observer callback has no admission-return channel; runtime rejection cannot
  be inferred from this adapter's counters. Runtime integration is a later milestone.
- Owner-thread-only queue and drain; no worker/thread handoff. The descriptor is copied
  but observer context remains borrowed and must outlive every drain. StateSink borrows
  the queue; both must outlive Core. Destruction never flushes or invokes callbacks.
  Drain and enqueue reentry into this adapter are rejected/counted; this does not make
  arbitrary callbacks safe to reenter Core, destroy objects, race threads or longjmp.
- Core never automatically drains. Drain can still be delayed by a slow/misbehaving
  callback; no wall-time nonblocking guarantee is claimed for it. Host callbacks must
  obey MadObs's bounded/nonblocking lifetime contract. C++ callback exceptions are
  converted by the public helper and tested defensively; throwing remains a contract
  violation, not a recommended integration pattern.
- Provisional schema: sdk_id 0x4d4c, sdk_version 1, event_id 1, severity 1, one key 1
  with values 0..4 matching idle/connecting/connected/backoff/closed. No globally
  registered schema claim. Host must resolve schema ownership before publication.
- No timestamp is sampled: monotonic_ns=0; the public finite-domain privacy helper
  also strips exact timing. No payload, endpoint, token, app/user ID, error text or
  correlation field is collected. Queue order/event counts still reveal activity;
  this is minimization, not anonymization, consent or private-runtime enforcement.

## Actual tests and non-goals

Source-level Core fixture compares network state/write behavior with no sink versus
queued sink; callbacks remain untouched until explicit drain. Bounded overflow,
invalid states, noop, invalid observer ABI, callback exceptions, reentry, budget,
zero timestamp/inactive attributes and no destructor flush are exercised.

A separate consumer compiles with the installed MadLink C SDK, staged exact public
MadObs API headers and a separately staged optional queue header. It consumes Core C
state events and explicitly drains them; it does not include MadLink's C++ header.
This is real header implementation execution with a test observer, not a mock copy of
MadObs functions, but NOT a real installed MadObs runtime/WAL/exporter test. The C
event queue is lossy; polling it does not provide complete observation of every state.

Default installed core remains dependency-free and unchanged. WSS is unrelated to
MadObs integration. No mobile, cross-thread, runtime admission, exporter, official
CMake package-discovery or sanitizer leak validation is claimed. First-party adapter
code is MIT; public visibility alone is not redistribution clearance for MadObs.
No MadObs source/header/library is included in this repository snapshot.
