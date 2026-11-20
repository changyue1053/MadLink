"""Authorize only one stock Xcode-generated launch of the inspected XCTest."""
import hashlib
from pathlib import Path
import plistlib

CONFIG = "Debug-iphonesimulator"
APP = CONFIG + "/Demo.app"
HOST = APP + "/Demo"
TEST = "SmokeTests"
TEST_ID = "org.madlink.preview.SmokeTests"
APP_ID = "org.madlink.preview.Demo"
TOP = CONFIG + "/SmokeTests.xctest"
NESTED = APP + "/PlugIns/SmokeTests.xctest"
ROOT = "__TESTROOT__/"
PLATFORM = "__PLATFORMS__/iPhoneSimulator.platform/Developer"


def need(ok, code):
    if not ok:
        raise ValueError(code)


def exact(root, relative, directory=False):
    candidate = root / relative
    need(candidate.resolve(strict=True) == candidate and
         (candidate.is_dir() if directory else candidate.is_file()), "wss-receipt-path")
    return candidate


def load(path, max_bytes):
    with path.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    need(len(raw) <= max_bytes, "wss-receipt-size")
    document = plistlib.loads(raw)
    need(isinstance(document, dict), "wss-receipt-format")
    return document


def target(document):
    meta = document.get("__xctestrun_metadata__", {})
    need(isinstance(meta, dict) and set(meta) <= {"FormatVersion"} and
         type(meta.get("FormatVersion", 1)) is int, "wss-receipt-format")
    version = meta.get("FormatVersion", 1)
    root_keys = {"__xctestrun_metadata__", "CodeCoverageBuildableInfos"}
    need(document.get("CodeCoverageBuildableInfos", []) == [], "wss-receipt-coverage")
    if version == 1:
        need(set(document) - root_keys == {TEST}, "wss-receipt-target")
        item = document[TEST]
    elif version == 2:
        need(set(document) <= root_keys | {"TestPlan", "TestConfigurations"}, "wss-receipt-root")
        plan = document.get("TestPlan", {})
        need(isinstance(plan, dict) and set(plan) <= {"IsDefault", "Name"} and
             plan.get("IsDefault", True) is True and isinstance(plan.get("Name", ""), str),
             "wss-receipt-plan")
        configs = document.get("TestConfigurations")
        need(isinstance(configs, list) and len(configs) == 1 and isinstance(configs[0], dict),
             "wss-receipt-config")
        config = configs[0]
        need(set(config) <= {"Name", "IsEnabled", "TestTargets"} and
             config.get("IsEnabled", True) is True and isinstance(config.get("Name", ""), str),
             "wss-receipt-config")
        targets = config.get("TestTargets")
        need(isinstance(targets, list) and len(targets) == 1, "wss-receipt-target")
        item = targets[0]
    else:
        raise ValueError("wss-receipt-format")
    need(isinstance(item, dict) and item.get("BlueprintName", TEST if version == 1 else None) == TEST,
         "wss-receipt-target")
    return item


def bundle_path(document):
    item = target(document)
    false = {"IsUITestBundle", "UseDestinationArtifacts", "IsSkipped", "IsAppHostedTestBundleDisabled",
             "IsXCTRunnerHostedTestBundle", "UITargetAppMainThreadCheckerEnabled",
             "GatherLocalizableStringsData", "ParallelizationEnabled", "TreatMissingBaselinesAsFailures"}
    empty_lists = {"OnlyTestIdentifiers", "SkipTestIdentifiers", "CommandLineArguments",
                   "UITargetAppCommandLineArguments"}
    empty_strings = {"TestBundleDestinationRelativePath", "BaselinePath", "TestLanguage", "TestRegion"}
    # Known metadata may be present in a stock generated receipt. It may not
    # choose an alternate target, an alternate load path, or a subset of tests.
    scalar = {"BlueprintName", "TestHostPath", "TestBundlePath", "TestHostBundleIdentifier",
              "TestBundleIdentifier", "DependentProductPaths", "EnvironmentVariables",
              "TestingEnvironmentVariables", "UITargetAppEnvironmentVariables", "TestExecutionOrdering",
              "ProductModuleName", "IsAppHostedTestBundle", "SystemAttachmentLifetime", "UserAttachmentLifetime",
              "UITargetAppPath", "UITargetAppBundleIdentifier"}
    need(set(item) <= false | empty_lists | empty_strings | scalar and
         all(item.get(k, False) is False for k in false) and
         all(item.get(k, []) == [] for k in empty_lists) and
         all(item.get(k, "") == "" for k in empty_strings) and
         item.get("UITargetAppEnvironmentVariables", {}) == {} and
         item.get("TestExecutionOrdering", "") in ("", "alphabetical") and
         item.get("ProductModuleName", TEST) == TEST and item.get("IsAppHostedTestBundle", True) is True and
         all(item.get(k, "deleteOnSuccess") == "deleteOnSuccess"
             for k in ("SystemAttachmentLifetime", "UserAttachmentLifetime")) and
         item.get("UITargetAppPath", "") in ("", ROOT + APP) and
         item.get("UITargetAppBundleIdentifier", "") in ("", APP_ID),
         "wss-receipt-execution-override")
    need(item.get("TestHostPath") in (ROOT + APP, ROOT + HOST) and
         item.get("TestHostBundleIdentifier", APP_ID) == APP_ID, "wss-receipt-host")
    variants = {ROOT + TOP: TOP, ROOT + NESTED: NESTED, "__TESTHOST__/PlugIns/SmokeTests.xctest": NESTED}
    requested = item.get("TestBundlePath")
    need(isinstance(requested, str) and requested in variants and
         item.get("TestBundleIdentifier", TEST_ID) == TEST_ID, "wss-receipt-bundle")
    # Xcode can list its top-level build product as a dependency of the
    # installed nested test bundle. No other dependency path is authorized.
    known_paths = set(variants) | {ROOT + APP, ROOT + HOST}
    dependencies = item.get("DependentProductPaths", [])
    need(isinstance(dependencies, list) and
         all(isinstance(value, str) and value in known_paths for value in dependencies),
         "wss-receipt-dependencies")
    need(item.get("EnvironmentVariables", {}) in ({}, {"OS_ACTIVITY_DT_MODE": "YES"}), "wss-receipt-env")
    loader = {
        "DYLD_FRAMEWORK_PATH": {ROOT + CONFIG, ROOT + CONFIG + ":" + PLATFORM + "/Library/Frameworks"},
        "DYLD_LIBRARY_PATH": {ROOT + CONFIG, ROOT + CONFIG + ":" + PLATFORM + "/usr/lib"},
        "DYLD_INSERT_LIBRARIES": {PLATFORM + "/usr/lib/libXCTestBundleInject.dylib"},
        "XCInjectBundleInto": {ROOT + HOST, "__TESTHOST__/Demo"},
        "XCInjectBundle": {requested, "__TESTBUNDLE__"},
    }
    environment = item.get("TestingEnvironmentVariables", {})
    need(isinstance(environment, dict) and all(k in loader and isinstance(value, str) and value in loader[k]
                                              for k, value in environment.items()), "wss-receipt-loader")
    return variants[requested]


def select(products):
    products = Path(products)
    need(products.is_dir() and products.resolve(strict=True) == products, "wss-receipt-products")
    manifests = list(products.glob("*.xctestrun"))
    need(len(manifests) == 1, "wss-receipt-count")
    receipt = exact(products, manifests[0].name)
    bundle = bundle_path(load(receipt, 1024 * 1024))
    # Bind identities in both generated Info.plists, not just path suffixes.
    for location, name, identifier, mode in ((APP, "Demo", APP_ID, "APPL"), (bundle, TEST, TEST_ID, "BNDL")):
        info = load(exact(products, location + "/Info.plist"), 65536)
        need((info.get("CFBundleExecutable"), info.get("CFBundleIdentifier"), info.get("CFBundlePackageType"))
             == (name, identifier, mode), "wss-receipt-identity")
    return receipt, exact(products, HOST), exact(products, bundle + "/" + TEST)


def snapshot(folder, selected, fingerprint):
    receipt, host, test = selected
    hash_paths = {
        "receipt": receipt, "host-executable": host, "test-executable": test,
        "job-ca-include": exact(folder, "LoopbackJob.inc"),
    }
    result = {}
    for name, path in hash_paths.items():
        with path.open("rb") as stream:
            result[name] = hashlib.file_digest(stream, "sha256").digest()
    # Stronger than executable hashes alone: include embedded dylibs/resources
    # and the inspected source-generated project plus scheme.
    result["host-closure"] = fingerprint(host.parent)
    result["test-closure"] = fingerprint(test.parent)
    result["project"] = fingerprint(exact(folder, "Preview.xcodeproj", directory=True))
    return result
