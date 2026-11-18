# MadLink (experimental)

Business-agnostic reliable communication SDK extracted from IMLink, preserving
QUIC/TCP-TLS, request/cancellation, retry budgets, DNS, push and platform sources.
Not an IM SDK. No MadDB/MadCrypto/MadInfer/MadMedia/MadObs runtime dependency.
Current tested build: Linux x86_64, TCP/TLS and QUIC static build; platform bindings retained but not
validated in this environment. This batch does not claim production readiness.

## Reproducible standalone build

CMake >=3.20, C++17 compiler, make, Python for include checks.
Acquire pinned dependencies explicitly, not during configure:

```sh
bash scripts/fetch_deps.sh /tmp/madlink-deps
BSSL=/tmp/madlink-deps/boringssl-533902fb2e8fd0586db7d58879d697721726605a
cmake -S "$BSSL" -B /tmp/madlink-deps/boringssl-build -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/madlink-deps/boringssl-build --target ssl crypto -j4
cmake -S . -B build -DMADLINK_ENABLE_QUIC=OFF \
  -DIMLINK_BSSL_DIR="$BSSL" -DIMLINK_BSSL_BUILD=/tmp/madlink-deps/boringssl-build \
  -DMADLINK_GTEST_SOURCE=/tmp/madlink-deps/googletest-1.17.0
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

`-DBUILD_TESTING=OFF` needs no GoogleTest. QUIC is explicit, never detected from
an incidental library file: `-DMADLINK_ENABLE_QUIC=ON` requires pinned XQUIC source
and static build (`IMLINK_XQUIC_DIR`, `IMLINK_XQUIC_BUILD`) and fails if missing.
To build the pinned QUIC dependency (the SDK only needs its static target):

```sh
bash scripts/fetch_deps.sh /tmp/madlink-deps quic
XQUIC=/tmp/madlink-deps/xquic-278755ef64a4ed7ac89c0ac1fc30aacb1221b8d4
cmake -S "$XQUIC" -B /tmp/madlink-deps/xquic-build -DSSL_TYPE=boringssl \
  -DSSL_PATH="$BSSL" -DSSL_INC_PATH="$BSSL/include" \
  '-DSSL_LIB_PATH=/tmp/madlink-deps/boringssl-build/libssl.a;/tmp/madlink-deps/boringssl-build/libcrypto.a' \
  -DXQC_ENABLE_TESTING=0
cmake --build /tmp/madlink-deps/xquic-build --target xquic-static -j4
# Add MADLINK_ENABLE_QUIC=ON, IMLINK_XQUIC_DIR=$XQUIC and
# IMLINK_XQUIC_BUILD=/tmp/madlink-deps/xquic-build to the SDK configure command.
```

Real QUIC integration tests accept an external test server via
`MADLINK_QUIC_TEST_SERVER=/absolute/path/to/test_server`.
Use `MADLINK_REQUIRE_QUIC_INTEGRATION=ON` for release verification: configure fails
if that binary is absent. In development mode four server tests explicitly skip
when absent; skipped is NOT passed.

Third-party libraries remain outside this repository; no private source is fetched.

## Consumption

Use `add_subdirectory(MadLink)` and `target_link_libraries(app PRIVATE MadLink::MadLink)`.
Include `<madlink/madlink.h>`; `madlink` is currently a C++ namespace alias over the
preserved implementation. See `PUBLIC_API.md` for lifecycle and compatibility limits.
The two-app host sample constructs independent clients with distinct protocols.

Observability is opt-in: set `MADLINK_WITH_OBS=ON` and provide the public MadObs
API include directory via `MADOBS_INCLUDE_DIR`, then link `MadLink::ObsAdapter`.
It is header-only, no runtime link. Assign an SDK ID explicitly (global registry
not frozen). A custom `metrics_sink` or absent sink also works. Never export body,
tokens, free-form tags or paths through telemetry. Empty log sink is Noop.

Important behavior changes: readiness timeout is fail-closed; SPKI/mTLS unsupported
config returns null instead of being silently accepted. Legacy protocol/ALPN and
cache identifiers are preserved. Historical `imlink/README.md` is source context,
not this SDK's release status. See `TASK_RESULT.md` and `SUPPORT_MATRIX.md`.

## Publication gate

The owner authorized this experimental public source checkpoint after the scoped
review in `docs/PUBLICATION_REVIEW.md`. No first-party open-source license is
granted or invented. Publication is not a production release. Upstream notices
are in `LICENSES/`; outstanding release gates are in `TASK_RESULT.md`.
