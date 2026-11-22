# Validation scope

The default MadLink source tests are Linux host checks. The core, C ABI and
tracked completion fixtures use synthetic owner-thread callbacks, not sockets
or a real service. The tests exercise lifecycle, limits, retry and cancellation,
generation isolation, allocation failure, bounded completion credit and drain
after poison. Run them with the commands in [README.md](README.md).

The [relocation test](packaging/test-relocation.py) removes a disposable producer
before building independent C consumers against its moved header/archive.
The [tracked test](packaging/test-tracked-completions.py) runs legacy, tracked
and allocation-fault consumers against a single moved SDK. Its UBSan mode is
not AddressSanitizer or leak evidence.

The [ABI upgrade check](packaging/abi-upgrade/README.md) separately compares the
reviewed public pre-tracked and tracked trees. It compiles old-header consumer
objects once, links/runs them against both static archives, and requires the
tracked object to fail on the old archive for exactly the three added symbols.
This is Linux x86-64 same-toolchain relinking evidence for those fixtures, not
binary replacement, arbitrary legacy compatibility, or mobile compatibility.

Compiler-matrix cases with tools unavailable are not run and the matrix is
incomplete. No mobile runtime, public-network transport, peer delivery, release,
or production qualification follows from any of these host checks.
