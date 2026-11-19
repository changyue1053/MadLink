# Installed public C ABI session lifecycle acceptance

Adds runtime evidence beyond the two existing smoke consumers. `app_a` checks one
send lifecycle; `app_b` checks receive/cancel and destruction isolation for two
handles. `tests/test_c_generation.c` checks stale malformed wire events across an
explicit reconnect, but is not the repeated relocated-consumer scenario below.

This independent consumer uses only `madlink_c.h` and an installed core archive.
`packaging/test-relocation.py` builds it **after removing the disposable producer
source/build tree**, using the moved prefix with spaces, and executes it twice.
The existing four-direction compiler matrix automatically includes it. Existing
consumers, compiler availability rules and missing-prefix negatives are retained.
No workflow, core implementation, public ABI, license or transport code changes.

Each of 32 bounded, deterministic cycles keeps two app-owned handles alive:

- Submit different owner-tagged binary payloads and check exact accepted writes
  and written-operation events without consuming the other instance's queue.
- Deliver owner-specific received bytes, ticking B then A, and check exact content
  plus empty opposite event queues.
- Block A's pending send, disconnect it, require that operation's transport failure
  and exactly one connection failure/backoff event. B remains unaffected.
- Advance injected clock to just before, then exactly to the retry boundary;
  reject late received/disconnected events from the old generation and require
  new connecting/connected transitions.
- Check that the failed operation is not replayed, cannot be cancelled again,
  and a fresh send succeeds with a new per-handle ID.
- Explicitly close/reconnect A to reset its retry budget for the next cycle.

Finally close A with a blocked pending operation, require exactly one cancellation,
destroy A, then prove B can still send before its own clean close/destroy.
Per-handle operation IDs are allowed to collide across handles; they are not a
global application ledger. Every expected event is checked in order, followed by
an explicit empty-queue check. Building with NDEBUG fails rather than passing a
consumer whose assertions were removed.

This is **actual Linux host execution of installed MadLink**, with synthetic
app-owned transports, clocks and randomness. It does not use sockets, external
traffic, sleeps, threads, Obs or any additional repository. It does not prove WSS,
remote acknowledgment, crash persistence, mobile installation, device runtime,
thread safety or production readiness. Transport acceptance is not peer delivery.

Local run:

```
python3 packaging/test-relocation.py
EXTRA_CXXFLAGS='-fsanitize=undefined -fno-sanitize-recover=all' python3 packaging/test-relocation.py
```

Evidence JSON and local tool output remain in ignored build directories. No
artifact is uploaded. A four-way matrix requires both GCC and Clang; missing
Clang must remain NOT_RUN/INCOMPLETE, not an inferred pass.
