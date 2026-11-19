# Opt-in OpenHarmony native cross-link gate (UNRUN)

Source-only candidate based on public MadLink checkpoint
`0f33e1383503babe7d489fc3f771fc622d7cff75`, tree
`b009e48a3a07099c96c32fe62d735ddba9765f0b`. Local equivalent parent is
`3e0cac996ba4f8c716134784a9d9fc131dfc1eb1`.
No IMSDK, MadObs runtime, transport adapter, other repository, production source,
license or default workflow changes. There is no automatic CI job and no skipped
check presented as a successful target build.

## Prerequisites and trust boundary

This is Linux x86_64 host only. The caller must already possess a verified official
OpenHarmony **public 6.0.0.47 / API20 native SDK**, its retained official release
archive, the SDK-bundled CMake >=3.20 at `native/build-tools/cmake/bin/cmake` and
a preinstalled host make. Nothing downloads, installs,
extracts the SDK, accepts licenses, signs in or connects devices.

The official archive and checksum could not be obtained in this environment.
**No official checksum is supplied or invented.** Do not fill the trust input
with a locally guessed checksum or a mirror. Actual execution is blocked until
an authorized operator independently verifies the official publisher checksum,
installation derivation and receipt. A URL and an SDK version string do not
prove provenance. The script verifies receipt and installed-file integrity;
it does NOT independently authenticate the publisher or validate licenses.

Supply an externally reviewed JSON receipt and its SHA256 through a trusted
channel. Do not generate and automatically trust a new receipt in this gate.
The schema (descriptive placeholders below are not runnable evidence) is:

- `schema`: integer 1
- `version`: `6.0.0.47`; `api`: integer 20; `component`: `native`
- `provenance_verified`: true, attested by the independent authorized reviewer
- `official_archive_url`: official HTTPS `repo.huaweicloud.com/openharmony/` release URL
- `official_archive_sha256`: independently verified official 64-hex checksum
- `native_files`: complete map of native-root relative paths to
  `{"sha256": "..."}` for regular files or `{"symlink": "relative-target"}`
  for symlinks. Relative internal symlinks only; no absolute, escaping or broken symlinks.

The reviewer binds this manifest to the verified archive's installed native
component. The script checks the retained archive hash and every native SDK file
against that pinned receipt before executing SDK tools. SDK metadata
`oh-uni-package.json` must report `path=native`, `version=6.0.0.47` and
`apiVersion=20`. A different metadata layout fails closed; it has not yet been
validated against the unavailable official archive. No substitute SDK is allowed.

## Explicit invocation

```sh
python3 scripts/check-ohos-native.py --run \
  --sdk /absolute/preinstalled/native \
  --archive /absolute/verified-official-release-archive \
  --receipt /absolute/independently-reviewed-receipt.json \
  --receipt-sha256 "$EXTERNALLY_APPROVED_RECEIPT_SHA256" \
  --expected-sha "$REVIEWED_FULL_CANDIDATE_SHA" \
  --cmake /absolute/preinstalled/native/build-tools/cmake/bin/cmake
```

Without `--run` the gate exits nonzero before any SDK work. Exact clean candidate
HEAD is required. Caller compiler flags/environment are not inherited by build
commands; SDK and toolchain paths are explicit. The CMake executable must resolve to the fixed SDK-bundled path within the
manifest-verified native tree; arbitrary external CMake executables are rejected.
SDK installations must remain immutable for the run. Source/header inspection and local Python tests are not
substitutes for this opt-in gate.

## Intended evidence, not a claim of a completed build

The existing repo has no root CMake project. An isolated temporary CMake wrapper
builds exactly the two unchanged core C++17 files using
`native/build/cmake/ohos.toolchain.cmake`, `OHOS_ARCH=arm64-v8a`,
`OHOS_PLATFORM=OHOS`, `OHOS_STL=c++_shared`. API20 is verified from the pinned
SDK metadata, not by pretending the platform string is an API integer.
MadObs is explicitly OFF and enabling it is fatal. No original installer changes.

It installs a static `libmadlink.a`, public C header, notices and relocatable
`MadLink::madlink` CMake export into temporary storage, then moves the installed
prefix into a spaced path and removes the whole temporary producer tree. An
independent C11 consumer uses only that moved package through `find_package`
with `NO_DEFAULT_PATH`, then links a shared fixture via the target C++ driver.
No target executable is run. The cache must select the OHOS ARM64 toolchain and static configuration.
Compiler cache keys are checked if present, but are not required: a toolchain
may use normal CMake `set` variables. Instead, both generated
`CMakeCCompiler.cmake` and `CMakeCXXCompiler.cmake` records are mandatory and must
identify the verified SDK drivers. Every actual exported compile command must
use the exact corresponding SDK clang/clang++ driver, one
`--target=aarch64-linux-ohos` (or separated `-target`), one verified SDK sysroot,
the exact expected source and an object within that build. Producer proof covers
both core C++ files; consumer proof covers its independent C file. Missing,
extra, duplicate or foreign sources, response files, conflicting target/sysroot,
language overrides and foreign CPU specialization fail. ARM64 baseline `armv8-a`
is permitted; absent explicit architecture flags are permitted because exact
AArch64 target and final ELF remain mandatory. No guessed numeric API suffix is
accepted; API20 remains pinned SDK metadata evidence. Projects also reject a
non-OHOS target. These conservative patterns still await an actual SDK run. Shared
link uses `-z defs`; the ELF must be little-endian ARM64 ET_DYN with bounded,
non-W+X, congruent >=4KiB PT_LOADs, no interpreter, RPATH/RUNPATH or TEXTREL.
All eight public ABI symbols and the C probe must be defined. DT_NEEDED is
limited to target libc/libm/libdl/libc++_shared. Any unexpected dependency fails.
Target libc++ remains a required platform dependency, not copied into the SDK.

Only fixed stage outcomes are printed for tool failures. Detailed tool output is
discarded; temporary artifacts are removed on normal/error unwinding. SIGKILL
or host loss cannot guarantee cleanup. No package/source/log upload or release.

This is not HAR/HAP, ArkTS/NAPI integration, commercial HarmonyOS certification,
device installation, loader/runtime ABI validation, real networking, or a
16KiB-device compatibility claim. Even a future successful cross-link proves
only this exact SDK/target/source combination. A real cross-build failure must
be reviewed before changing production code or loosening checks.

## Local checks

Thirteen local structural/negative tests pass after compiler-proof and cache-parser
hardening. Cache records use line-by-line full matches, not multiline negated
character classes. Blank lines, standard generated comments and CRLF are
accepted; duplicate keys, malformed records, shebang input and known-value drift
are rejected. This is parser evidence only; official SDK status is unchanged.

`PYTHONDONTWRITEBYTECODE=1 python3 scripts/test-ohos-native.py` covers synthetic
ELF acceptance/rejections, receipt integrity/tampering, escaping symlinks,
standalone CMake scope, explicit opt-in and fixed failure output. Synthetic
receipts are **not SDK provenance evidence**. The C fixture can be syntax-checked
with a host C11 compiler; that is not an OHOS link. Native SDK, CMake, real target
build/installation/relocation/ELF checks remain UNRUN in this environment.

## Primary references

- [OpenHarmony 6.0 version mapping](https://github.com/openharmony/docs/blob/OpenHarmony-6.0-Release/en/release-notes/OpenHarmony-v6.0-release.md): public SDK 6.0.0.47, API20.
- [OpenHarmony ABI and CMake toolchain](https://github.com/openharmony/docs/blob/OpenHarmony-6.0-Release/en/application-dev/napi/ohos-abi.md): ARM64, LLVM libc++, ELF and `OHOS_ARCH`.
- [Official OpenHarmony build wiki](https://gitee.com/openharmony/build/wikis/pages/export?doc_id=3015289&type=pdf): native CMake toolchain and `OHOS_PLATFORM=OHOS` / C++ STL choices.

These references describe the design; they are not receipts for a local toolchain.

- [Official native build overview](https://gitcode.com/openharmony/docs/blob/master/zh-cn/application-dev/napi/build-with-ndk-overview.md): explicit OHOS compiler target and sysroot.
