"""Add exactly one authenticated WSS case to the proven installed iOS lane."""
from pathlib import Path
import importlib.util
import re
import shutil
import sys

from peer import peers
import binding

HERE = Path(__file__).resolve().parent
TRACKED = HERE.parent / "ios-tracked-preview"
sys.path.insert(0, str(TRACKED))
spec = importlib.util.spec_from_file_location("tracked", TRACKED / "verify.py")
tracked = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tracked)
from project import generate

check, run = tracked.check, tracked.run
NAME = "MadLinkWssTests/testInstalledAuthenticatedLoopbackWSS"


def exact_results(summary, cases):
    for key, want in (("totalTestCount", 4), ("passedTests", 4), ("failedTests", 0), ("skippedTests", 0)):
        check(type(summary.get(key)) is int and summary[key] == want, "wss-test-counts")
    check(summary.get("testStatus", "Passed") == "Passed" and summary.get("expectedFailures", 0) == 0, "wss-result")
    seen = set()
    def walk(nodes):
        check(isinstance(nodes, list), "wss-test-tree")
        for node in nodes:
            check(isinstance(node, dict) and node.get("result", "Passed") == "Passed", "wss-result")
            if node.get("nodeType") == "Test Case":
                name = node.get("nodeIdentifier")
                check(isinstance(name, str) and node.get("result") == "Passed", "wss-name")
                name = name.removesuffix("()")
                check(name in tracked.TESTS | {NAME} and name not in seen, "wss-name")
                seen.add(name)
            walk(node.get("children", []))
    walk(cases.get("testNodes"))
    check(seen == tracked.TESTS | {NAME}, "wss-name")


def write_fixture(folder, der, ports):
    check(type(der) is bytes and 256 <= len(der) <= 2048 and len(ports) == 2 and len(set(ports)) == 2 and
          all(type(port) is int and 1 <= port <= 65535 for port in ports), "wss-input")
    hex_rows = [",".join(f"0x{x:02x}" for x in der[i:i + 16]) for i in range(0, len(der), 16)]
    (folder / "LoopbackJob.inc").write_text(
        "#include <stdint.h>\n"
        + f"constexpr uint16_t kValidPort={ports[0]}, kWrongPort={ports[1]};\n"
        + "constexpr uint8_t kRootDer[]={\n" + ",\n".join(hex_rows) + "\n};\n", encoding="ascii")


def prepare(folder, xc, der, ports):
    # Preserve the exact original file setup and project generator. Regenerate
    # only its disposable Xcode project to add one test-source and framework pair.
    local = tracked.prepare_consumer(folder, xc, True)
    shutil.rmtree(folder / "Preview.xcodeproj")
    shutil.copyfile(HERE / "WssTests.mm", folder / "WssTests.mm")
    write_fixture(folder, der, ports)
    generate(folder, test_sources=("SessionTests.mm", "SessionLifecycle.c", "TrackedTests.mm",
                                   "TrackedFixture.c", "WssTests.mm"),
             test_settings={"OTHER_LDFLAGS": ["-lc++", "-framework", "Foundation", "-framework", "XCTest",
                                              "-framework", "Network", "-framework", "Security"]})
    return local


def simulator(work, xc, original):
    folder = work / "independent simulator consumer"
    build = work / "simulator build"
    result = work / "result.xcresult"
    cert_dir = work / "peer secrets"
    cert_dir.mkdir(mode=0o700)
    with peers(cert_dir) as (der, ports, start):
        local = prepare(folder, xc, der, ports)
        udid = run(["xcrun", "simctl", "create", "MadLinkWSSPreview", "com.apple.CoreSimulator.SimDeviceType.iPhone-17",
                    "com.apple.CoreSimulator.SimRuntime.iOS-26-2"], "sim-create", capture=True, timeout=60).strip()
        check(re.fullmatch(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", udid), "simulator-uuid")
        try:
            run(["xcrun", "simctl", "boot", udid], "sim-boot")
            run(["xcrun", "simctl", "bootstatus", udid, "-b"], "sim-ready")
            common = ["-project", "Preview.xcodeproj", "-scheme", "Preview", "-configuration", "Debug",
                      "-destination", "platform=iOS Simulator,id=" + udid, "-derivedDataPath", build, "ARCHS=arm64",
                      "ONLY_ACTIVE_ARCH=YES", "-parallel-testing-enabled", "NO", "CODE_SIGNING_ALLOWED=YES",
                      "CODE_SIGN_IDENTITY=-", "CODE_SIGNING_REQUIRED=NO", "ENABLE_DEBUG_DYLIB=NO"]
            run(["xcodebuild", "build-for-testing", *common], "build-for-testing", cwd=folder)
            products = build / "Build/Products"
            selected = binding.select(products)
            receipt, host, test = selected
            tracked.inspect_product(host, True, False)
            tracked.inspect_product(test, True, True)
            before = binding.snapshot(folder, selected, tracked.fingerprint)
            jobs = start()
            run(["xcodebuild", "test-without-building", "-xctestrun", receipt,
                 "-destination", "platform=iOS Simulator,id=" + udid,
                 "-destination-timeout", "120", "-parallel-testing-enabled", "NO",
                 "-resultBundlePath", result], "test-without-building", cwd=folder, timeout=120)
            after = binding.select(products)
            check(after == selected and binding.snapshot(folder, after, tracked.fingerprint) == before,
                  "simulator-product-mutation")
            for job, reason in zip(jobs, ("wss-peer-echo", "wss-peer-reject-before-upgrade")):
                try:
                    job.result(timeout=10)
                except Exception:
                    raise tracked.Failure(reason) from None
            exact_results(*tracked.read_xctest_results(result))
            check(tracked.fingerprint(local) == original, "simulator-package-mutation")
        finally:
            run(["xcrun", "simctl", "delete", udid], "sim-delete")
    print("PASS: installed ARM64 simulator MadLink C ABI, three existing cases and authenticated WSS loopback",
          flush=True)


if __name__ == "__main__":
    try:
        # Keep stock toolchain, producer, artifact inspection and unsigned
        # generic device link from the exact green parent. Only replace the
        # simulator runner in this separate explicit qualification process.
        tracked.simulator_test = simulator
        tracked.main()
    except tracked.Failure as error:
        raise SystemExit("FAIL: " + str(error)) from None
    except ValueError as error:
        fixed = {"wss-receipt-path", "wss-receipt-size", "wss-receipt-format", "wss-receipt-coverage",
                 "wss-receipt-target", "wss-receipt-root", "wss-receipt-plan", "wss-receipt-config",
                 "wss-receipt-execution-override", "wss-receipt-host", "wss-receipt-bundle",
                 "wss-receipt-dependencies", "wss-receipt-env", "wss-receipt-loader", "wss-receipt-products",
                 "wss-receipt-count", "wss-receipt-identity"}
        label = str(error)
        raise SystemExit("FAIL: " + (label if label in fixed else "wss-receipt-invalid")) from None
    except Exception:
        raise SystemExit("FAIL: WSS qualification infrastructure") from None
