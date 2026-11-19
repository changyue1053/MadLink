# Optional iOS local composition validation

Opt-in test source only. Default core and mandatory standalone OFF runtime acceptance are unchanged. A
separate CI job temporarily fetches public MadObs at
4af77ffa464a48307e5ff2d95f10b835919d205b without credentials, builds the real
simulator runtime with target SDK zlib and null crypto, then deletes its disposable
producer before linking the independent XCTest consumer. No upstream source or
binary is committed, uploaded or redistributed; public visibility is NOT a license
grant and this adds no license for MadObs. Distribution requires separate clearance.

ON builds and inspects its own fresh relocated MadLink package with the shared
package-only function, deleting the disposable producer. It does not run or claim
an OFF runtime test. Both separate standalone OFF and optional ON workflow jobs
must pass at the same exact commit; neither substitutes for the other. ON links
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

Run 44467563564 failed in an ambiguously named version subprocess. Composition
now emits fixed START/PASS/FAIL stages for Git identity, SDK queries, source archive,
CMake configure/build/install, installed archive validation, lipo, simulator
architecture and separate ON test/result commands. Only fixed diagnostic categories
and numeric exit codes are shown. The installed lib/libmadobs_runtime.a must open
and have static archive magic before lipo. This name matches the pinned upstream
OUTPUT_NAME madobs_runtime and ARCHIVE DESTINATION lib, as well as its published
iOS validation script. No path or build behavior was rewritten without evidence.

Run 44469509797 passed OFF, runtime install and relocated archive ARM64 inspection,
then failed on a missing simulator guest uname helper. Architecture acceptance is
now enforced in the actual XCTest translation unit with TARGET_OS_SIMULATOR and
__arm64__ compile guards. The guest shell utility is no longer required. Explicit
ARM64 build settings, created UUID destination, archive architecture inspection
and exact named successful XCTest acceptance remain mandatory and unchanged.
This fix does not claim that the ON test has executed successfully yet.

Run 44473294042 reached ON build-for-testing after OFF and installed ARM64 runtime
checks. Compiler diagnostics now distinguish anchored unknown identifier, missing
header/module, ARC and signature errors, plus allowlisted failed command/target
pairs. Only four known public header names may be reported; unknown names/paths
remain suppressed. Public pinned runtime signatures match the calls on inspection;
no speculative ABI, include-path or lifecycle change is made by this diagnostic patch.

Run 44479952608 timed out in the previously nested OFF gate before ON. Package
construction/inspection is now shared, while the standalone default still always
runs its real simulator test. ON launches only its own simulator and retains the
exact named real runtime XCTest acceptance. Archive commands retain their bounded
per-command timeouts; there is no aggregate 600-second subprocess around a second
whole OFF test. No simulator result is inferred from package-only success.

Run 44482235489 reached ON build but returned only a generic build failure. The
composition no longer edits serialized project text. Test-only generator inputs
now declare MADOBS_PREFIX, quoted header search paths, and a static archive file
reference in PBXFrameworksBuildPhase instead of a path in OTHER_LDFLAGS. The App
and default producer/consumer generated projects remain unchanged. This removes
fragile configuration, not a claim that it explains the observed failure.

Before creating a simulator, stage fixture-compile invokes the pinned SDK's
clang++ on the actual unchanged Tests.mm with ARM64 simulator target, C++17, ARC,
modules, installed public headers and relocated MadLink framework. It performs
syntax-only compilation, not linking or runtime testing. Failure distinguishes
fixture/API/Apple-header issues from later Xcode build-graph/link/test stages.
Both mandatory exact-commit OFF and ON runtime gates remain required.

Local Linux checks passed explicit test-target/library-reference and spaced-path
argv tests, unchanged default project/scheme hashes, and a C++17 syntax-only check
of the fixture's native callbacks and API initialization against anonymously read
public headers at the pinned MadObs commit. Those temporary headers were not
committed. This host check does not compile XCTest, ARC or the Apple modules;
actual fixture-compile and Xcode/XCTest execution await hosted Apple validation.
