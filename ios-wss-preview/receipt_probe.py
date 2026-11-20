"""Build-only receipt probe; it cannot authorize or launch a test."""
from itertools import islice
import plistlib
import re

import binding
from verify import check, prepare, run, tracked

PREFIX = "WSS_RECEIPT_PROBE "
MAX_RECEIPT = 1024 * 1024
POLICY_LABELS = frozenset((
    "wss-receipt-format", "wss-receipt-coverage", "wss-receipt-target", "wss-receipt-root",
    "wss-receipt-plan", "wss-receipt-config", "wss-receipt-execution-override", "wss-receipt-host",
    "wss-receipt-bundle", "wss-receipt-dependencies", "wss-receipt-env", "wss-receipt-loader",
))
METADATA = "__xctestrun_metadata__"
FORMAT = "FormatVersion"


def describe(document):
    """Finite shape categories only; never preserve or render input content."""
    if not isinstance(document, dict):
        return ["root:not-dictionary"]
    result = ["root:dictionary"]
    if METADATA not in document:
        result.append("metadata:absent")
    elif not isinstance(document[METADATA], dict):
        result.append("metadata:not-dictionary")
    else:
        meta = document[METADATA]
        result.append("metadata:dictionary")
        extra = len(meta) - int(FORMAT in meta)
        result.append(("metadata-extra:none", "metadata-extra:one", "metadata-extra:multiple")[min(extra, 2)])
        if FORMAT not in meta:
            result.append("format:absent")
        elif type(meta[FORMAT]) is not int:
            result.append("format:not-integer")
        elif meta[FORMAT] == 1:
            result.append("format:one")
        elif meta[FORMAT] == 2:
            result.append("format:two")
        else:
            result.append("format:unsupported-integer")
    configs = document.get("TestConfigurations")
    v1 = document.get(binding.TEST)
    result.append("route-v1:" + ("dictionary" if isinstance(v1, dict)
                                 else "wrong-type" if binding.TEST in document else "absent"))
    result.append("route-v2:" + ("single-dictionary" if isinstance(configs, list) and len(configs) == 1
                                 and isinstance(configs[0], dict) else "other" if "TestConfigurations" in document
                                 else "absent"))
    route_target = v1 if isinstance(v1, dict) else None
    if isinstance(configs, list) and len(configs) == 1 and isinstance(configs[0], dict):
        config = configs[0]
        result.append("v2-config:" + ("enabled" if config.get("IsEnabled", True) is True else "other"))
        targets = config.get("TestTargets")
        one_target = isinstance(targets, list) and len(targets) == 1 and isinstance(targets[0], dict)
        result.append("v2-target:" + ("single-dictionary" if one_target else "other"))
        route_target = targets[0] if one_target and route_target is None else None
    # If exactly one prospective route is visible, report the independently
    # applicable path/loader shape even when outer metadata is already invalid.
    # This does not bypass the original validator or authorize any launch.
    if route_target is not None:
        host, bundle = route_target.get("TestHostPath"), route_target.get("TestBundlePath")
        hosts = (binding.ROOT + binding.APP, binding.ROOT + binding.HOST)
        bundles = (binding.ROOT + binding.TOP, binding.ROOT + binding.NESTED, "__TESTHOST__/PlugIns/SmokeTests.xctest")
        result.append("target-host:" + ("known" if host in hosts else "other"))
        result.append("target-bundle:" + ("known" if bundle in bundles else "other"))
        environment = route_target.get("TestingEnvironmentVariables", {})
        known_keys = {"DYLD_FRAMEWORK_PATH", "DYLD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
                      "XCInjectBundleInto", "XCInjectBundle"}
        result.append("target-loader:" + (
            "known-keys" if isinstance(environment, dict) and set(environment) <= known_keys else "other"))
        result.append("target-selection:" + (
            "none" if all(route_target.get(key, []) == [] for key in ("OnlyTestIdentifiers", "SkipTestIdentifiers",
                                                                      "CommandLineArguments")) else "other"))
    coverage = document.get("CodeCoverageBuildableInfos", [])
    result.append("coverage:" + ("empty" if coverage == [] else "other"))
    try:
        choice = binding.bundle_path(document)
    except ValueError as error:
        fixed = error.args[0] if len(error.args) == 1 else None
        result.append("policy:" + (fixed if isinstance(fixed, str) and fixed in POLICY_LABELS else "invalid"))
    else:
        result.append("policy:accepted-structure")
        result.append("bound-bundle:" + ("top" if choice == binding.TOP else "nested"))
    return result


def plist_shape(path, limit):
    try:
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            return "too-large", None
        return "parsed", plistlib.loads(data)
    except Exception:
        return "invalid", None


def inspect(products):
    if not products.is_dir() or products.resolve(strict=True) != products:
        return ["products:noncanonical"]
    manifests = list(islice(products.glob("*.xctestrun"), 2))
    if len(manifests) != 1:
        return ["receipt:" + ("absent" if not manifests else "multiple")]
    try:
        receipt = binding.exact(products, manifests[0].name)
    except (OSError, ValueError):
        return ["receipt:noncanonical"]
    status, document = plist_shape(receipt, MAX_RECEIPT)
    result = ["receipt:" + status]
    if status == "parsed":
        result.extend(describe(document))
    for label, relative in (("host-info", binding.APP), ("test-top-info", binding.TOP), ("test-nested-info", binding.NESTED)):
        directory = products / relative
        if not directory.exists() and not directory.is_symlink():
            result.append(label + ":absent")
            continue
        try:
            path = binding.exact(products, relative + "/Info.plist")
        except (OSError, ValueError):
            result.append(label + ":noncanonical")
            continue
        parsed, info = plist_shape(path, 65536)
        result.append(label + ":" + (
            ("dictionary" if isinstance(info, dict) else "not-dictionary") if parsed == "parsed" else parsed))
    return result


def diagnose(work, xc, original):
    folder = work / "independent simulator consumer"
    build = work / "simulator build"
    # The original graph and source are unchanged. These constants only permit
    # compilation; they are not a CA, never loaded by XCTest and never bound.
    copy = prepare(folder, xc, b"\0" * 256, (1, 2))
    udid = run(["xcrun", "simctl", "create", "MadLinkWSSPreview", "com.apple.CoreSimulator.SimDeviceType.iPhone-17",
                "com.apple.CoreSimulator.SimRuntime.iOS-26-2"], "sim-create", capture=True, timeout=120).strip()
    check(re.fullmatch(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", udid), "simulator-uuid")
    try:
        common = ["-project", "Preview.xcodeproj", "-scheme", "Preview", "-configuration", "Debug",
                  "-destination", "platform=iOS Simulator,id=" + udid, "-derivedDataPath", build, "ARCHS=arm64",
                  "ONLY_ACTIVE_ARCH=YES", "-parallel-testing-enabled", "NO", "CODE_SIGNING_ALLOWED=YES",
                  "CODE_SIGN_IDENTITY=-", "CODE_SIGNING_REQUIRED=NO", "ENABLE_DEBUG_DYLIB=NO"]
        run(["xcodebuild", "build-for-testing", *common], "build-for-testing", cwd=folder, timeout=240)
        check(tracked.fingerprint(copy) == original, "simulator-package-mutation")
        for label in inspect(build / "Build/Products"):
            print(PREFIX + label, flush=True)
    finally:
        run(["xcrun", "simctl", "delete", udid], "sim-delete")
    print(PREFIX + "build-only-finished-no-runtime", flush=True)


def main():
    # Isolate the probe from the full WSS driver. Use its exact pinned real
    # archive producer; neither runtime callback nor the device app is used.
    tracked.device_link = lambda work, xc, original: None
    tracked.simulator_test = diagnose
    tracked.main()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("FAIL: wss-receipt-build-only") from None
