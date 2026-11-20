"""Separate stock-Xcode archived, device-link and simulator XCTest qualification."""
import hashlib
import json
from pathlib import Path
import platform
import plistlib
import re
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.append(str(ROOT / "ios"))
from project import generate
from diagnostics import run, STAGES
from sdk_package import build_package

STAGES.update({"sdk-pin", "archive-inspect", "device-build", "device-inspect", "sim-inspect", "test-cases"})
V1 = {"_ml_create_v1", "_ml_connect_v1", "_ml_send_v1", "_ml_tick_v1",
      "_ml_cancel_v1", "_ml_close_v1", "_ml_next_event_v1", "_ml_destroy_v1"}
TRACKED = {"_ml_create_tracked_v1", "_ml_send_tracked_v1", "_ml_next_completion_v1"}
TESTS = {"MadLinkTests/testSyntheticLifecycle", "MadLinkSessionTests/testInstalledSessionRecovery32Cycles",
         "MadLinkTrackedTests/testInstalledTrackedCompletions"}
LEGACY_BLOBS = {
    "ios/App.mm": "383c50ba2e8275740742cebe8c6735432181818d",
    "ios/Smoke.mm": "afc4e2d79320e446e65533245042d6573335522d",
    "ios/Tests.mm": "74f57eafd2a3b6932fdb7ec60eb225356b1c3ddb",
    "ios/sdk_package.py": "7ebfc562a862a790b7566c04a203f8a162cfaa81",
    "ios-tracked-preview/project.py": "e8020fd3275a9b7eb81d544dda8c6de5a1c60de3",
    "ios-tracked-preview/SessionTests.mm": "e129bb4779aae8556480a8ac0a6b101544be8d95",
    "ios-tracked-preview/SessionLifecycle.inc": "d6472026c0db13ec5a0c5c0e535b8ee7befc4c84",
}


class Failure(Exception):
    pass


def check(condition, label):
    if not condition:
        raise Failure(label)


def verify_legacy_inputs():
    for relative, expected in LEGACY_BLOBS.items():
        data = (ROOT / relative).read_bytes()
        oid = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        check(oid == expected, "legacy-input")


def contained(base, relative):
    p = base / relative
    check(not p.is_symlink() and p.is_file() and p.resolve() == p.absolute() and
          p.resolve().is_relative_to(base.resolve()), "artifact-containment")
    return p


def fingerprint(root):
    out = {}
    for path in sorted(root.rglob("*")):
        check(not path.is_symlink(), "package-symlink")
        if not path.is_dir():
            check(path.is_file(), "package-entry-type")
            with path.open("rb") as f:
                out[path.relative_to(root)] = hashlib.file_digest(f, "sha256").digest()
    return out


def symbol_gate(text, *, exact=False):
    seen = re.findall(r"(?m)^\s*[0-9a-fA-F]+[ \t]+[Tt][ \t]+(_ml_[a-z0-9_]+)[ \t]*$", text)
    required = V1 | TRACKED if exact else TRACKED
    check(all(seen.count(name) == 1 for name in required), "tracked-symbols")
    if exact:
        check(set(seen) == required, "archive-abi-symbol-set")


def arch(path, stage):
    check(run(["xcrun","lipo","-archs",path],stage,capture=True,timeout=45).split()==["arm64"],
          "binary-arm64")


def platform_gate(text, simulator):
    found = re.findall(r"(?m)^\s*platform\s+(\w+)\s*$", text)
    good = {"IOSSIMULATOR","7"} if simulator else {"IOS","2"}
    check(found and all(x in good for x in found), "binary-target-platform")


def inspect_package(xc):
    entries=plistlib.loads(contained(xc,"Info.plist").read_bytes())["AvailableLibraries"]
    check(len(entries)==2, "xc-slice-count")
    slices=set()
    for entry in entries:
        variant=entry.get("SupportedPlatformVariant","")
        paired={"":"ios-arm64","simulator":"ios-arm64-simulator"}
        check(variant in paired and variant not in slices and
              entry.get("SupportedPlatform")=="ios" and entry.get("LibraryPath")=="MadLink.framework" and
              entry.get("LibraryIdentifier")==paired[variant] and entry.get("SupportedArchitectures")==["arm64"],
              "xc-slice-identity")
        slices.add(variant)
        framework=xc / paired[variant] / "MadLink.framework"
        head=contained(framework,"Headers/madlink_c.h")
        check(head.read_bytes()==(ROOT/"include/madlink_c.h").read_bytes(), "xc-public-header")
        check(not (framework/"Headers/madlink.hpp").exists(), "xc-private-header")
        binary=contained(framework,"MadLink")
        with binary.open("rb") as f:
            check(f.read(8)==b"!<arch>\n", "xc-static-artifact")
        arch(binary,"archive-inspect")
        symbol_gate(run(["xcrun","nm","-gU",binary],"archive-inspect",capture=True,timeout=45),exact=True)


def check_results(summary, cases):
    for key, want in (("totalTestCount",3),("passedTests",3),("failedTests",0),("skippedTests",0)):
        check(type(summary.get(key)) is int and summary[key]==want, "test-counts")
    check(summary.get("testStatus","Passed")=="Passed" and summary.get("expectedFailures",0)==0, "test-status")
    seen=set()
    def walk(nodes):
        check(isinstance(nodes,list), "test-tree")
        for node in nodes:
            check(isinstance(node,dict) and node.get("result","Passed")=="Passed", "test-status")
            if node.get("nodeType")=="Test Case":
                name=node.get("nodeIdentifier")
                check(isinstance(name,str), "test-name")
                name=name.removesuffix("()")
                check(name in TESTS and name not in seen and node.get("result")=="Passed", "test-name")
                seen.add(name)
            walk(node.get("children",[]))
    walk(cases["testNodes"])
    check(seen==TESTS, "test-name")


def read_xctest_results(result):
    return tuple(
        json.loads(run(["xcrun","xcresulttool","get","test-results",kind,"--path",str(result)],
                       stage,capture=True,timeout=60))
        for kind, stage in (("summary","test-summary"),("tests","test-cases"))
    )


def prepare_consumer(folder, xc, simulator):
    folder.mkdir()
    for name in ("App.mm","Smoke.mm","Tests.mm"):
        actual = HERE/"DeviceSmoke.mm" if not simulator and name=="Smoke.mm" else ROOT/"ios"/name
        shutil.copyfile(actual,folder/name)
    shutil.copytree(xc,folder/"MadLink.xcframework")
    tests=()
    if simulator:
        for name in ("SessionTests.mm","SessionLifecycle.inc","TrackedTests.mm","TrackedAcceptance.c"):
            shutil.copyfile(HERE/name,folder/name)
        (folder/"SessionLifecycle.c").write_text(
            '#define MADLINK_SESSION_XCTEST 1\n#define main madlinkSessionAcceptance\n'
            '#include "SessionLifecycle.inc"\n')
        (folder/"TrackedFixture.c").write_text(
            '#define MADLINK_TRACKED_XCTEST 1\n#include "TrackedAcceptance.c"\n')
        tests=("SessionTests.mm","SessionLifecycle.c","TrackedTests.mm","TrackedFixture.c")
    generate(folder,test_sources=tests)
    return folder/"MadLink.xcframework"


def inspect_product(path, simulator, tracked):
    stage="sim-inspect" if simulator else "device-inspect"
    arch(path,stage)
    platform_gate(run(["xcrun","vtool","-show-build",path],stage,capture=True,timeout=45),simulator)
    if tracked:
        symbol_gate(run(["xcrun","nm","-U",path],stage,capture=True,timeout=45))


def device_link(work, xc, original):
    folder=work/"independent device consumer"
    local=prepare_consumer(folder,xc,False)
    build=work/"device build"
    run(["xcodebuild","build","-project","Preview.xcodeproj","-scheme","Preview","-configuration","Debug",
         "-destination","generic/platform=iOS","-derivedDataPath",build,"ARCHS=arm64","ONLY_ACTIVE_ARCH=YES",
         "CODE_SIGNING_ALLOWED=NO","ENABLE_DEBUG_DYLIB=NO"],"device-build",cwd=folder)
    app=contained(build,"Build/Products/Debug-iphoneos/Demo.app/Demo")
    inspect_product(app,False,True)
    check(fingerprint(local)==original,"device-package-mutation")
    print("PASS: unsigned ARM64 iOS device app linked tracked ABI from relocated package (not executed)")


def simulator_test(work, xc, original):
    folder=work/"independent simulator consumer"
    local=prepare_consumer(folder,xc,True)
    build=work/"simulator build"
    result=work/"result.xcresult"
    udid=run(["xcrun","simctl","create","MadLinkTrackedPreview","com.apple.CoreSimulator.SimDeviceType.iPhone-17",
              "com.apple.CoreSimulator.SimRuntime.iOS-26-2"],"sim-create",capture=True,timeout=60).strip()
    check(re.fullmatch(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}",udid), "simulator-uuid")
    try:
        run(["xcrun","simctl","boot",udid],"sim-boot")
        run(["xcrun","simctl","bootstatus",udid,"-b"],"sim-ready")
        common=["-project","Preview.xcodeproj","-scheme","Preview","-configuration","Debug",
                "-destination","platform=iOS Simulator,id="+udid,"-derivedDataPath",build,"ARCHS=arm64",
                "ONLY_ACTIVE_ARCH=YES","-parallel-testing-enabled","NO","CODE_SIGNING_ALLOWED=YES",
                "CODE_SIGN_IDENTITY=-","CODE_SIGNING_REQUIRED=NO","ENABLE_DEBUG_DYLIB=NO"]
        run(["xcodebuild","build-for-testing",*common],"build-for-testing",cwd=folder)
        products=build/"Build/Products"
        sim=products/"Debug-iphonesimulator"
        host=contained(sim,"Demo.app/Demo")
        inspect_product(host,True,False)
        tests=[]
        for path in ("SmokeTests.xctest/SmokeTests","Demo.app/PlugIns/SmokeTests.xctest/SmokeTests"):
            if (sim/path).exists():
                test=contained(sim,path)
                inspect_product(test,True,True)
                tests.append(test)
        check(tests, "simulator-test-product")
        snapshot={p:hashlib.sha256(p.read_bytes()).digest() for p in (host,*tests)}
        run(["xcodebuild","test-without-building",*common,"-resultBundlePath",result],"test-without-building",cwd=folder)
        check(all(hashlib.sha256(p.read_bytes()).digest()==d for p,d in snapshot.items()),"simulator-product-mutation")
        check_results(*read_xctest_results(result))
        check(fingerprint(local)==original,"simulator-package-mutation")
    finally:
        run(["xcrun","simctl","delete",udid],"sim-delete")
    print("PASS: ARM64 iOS Simulator exact legacy lifecycle, 32-cycle recovery and tracked-result XCTest")


def main():
    verify_legacy_inputs()
    check(platform.system()=="Darwin" and platform.machine()=="arm64","stock-arm64-macos")
    version=run(["xcodebuild","-version"],"version",capture=True,timeout=30)
    check(version.splitlines()==["Xcode 26.2","Build version 17C52"],"xcode-pin")
    for sdk in ("iphoneos","iphonesimulator"):
        check(run(["xcrun","--sdk",sdk,"--show-sdk-version"],"sdk-pin",capture=True,timeout=30).strip()=="26.2",
              "xcode-sdk-pin")
    with tempfile.TemporaryDirectory(prefix="madlink-ios-tracked-") as base:
        work=Path(base).resolve()
        source=work/"disposable checkout"
        source.mkdir()
        for name in ("include","src"):
            shutil.copytree(ROOT/name,source/name)
        for name in ("LICENSE","THIRD_PARTY_NOTICES.md"):
            shutil.copyfile(ROOT/name,source/name)
        _, package=build_package(source)
        container=work/"relocated package"
        container.mkdir()
        xc=container/"MadLink.xcframework"
        shutil.move(package,xc)
        shutil.rmtree(source)
        check(not source.exists(),"producer-removal")
        original=fingerprint(xc)
        inspect_package(xc)
        print("PASS: relocated ARM64 device and simulator static XCFramework slice ABI symbols")
        device_link(work,xc,original)
        simulator_test(work,xc,original)
        check(fingerprint(xc)==original,"package-mutation")


if __name__=="__main__":
    try:
        main()
    except Failure as error:
        raise SystemExit("FAIL: "+str(error)) from None
    except Exception:
        raise SystemExit("FAIL: qualification infrastructure") from None
