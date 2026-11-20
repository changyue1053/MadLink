"""Use a closed stock scheme route without passing the build receipt to Xcode."""
import os
from pathlib import Path
import pwd
import re
import tempfile

import scheme_authority as authority
from verify import check, exact_results, peers, prepare, run, tracked
import sdk_package


def stock(tool, args, stage, **kwargs):
    return run([authority.TOOLS[tool], *args], stage, **kwargs)


def stock_preflight():
    app = Path(authority.XCODE_APP)
    check(app.is_dir() and app.resolve(strict=True) == app, "scheme-xcode-canonical")
    for filename in authority.TOOLS.values():
        path = Path(filename)
        check(path.is_file() and path.resolve(strict=True) == path, "scheme-xcode-tool-canonical")
    stock("codesign", ["--verify", "--strict",
                       '-R=identifier "com.apple.dt.Xcode" and anchor apple', app], "version", timeout=90)
    stock("codesign", ["--verify", "--strict", "-R=anchor apple", authority.TOOLS["xcodebuild"]],
          "version", timeout=45)
    designated = stock("codesign", ["-d", "-r-", app], "version", capture=True, timeout=45)
    resolution = stock("xcrun", ["--find", "xcodebuild"], "version", capture=True, timeout=45)
    version = stock("xcodebuild", ["-version"], "version", capture=True, timeout=45)
    authority.stock_identity(app, resolution, designated, version)


def verified_run(command, stage, **kwargs):
    # Reused package/tracked functions must share the same exact pinned
    # launcher as the final consumer, not the /usr/bin xcodebuild shim.
    tool = authority.TOOLS.get(str(command[0]))
    check(tool is not None, "scheme-xcode-tool-route")
    return run([tool, *command[1:]], stage, **kwargs)


def inspect_product(path, test):
    tracked.inspect_product(path, True, test)
    stock("codesign", ["--verify", "--strict", path.parent], "sim-inspect", timeout=45)
    signature = stock("codesign", ["-d", "--verbose=4", path.parent], "sim-inspect", capture=True, timeout=45)
    check(signature.splitlines().count("Signature=adhoc") == 1, "scheme-ad-hoc-signature")
    linked = authority.dependencies(stock("xcrun", ["otool", "-L", path], "sim-inspect", capture=True, timeout=45))
    authority.loader_controls(stock("xcrun", ["otool", "-l", path], "sim-inspect", capture=True, timeout=45))
    if test:
        check({"@rpath/XCTest.framework/XCTest", "/System/Library/Frameworks/Network.framework/Network",
               "/System/Library/Frameworks/Security.framework/Security"} <= linked, "scheme-frameworks")


def arguments(udid, build, products):
    check(re.fullmatch(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", udid), "simulator-uuid")
    return ["-project", "Preview.xcodeproj", "-scheme", "Preview", "-configuration", "Debug",
            "-destination", "platform=iOS Simulator,id=" + udid, "-derivedDataPath", build,
            "ARCHS=arm64", "ONLY_ACTIVE_ARCH=YES", "-parallel-testing-enabled", "NO",
            "CODE_SIGNING_ALLOWED=YES", "CODE_SIGN_IDENTITY=-", "CODE_SIGNING_REQUIRED=NO",
            "ENABLE_DEBUG_DYLIB=NO", "SYMROOT=" + str(products)]


def simulator(work, xc, original):
    folder = work / "independent simulator consumer"
    build = work / "simulator build"
    products = build / "Build/Products"
    result = work / "result.xcresult"
    evidence_dir = work / "receipt retained outside launch roots"
    evidence_dir.mkdir(mode=0o700)
    evidence = evidence_dir / "stock-receipt.plist"
    tomb = evidence_dir / "stock-build-project.evidence"
    cert_dir = work / "peer secrets"
    cert_dir.mkdir(mode=0o700)
    with peers(cert_dir) as (der, ports, start):
        local = prepare(folder, xc, der, ports)
        graph = authority.close_launch_inheritance(folder)
        check(tracked.fingerprint(local) == original, "simulator-package-mutation")
        print("WSS_SCHEME pre-build-authored-verified", flush=True)
        check(not build.exists() and not result.exists(), "scheme-fresh-roots")
        udid = stock("xcrun", ["simctl", "create", "MadLinkWSSPreview", "com.apple.CoreSimulator.SimDeviceType.iPhone-17",
                              "com.apple.CoreSimulator.SimRuntime.iOS-26-2"],
                     "sim-create", capture=True, timeout=120).strip()
        common = arguments(udid, build, products)
        try:
            stock("xcrun", ["simctl", "boot", udid], "sim-boot")
            stock("xcrun", ["simctl", "bootstatus", udid, "-b"], "sim-ready")
            stock("xcodebuild", ["build-for-testing", *common], "build-for-testing", cwd=folder)
            print("WSS_SCHEME build-for-testing-completed", flush=True)
            check(tracked.fingerprint(local) == original, "simulator-package-mutation")
            authority.quarantine_project(folder, build, tomb, graph)
            print("WSS_SCHEME post-build-authored-restored", flush=True)
            selected, receipt_digest = authority.receipt(products, evidence)
            check(not any(build.rglob("*.xctestrun")), "scheme-no-derived-receipt")
            host, tests = authority.product_paths(products, selected)
            authority.sysroot_inventory(products, selected, local)
            inspect_product(host, False)
            for compiled in tests.values():
                inspect_product(compiled, True)
            before = authority.snapshot(folder, products, selected, evidence, tracked.fingerprint)
            jobs = start()
            print("WSS_SCHEME pre-launch-closed-graph-and-artifacts-verified", flush=True)
            # Do not give Xcode the stock receipt, test selectors, or a
            # substituted plan. It searches only the exact job-local SYMROOT.
            stock("xcodebuild", ["test-without-building", *common, "-resultBundlePath", result],
                  "test-without-building", cwd=folder, timeout=120)
            print("WSS_SCHEME scheme-launch-returned", flush=True)
            check(not any(build.rglob("*.xctestrun")), "scheme-no-derived-receipt")
            after = authority.snapshot(folder, products, selected, evidence, tracked.fingerprint)
            check(after == before and authority.digest(evidence) == receipt_digest, "scheme-launch-mutation")
            for job, reason in zip(jobs, ("wss-peer-echo", "wss-peer-reject-before-upgrade")):
                try:
                    job.result(timeout=10)
                except Exception:
                    raise tracked.Failure(reason) from None
            exact_results(*tracked.read_xctest_results(result))
            check(tracked.fingerprint(local) == original, "simulator-package-mutation")
            print("WSS_SCHEME post-launch-closure-verified", flush=True)
        finally:
            stock("xcrun", ["simctl", "delete", udid], "sim-delete")
    print("PASS: stock authored-scheme ARM64 simulator WSS with exact four installed cases", flush=True)


def main():
    home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve(strict=True)
    # Use a job-owned temporary root; do not honor an ambient TMPDIR.
    with tempfile.TemporaryDirectory(prefix="madlink-closed-xcode-", dir="/private/tmp") as tmp:
        sandbox = Path(tmp).resolve(strict=True)
        os.environ.clear()
        os.environ.update(authority.clean_environment(home, sandbox))
        tempfile.tempdir = str(sandbox)
        stock_preflight()
        tracked.run = verified_run
        sdk_package.run = verified_run
        tracked.simulator_test = simulator
        tracked.main()


if __name__ == "__main__":
    try:
        main()
    except tracked.Failure as error:
        raise SystemExit("FAIL: " + str(error)) from None
    except ValueError as error:
        fixed = {"scheme-graph-location", "scheme-graph-root", "scheme-graph-canonical",
                 "scheme-graph-directory", "scheme-graph-member", "scheme-graph-digest",
                 "scheme-evidence-format", "scheme-evidence-target", "scheme-evidence-loader",
                 "scheme-evidence-loader-override", "scheme-evidence-count", "scheme-evidence-quarantine",
                 "scheme-products-root", "scheme-test-product", "scheme-extra-product", "scheme-product-identity",
                 "scheme-product-dependency", "scheme-product-rpath", "wss-receipt-path", "wss-receipt-size",
                 "wss-receipt-format", "wss-receipt-coverage", "wss-receipt-target", "wss-receipt-root",
                 "wss-receipt-plan", "wss-receipt-config", "wss-receipt-execution-override",
                 "wss-receipt-host", "wss-receipt-bundle", "wss-receipt-dependencies",
                 "wss-receipt-env", "wss-receipt-loader", "scheme-xcode-tool-resolution",
                 "scheme-xcode-bundle-identity", "scheme-xcode-designated-identity", "scheme-xcode-version",
                 "scheme-inventory-canonical", "scheme-inventory-type", "scheme-inventory-debug-layout",
                 "scheme-inventory-debug-format", "scheme-inventory-static-layout", "scheme-inventory-static-format",
                 "scheme-inventory-closed", "scheme-inventory-pkginfo", "scheme-loader-control",
                 "scheme-product-launch-metadata", "scheme-graph-size", "scheme-graph-parent-scheme",
                 "scheme-graph-build-mutation", "scheme-project-quarantine", "scheme-project-restore",
                 "scheme-launch-location"}
        label = str(error)
        raise SystemExit("FAIL: " + (label if label in fixed else "closed-stock-scheme-invalid")) from None
    except Exception:
        raise SystemExit("FAIL: closed-stock-scheme-infrastructure") from None
