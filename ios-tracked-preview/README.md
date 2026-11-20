# Installed MadLink tracked C ABI on iOS (preview)

This gate uses the exact public tracked implementation
`a6d869efd8a5b3f2eb1f31e9b5c1a37392251867` (tree
`e6ee8b6ef2c8f8bfd30e5ac90ae05d7811a12350`). It takes the existing legacy
App / XCTest, 32-cycle C fixture, and project generator from public
`5b64c6f3bc7b512072c4d885b4d07b013cf24715`; their exact Git blob identities
are checked. It does not switch to that older SDK core. Existing public
header, core, default Xcode workflow and tracked Linux gate are untouched.

The normal stock Xcode producer creates the same two static framework slices.
The whole XCFramework is moved beneath a spaced directory and the temporary
producer is removed. Each slice must expose the eight v1 and three tracked C
symbols exactly once and contain the exact public header. Both the independent
device-link app and independent simulator project consume byte-identical
copies of that relocated package. No source translation unit from the vendor
core is compiled into either app.

The unsigned generic ARM64 **device link** uses the tracked declarations and
requires all three definitions in the actual linked app. It never installs
or runs. The exact owned iOS 26.2 simulator independently links and runs three
required XCTest cases:

- `MadLinkTests/testSyntheticLifecycle` (unmodified)
- `MadLinkSessionTests/testInstalledSessionRecovery32Cycles` (unmodified)
- `MadLinkTrackedTests/testInstalledTrackedCompletions`: pending and unread
  credit, true diagnostic eviction, result survival and credit recovery,
  cancellation, conservative unknown after a rejected synthetic write.

Archive Mach-O architecture, application/test architecture and platform,
before/after package bytes and exact case names/results are mandatory.
Tracked local acceptance is not delivery or a business acknowledgment.
This does not claim device runtime, iOS cohost, crash durability, newer
or older runtimes, stable versioning, release signing or publication.

The opt-in branch uses stock ARM64 macOS with Xcode 26.2 (17C52), and existing
iOS SDKs/runtime 26.2; Xcode/Simulator are not installed by the gate. Only a
new job-owned simulator is created and deleted, with no added network,
signing account, artifact upload or contact with physical devices. The
portable guard tests and same C callbacks can run on Linux; only a hosted
successful Apple link/test establishes the Apple evidence.
