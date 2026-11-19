# Android ARM64 Prefab preview

Based on public cd1bd262 / tree e191f0a854a1c50a9d67304d8fa9613a6f21a640.
This is an opt-in native SDK, not a Java/Kotlin SDK API. The consumer JNI belongs
only to the test App. Default core, host checks, curl and MadObs remain unchanged.

Pinned tools: JDK 17, Gradle 8.9, AGP 8.7.3, NDK r28c 28.2.13676358,
SDK 35, Build Tools 35.0.0, CMake 3.22.1. Use already authorized official SDK
packages; no license acceptance is performed by the driver. CMake package
availability and all Android builds remain unverified until executed.

Run `python3 packaging/test-android-preview.py --sdk SDK --gradle GRADLE_BIN`.
It builds a static PIC core Prefab AAR with only the C header, deletes its
disposable producer, moves the artifact to a path with spaces, then builds a
separate Gradle-root App consuming only that AAR through find_package. No producer
project dependency or runtime telemetry exists. Compile dependencies are external
Google/Maven artifacts, not an offline build. Exact tools are pinned, not every
transitive artifact or hosted image; no bit-reproducibility claim.

The single test JNI .so links static libc++; this is not a multi-DSO runtime
policy. Existing C boundary ownership/thread/OOM-poison/no-replay semantics apply.
ARM64 minSdk24 only. AAR includes first-party MIT and existing third-party notices.
NDK/compiler runtime licensing is not relicensed by MIT; review actual linked
runtime notices before distributing binaries. No binary publication is included.

Build gate checks actual final APK ELF LOAD alignment, uncompressed 16KiB ZIP
entry alignment, zipalign, and builds the instrumentation APK. It DOES NOT run
Android. No adb, emulator, device discovery, INTERNET permission, network executor,
MadObs or curl integration. The synthetic App JNI checks connect/send/written/close;
its android.test instrumentation invokes the same assertions. No receive,
reconnect, mobile lifecycle or complete ABI test coverage is claimed by this smoke.

A later authorized device gate must install and run instrumentation on ARM64
4KiB and 16KiB Android, verify actual page size 16384 for the latter and disable
compatibility-mode reliance. Build success is not runtime compatibility. AAB and
Play publishing are outside this preview.

Official references:
- https://developer.android.com/build/native-dependencies
- https://developer.android.com/ndk/guides/cmake
- https://developer.android.com/guide/practices/page-sizes
- https://developer.android.com/ndk/guides/cpp-support

Tool version selection follows the publicly tested MadDB checkpoint
bb01de26c60e0ac8efab830f1f7dd663cbf623ae; its official Gradle8.9 checksum is reused.
No MadDB implementation is copied. The new workflow uses the existing MadLink
pinned checkout action. SDK installation reads stdin from /dev/null, relying only
on existing runner licenses; no `--licenses` or acceptance piping. A license or
package availability failure is a blocker, not a successful build. No raw test
logs/artifacts are uploaded and no main branch trigger is introduced.

## Bounded failure diagnostics

The Android build driver reports only named stage, exception class, numeric child
exit, and up to eight fixed Gradle/CMake/compiler diagnostic categories. It never
echoes arbitrary tool-message suffixes, commands, environment, URLs, paths or full
logs. This intentionally over-redacts rather than trusting a secret regex. Child
output is disk-backed; at most 256 KiB from each end of each stream is scanned. Unrecognized messages
may therefore require a further narrowly scoped diagnostic patch. No presumed
build failure has been fixed without evidence; package/runtime gates are unchanged.

Consumer APK assembly and instrumentation APK assembly now have separate diagnostic
stages. Failed Gradle tasks are emitted only when their complete path equals an
explicit fixed allowlist entry, never an arbitrary extracted task/path. At most
four task names are emitted. Bounded log tails are examined because Gradle often
reports failures after lengthy progress output. No consumer configuration change
is inferred from an exit code alone.

The retained legacy instrumentation smoke explicitly compiles against SDK optional
`android.test.runner` and `android.test.base` libraries. This follows Android's
legacy JUnit3 setup guidance and the same SDK35/AGP8.7.3 configuration used in the
public MadDB preview. No Maven test dependency or network permission is added.
AGP generates the instrumentation manifest; device execution remains unverified.
Reference: https://developer.android.com/training/testing/instrumented-tests/androidx-test-libraries/test-setup

Hosted run 44456901934 reached successful ordinary consumer APK assembly, then
failed at compileDebugAndroidTestJavaWithJavac. The optional-library fix still
requires hosted compilation. The later ELF/ZIP alignment assertions have NOT
passed yet, because the driver stops on instrumentation compilation failure.
