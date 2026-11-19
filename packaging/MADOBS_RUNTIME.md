# Opt-in real runtime host check

This proposed next stage builds the public MadObs commit
`79fd8ced44a18bca574598ff683cd706ded16a60` and uses its real installed
`MadObs::runtime`, not copied headers or a simulated observer. It does not change
MadLink's standalone SDK dependencies or existing CI jobs.

Run `python3 packaging/test-madobs-runtime.py PUBLIC_MADOBS_CHECKOUT` with that exact
clean public Git checkout and CMake >=3.20, Python >=3.12, GCC/G++ (C++20 for upstream),
make, zlib development headers, pkg-config and binutils already available. The driver
never downloads or installs anything. Missing tools are a failure/NOT RUN, not a skip
or proof of runtime compatibility. The hosted job obtains tools from official Ubuntu
packages and fetches only the pinned public repository without credentials; failure
has no private-source or alternate-version fallback. No extra GitHub action is added.

Producer source/build copies are disposable. The real upstream CMake installer and
MadLink installer produce separate prefixes, which are moved to space-containing
paths. Only the generated copies are removed. An independent C++ consumer then finds
MadObs 0.1.0 EXACT and links the installed archives; compiler dependencies must exclude
producer headers and MadLink's C++ API. The optional queue header is staged separately.

The consumer drives three synthetic MadLink C state events into the bounded queue,
then binds/drains through `madobs_observer_for_runtime`. It checks actual runtime
admission/drain/drop counters separately from adapter callback-invocation counters.
Stopping joins the worker before final verification and teardown. A sequential
post-stop negative probe demonstrates that callback invocation is not admission.
The supplied sink makes no network calls: it validates real batches through the
public policy validator and acknowledges local discard. At least one batch must be
observed; zero callbacks cannot pass. Callback counters are atomic, and the callback
never reenters the owner-thread queue or calls runtime stop/destroy.

Synthetic WAL data lives only in ignored temporary build output. No WAL contents,
raw event batches, upstream source, binaries or logs are uploaded. This is a null
crypto-provider configuration, explicitly without BoringSSL, JNI, server demos or
upstream test targets. It proves neither encryption nor authenticated telemetry
transport. No real telemetry endpoint, restart/durability, exporter delivery, mobile,
cross-thread queue use or cross-platform compatibility is claimed. It does not
change upstream licensing, and does not publish upstream sources or binaries.

Local implementation checks without CMake are syntax/static checks only. The real
upstream build/install, relocated consumer link/run and hosted scheduling remain
unverified until an actual successful run of this added job. Existing API-only tests
are separate evidence and cannot turn this stage green.
