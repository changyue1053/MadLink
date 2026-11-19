# Static C ABI iOS preview

Based on public a91b5ba318feb70c5f32cf76526bc3827d257716. Two native Xcode
static framework archives (ARM64 iOS and ARM64 simulator) produce the XCFramework.
Xcode generates framework Info.plist/module metadata; no synthetic framework plist.
Only madlink_c.h is public. C++17/libc++ and exceptions remain implementation needs.
No Swift/Kotlin SDK API, MadObs, curl, backend, network entitlement or extra worker.

`python3 ios/verify.py` requires an existing Apple ARM64 host, Xcode26.2 and iOS26.2
simulator runtime. No installs/licenses/signing accounts are requested. The driver
creates and deletes only its own simulator. It never selects attached hardware.
If the macos-15 hosted machine is Intel or lacks pinned tools, the gate fails;
it must not silently substitute x86_64 and claim ARM64 execution.

Producer source/builds are disposable and deleted before the independent App is
built from a relocated XCFramework. Static framework is link-only, never embedded.
App and XCTest source cover synthetic connect/send/written/close only. At least
one passed XCTest and no failed/skipped tests is required. No real transport,
reconnect/receive, physical device, background lifecycle or production claim.

Linux local checks can only validate Python/project syntax and unchanged host
core. Archives, XCFramework structure, independent link, simulator test runner and
result parsing remain unverified until the Apple gate actually passes. Generated
archives, local logs and test results stay ignored and are never uploaded.

References: Apple Creating a static framework and Creating a multiplatform binary
framework bundle. Public MadDB 2b6e70be supplied architectural guidance only;
no runtime implementation was copied. Existing MIT and third-party notices remain.

App linkage explicitly names Foundation/UIKit/libc++; the hosted XCTest target
names Foundation/XCTest/libc++ and the platform Developer framework path. Clang
modules/autolink are explicitly enabled; static MadLink remains link-only. No
asset catalog, privacy-sensitive resource, entitlement or copied third-party
asset is introduced. MIT and THIRD_PARTY_NOTICES are copied beside the generated
XCFramework. This source preview does not claim an App Store privacy assessment
or binary-distribution license audit.

Hosted run 44459622113 completed archives/XCFramework and structural assertions,
then failed during the independent simulator test command. This is not a passing
simulator result. The follow-up splits build-for-testing from test-without-building
and uses explicit ARM64, serial testing and local ad-hoc simulator signing
(CODE_SIGNING_ALLOWED=YES, CODE_SIGN_IDENTITY=-, CODE_SIGNING_REQUIRED=NO).
Archive signing remains disabled. No signing account, keychain credential or
provisioning update is requested. Failure reporting emits only fixed stages,
exception classes, exit codes and at most eight fixed error categories; raw
output and exception paths are not printed. Actual simulator success remains pending.
