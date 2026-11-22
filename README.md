# MadLink

MadLink is an experimental, MIT-licensed C++17 connection core with a C11
interface. It provides per-client lifecycle and retry state, bounded send queues,
and optional tracked send results. Applications provide the transport, monotonic
clock, and randomness. The installed core needs no networking or telemetry library.

This is the independently implemented standalone core, not the older IMLink
extraction described in the initial repository README. This source integration
does not ship QUIC, TCP/TLS, push, production transport, or platform bindings.

## Build and consume on Linux

Use existing C++17/C11 compilers, `ar`, Make, pkg-config and Python. These scripts
do not fetch or install dependencies.

```sh
sh run-tests.sh
sh run-c-abi-tests.sh
sh packaging/install-core.sh "$PWD/build/local-sdk" "$PWD/build/local-objects"
python3 -B packaging/test-relocation.py
python3 -B packaging/test-tracked-completions.py
python3 -B packaging/test-tracked-completions.py --ubsan
```

The static SDK installs `madlink_c.h`, `libmadlink.a`, pkg-config metadata, and
notices. Compile the application's C sources as C11 and link using the matching
C++ driver. The installation layout is relocatable; the archive itself is
specific to the build target and toolchain. See [installed SDK guide](packaging/INSTALLED.md).

## Lifecycle and tracked results

Each handle and its transport belong to one owner thread. Host callbacks are
synchronous, non-reentrant, nonblocking, and must not throw. Keep callback
context alive through destruction. Drive `ml_tick_v1` yourself; there is no
worker thread. Event payloads are borrowed and must be copied before the next
event poll or destruction.

Legacy diagnostic events may be dropped. To get an in-process terminal result
for every admitted tracked send, use `ml_create_tracked_v1` with 1–1024 slots,
`ml_send_tracked_v1`, and `ml_next_completion_v1`. Each admitted send reserves
a slot until the result is consumed; a full ledger rejects new tracked sends.
`LOCAL_ACCEPTED` means the transport accepted the bytes locally, not that the
peer received or acknowledged them. An unknown outcome is not permission to
retry; reconnect does not automatically replay queued operations.

On normal shutdown, close, drain tracked results, then destroy. On poison,
drain then destroy; legacy operations remain unavailable. Destruction discards
unread results. No process-restart recovery, delivery guarantee, production
transport, thread safety, or hard process-memory bound is claimed.

## Verification scope

See [validation](VALIDATION.md) and the [frozen-object ABI check](packaging/abi-upgrade/README.md).
The latter relinks unchanged old C objects against both exact installed archives
on a Linux x86-64 GCC toolchain. It does not replace code inside an already linked
static executable or establish cross-platform ABI compatibility. The historical
public revisions required by that reproduction are listed in its guide.

Android, iOS, OpenHarmony and production interoperability are not qualified by
this branch. No workflows, SDK binaries, certificates or raw test logs are
published in this source integration. See [LICENSE](LICENSE) and
[third-party notices](THIRD_PARTY_NOTICES.md).
