# Linux frozen-object C ABI upgrade checkpoint

Tests exact public pre-tracked commit `0f33e1383503babe7d489fc3f771fc622d7cff75`
(tree `b009e48a3a07099c96c32fe62d735ddba9765f0b`) against tracked commit
`a6d869efd8a5b3f2eb1f31e9b5c1a37392251867`
(tree `e6ee8b6ef2c8f8bfd30e5ac90ae05d7811a12350`). It requires locally
present Git objects and existing Linux x86-64 GNU C/C++ tools. It fetches,
installs or configures no system tools/dependencies and uses no network at
runtime.

Both immutable trees run their own existing package installer into separate
temporary roots; both install prefixes move, and both producer/build trees
are removed before compiling any consumer. The old header and three legacy
source files have fixed Git blob IDs; the latter must be identical in both
trees. GCC compiles each legacy C source only once, with the relocated **old**
public header; dependency files prove the observed header. Each ELF64 C
relocatable object's SHA-256, file identity and exact old C-symbol references
are checked. Each exact object is then passed unchanged to a static relink with
each relocated archive, with no C source or header on either link command.
The expected send/close, receive/cancel/ownership isolation and stale-generation
case reports must match exactly in all six runs.

The archives contain exactly the eight legacy named public C definitions in
the old case and those same eight plus only `ml_create_tracked_v1`,
`ml_send_tracked_v1`, and `ml_next_completion_v1` in the new case. Static ELF
public symbol counts (including extra plain C symbols/data), not C++ mangled
private implementation ABI, are checked. The existing new-header tracked
fixture separately compiles once, must fail to link against the old archive
for exactly the three new unresolved names, then must execute against the new
archive with its known completion/credit/handle assertions.

```sh
python3 -B packaging/abi-upgrade/test_verify.py
python3 -B packaging/abi-upgrade/verify.py
```

If only previously verified equivalent local commit IDs exist, pass
`--old-ref <40-hex>` and `--new-ref <40-hex>`; tree and per-file blob pins
remain mandatory. The controls also reject a wrong tree, wrong compiled
header, stale/replaced object, missing/duplicate/unexpected export, or a
linker failure with the wrong undefined symbols.

This is proof for unchanged legacy object **relinking** and the exercised
runtime behavior on one Linux x86-64 GCC/G++/GNU binutils toolchain. It does
not replace code inside an already linked static executable, assert full ABI
compatibility for arbitrary callers, prove DSO drop-in replacement, claim
cross-compiler/cross-architecture or mobile interoperability, or create a
production release. No binary is persisted, uploaded or added to source.
