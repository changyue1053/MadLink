# Installed MadLink iOS simulator WSS acceptance preview

Exact base: public `80c9d8ffd23a5911b4f2eb71b5408b1d57717f2a`
(tree `d2fd4ed05b6bd29d65b3011a6febce99dc912a4a`). Its installed ABI,
unsigned device app link and three synthetic simulator tests are not edited.
This independent, opt-in workflow reuses that producer, public header,
static XCFramework and package checks. It requires the same exact stock
ARM64 Xcode 26.2 (17C52), both SDKs 26.2 and iOS 26.2 simulator. The independent
test binary is linked against the relocated installed static library after
deleting the producer. Exactly the previous three cases and one new case
must pass. The one canonical generated Xcode test receipt must name the
inspected host and test product with no execution overrides. It is passed
explicitly to test-without-building; the receipt, executable/product trees,
generated project and public CA include are fingerprinted before and after.
The device app is still linked only, not run; it does not compile the WSS fixture.

The new fixture links Apple Network.framework and Security in the XCTest
target only. The installed SDK supplies the unmodified C API and tracked
ledger; the fixture supplies the `ml_host_v1` transport. A job-owned Python
TLS/WebSocket peer listens only at numeric IPv4 loopback on two ephemeral
ports. Existing Python TLS and local OpenSSL are required; missing tooling
fails without downloading or installing anything. Ephemeral keys remain in
the host-only temporary directory; only the public CA bytes and two ports go
into a generated test include, then are removed with the job workspace.
There is no TLS keychain trust installation, ATS exception, system changes,
public server, real-device selection, download, or artifact upload.

- Positive: reference TLS policy requires the actual numeric IP SAN and the
  sole ephemeral anchor, with trust network fetch disabled. The peer
  verifies a real TLS/HTTP 101 exchange and the exact masked synthetic
  binary client frame. MadLink must observe the actual binary reply and
  exactly one matching local-acceptance completion followed by an empty
  completion poll. That completion is not
  peer delivery proof; the independent peer's observations are the evidence
  for this one loopback frame only.
- Negative: same anchor but a different IP SAN. On the same peer leaf, the
  actual requested IP must fail and the alternate labeled IP must pass under
  the sole anchor; this diagnostic check never grants trust. MadLink must
  observe a transport failure and the Closed state, never connected. The
  second listening peer must independently see the real TLS attempt end
  in a TLS failure without any HTTP upgrade bytes.

Callbacks only record a finite fixed message/flags; all MadLink calls remain
on its synchronous owner thread. One bounded connection attempt, with no
retry or replay semantics, and localhost-only test cleanup. Existing package
inspection and ARM64 iOS Simulator compile guards are mandatory.
No inference about the optional libcurl adapter, device runtime, crash
behavior, TLS policy for apps, production delivery, or release readiness.
Portable Python tests exercise the actual host peer against Python TLS and
synthetic structural checks; only an exact passing Apple job establishes
simulator app networking and API linkage. Apple Network stack ordering and
numeric SAN handling are documented in Apple Network.framework and the Apple
Security SSLPolicyTests.
