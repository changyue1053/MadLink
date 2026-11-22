# MadLink core C SDK 0.1.0 (experimental)

Layout: include/madlink_c.h, lib/libmadlink.a, lib/pkgconfig/madlink.pc.
The pkg-config file resolves its own prefix at query time; the whole directory may
be relocated. No producer source/build paths are required for consuming the package.
Compile consumer code as C11, then link with the matching C++17 toolchain driver
because the implementation requires that toolchain's C++ runtime. Example:

    PKG_CONFIG_PATH="$SDK_PREFIX/lib/pkgconfig" pkg-config --cflags --libs madlink

The static binary is specific to the build target/toolchain. Relocatable layout does
NOT mean one binary runs on every OS/CPU. Cross compilation and platform deployment
must be separately validated. This package has no libcurl, TLS, WSS, MadObs or other
network dependency; these features are not included or implied by installation.

The C header is the authoritative API contract: owner-thread-only, synchronous,
non-reentrant callbacks, explicit polling and borrowed buffer lifetimes. OOM can
poison a handle; accepted data does not imply peer delivery. Diagnostic events are
lossy. For bounded, opt-in in-process outcomes use `ml_create_tracked_v1`,
`ml_send_tracked_v1` and `ml_next_completion_v1` from the same header/archive.
An accepted tracked send holds one fixed metadata slot until the result is
consumed; legacy sends remain untracked. Local acceptance is not delivery,
and transport/handle unknown never authorizes blind replay. Drain tracked
results even after poison, then destroy the handle. No crash recovery,
durability, other-platform validation or network capability is implied.

First-party source is MIT licensed; installed LICENSE contains the full terms.
THIRD_PARTY_NOTICES.md describes optional dependencies, which are not included in this
core package. No third-party source is vendored.
