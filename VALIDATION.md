# Validation scope

This is an experimental native Linux SDK snapshot, not a production or mobile support
claim. Tests use synthetic data and, where networking is involved, localhost only.
Raw logs, machine-specific evidence paths, generated keys and build products are not
published. Verification scripts generate local evidence under ignored build output.

## Verified with existing tools

- GCC/G++ 14.2.0 strict C11/C++17 builds.
- Eleven deterministic core lifecycle groups and allocation-failure regressions.
- C ABI error containment, poisoned handles, stale generation filtering and two C consumers.
- Relocated installed core package after deleting the disposable producer source/build;
  both standalone consumers, repeated builds, missing-prefix rejection, dependency/path
  scans and package manifests. The installed first-party license is included.
- Eight optional WSS localhost scenarios using libcurl 8.14.1/OpenSSL 3.5.7: binary
  roundtrip, Core integration, fragmented receive with PING/PONG, oversize rejection,
  certificate/hostname rejection, bounded blocked flush, and clean TLS reconnect.
  Partial-frame progress is real; subsequent AGAIN is injected, not kernel saturation.
- Optional MadObs queue/drain tests using separately staged exact public API headers:
  finite numeric schema, zero timestamp, overflow, budget, rejection/noop, callback
  error/reentry, no destructor flush, and an installed core C SDK consumer.
- Standalone UndefinedBehaviorSanitizer checks for the above supported local suites.

## Explicitly incomplete or unavailable

- Host compiler matrix: GCC→GCC passes; Clang is unavailable, so the other three
  producer/consumer combinations are NOT RUN and the matrix exits 2 / INCOMPLETE.
- AddressSanitizer/leak validation is unverified because LeakSanitizer reported an
  environment ptrace limitation. UBSan success is not an ASan/leak pass.
- CMake and an installed MadObs runtime are unavailable. MadObs checks are API-only
  with real upstream header helpers and a synthetic observer, not runtime admission,
  WAL, exporter delivery, restart persistence or official CMake package validation.
- No Android/iOS/HarmonyOS, cross-architecture, remote service, production transport,
  hard memory-cap or reliable completion-delivery claim. WSS does not imply MadObs
  runtime integration. Optional dependencies retain their own licensing requirements.

## Snapshot hygiene

Only tracked independently written source was exported into a new one-commit snapshot.
No historical/private implementation, staged upstream file, output, raw log, certificate
or key is included. The local source history was inspected before export; credential
pattern scans of its 11 commits / 66 unique blobs found no matches. The publication
tree receives a separate scan. Pattern scans reduce risk but are not a proof that no
possible sensitive information exists. Third-party provenance is separately documented
in THIRD_PARTY_NOTICES.md; no external material is relicensed as MIT.
