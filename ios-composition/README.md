# Optional iOS local composition validation

Opt-in test source only. Default core and existing OFF jobs are unchanged. A
separate CI job temporarily fetches public MadObs at
4af77ffa464a48307e5ff2d95f10b835919d205b without credentials, builds the real
simulator runtime with target SDK zlib and null crypto, then deletes its disposable
producer before linking the independent XCTest consumer. No upstream source or
binary is committed, uploaded or redistributed; public visibility is NOT a license
grant and this adds no license for MadObs. Distribution requires separate clearance.

Existing MadLink OFF archive/simulator gate is rerun unchanged before ON. ON links
MadObs only into the XCTest bundle; App remains standalone. The test drains three
synthetic C ABI state events through our bounded queue into the actual runtime,
checks admission/drain/drop counters and at least one policy-safe local sink batch.
All producers stop before synchronous runtime shutdown; host binding and sink
storage stay live. Post-stop invocation does not increase admission. No payload is
stored or printed; no endpoint exists. No runtime handles cross App/test modules.

One exact named XCTest must pass with no failures/skips. This is NOT remote
telemetry delivery, exact exported event ordering, WAL persistence, encryption,
physical-device or production proof. Only own temporary WAL/simulator is removed.
No tool install, license acceptance, account access, artifacts or release occurs.

Linux validates only source/static checks. Xcode/CMake iOS build, installed API
compatibility at the new upstream pin, exact result schema and actual combined
simulator lifecycle are unverified until the new hosted job passes. Archive/device
compatibility remains separate from this simulator-only MadObs composition.
