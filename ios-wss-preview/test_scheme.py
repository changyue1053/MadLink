from pathlib import Path
import plistlib
import shutil
import tempfile
import unittest
from unittest.mock import patch

import binding
import scheme_authority as authority
import scheme_verify
from verify import prepare, tracked


class SchemeTests(unittest.TestCase):
    def shell(self, root):
        fixture = root / "relocated"
        fixture.mkdir()
        folder = root / "scheme consumer"
        prepare(folder, fixture, bytes(256), (1, 2))
        authority.close_launch_inheritance(folder)
        return folder

    def test_ambient_injection_has_no_route(self):
        poison = {key: "/attacker" for key in (
            "PATH", "DEVELOPER_DIR", "XCODE_XCCONFIG_FILE", "DYLD_INSERT_LIBRARIES", "LD_PRELOAD",
            "SIMCTL_CHILD_DYLD_INSERT_LIBRARIES", "XCInjectBundle", "XCTestConfigurationFilePath",
            "XCTEST_CONFIGURATION_FILE_PATH", "HOME", "TMPDIR", "HTTP_PROXY", "TOOLCHAINS")}
        with patch.dict("os.environ", poison, clear=True):
            self.assertEqual(authority.clean_environment("/runner", "/owned"), {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "DEVELOPER_DIR": authority.DEVELOPER,
                "HOME": "/runner", "TMPDIR": "/owned", "LANG": "C", "LC_ALL": "C",
            })
        self.assertEqual(authority.TOOLS["xcodebuild"], authority.DEVELOPER + "/usr/bin/xcodebuild")
        self.assertEqual(authority.TOOLS["codesign"], "/usr/bin/codesign")
        self.assertEqual(authority.TOOLS["xcrun"], "/usr/bin/xcrun")

    def test_authored_graph_cannot_gain_hooks_or_inputs(self):
        with tempfile.TemporaryDirectory() as work:
            folder = self.shell(Path(work).resolve())
            expected = authority.exact_graph(folder)
            for unexpected in ("Extra.xcworkspace", "Tests.xctestplan", "Injected.xcconfig",
                               "Preview.xcodeproj/xcshareddata/xcschemes/Second.xcscheme",
                               "Preview.xcodeproj/Plugin"):
                p = folder / unexpected
                p.write_text("extra")
                with self.assertRaises(ValueError):
                    authority.exact_graph(folder)
                p.unlink()
            for name, injection in (
                ("project.pbxproj", "PBXShellScriptBuildPhase XCRemoteSwiftPackageReference"),
                ("project.pbxproj", "baseConfigurationReference OTHER_LDFLAGS"),
                ("xcshareddata/xcschemes/Preview.xcscheme", "PreActions CommandLineArguments"),
                ("xcshareddata/xcschemes/Preview.xcscheme", "EnvironmentVariables TestPlans SkippedTests"),
                ("xcshareddata/xcschemes/Preview.xcscheme", "enableAddressSanitizer=YES"),
            ):
                path = folder / "Preview.xcodeproj" / name
                previous = path.read_bytes()
                path.write_bytes(previous + injection.encode())
                with self.assertRaises(ValueError):
                    authority.exact_graph(folder)
                path.write_bytes(previous)
            self.assertEqual(authority.exact_graph(folder), expected)

    def test_build_graph_has_explicitly_disabled_launch_inheritance(self):
        with tempfile.TemporaryDirectory() as work:
            folder = self.shell(Path(work).resolve())
            scheme = folder / authority.PROJECT / authority.SCHEME
            self.assertIn(b'shouldUseLaunchSchemeArgsEnv="NO"', scheme.read_bytes())
            self.assertNotIn(b'shouldUseLaunchSchemeArgsEnv="YES"', scheme.read_bytes())
            with self.assertRaises(ValueError):
                authority.close_launch_inheritance(folder)

    def test_quarantine_moves_unread_sidecars_and_restores_authoritative_bytes(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work).resolve()
            folder = self.shell(root)
            build = root / "build"
            build.mkdir()
            safety = root / "private evidence"
            safety.mkdir(mode=0o700)
            quarantine = safety / "stock-build-project.evidence"
            original = authority.exact_graph(folder)
            project = folder / authority.PROJECT
            outside = root / "never-read"
            outside.write_bytes(b"untrusted contents")
            # The foreign symlink and workspace are retained in tomb only;
            # reading old recursive graph would fail before reaching restore.
            sidecar = project / "project.xcworkspace"
            sidecar.mkdir()
            (sidecar / "PreActions").symlink_to(outside)
            (project / authority.SCHEME).chmod(0o755)
            proc_inode = project.stat().st_ino
            authority.quarantine_project(folder, build, quarantine, original)
            self.assertEqual(authority.exact_graph(folder), original)
            self.assertEqual(quarantine.stat().st_ino, proc_inode)
            self.assertNotEqual(project.stat().st_ino, proc_inode)
            self.assertTrue((quarantine / "project.xcworkspace/PreActions").is_symlink())
            self.assertFalse((project / "project.xcworkspace").exists())
            self.assertEqual((project / authority.SCHEME).stat().st_mode & 0o777, 0o600)
            (project / "project.xcworkspace").mkdir()
            with self.assertRaises(ValueError):
                authority.exact_graph(folder)  # even a recreated sidecar rejects post-launch

    def test_changed_authored_input_or_unsafe_path_is_never_moved(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work).resolve()
            folder = self.shell(root)
            build = root / "build"
            build.mkdir(mode=0o700)
            safety = root / "evidence"
            safety.mkdir(mode=0o700)
            quarantine = safety / "quarantined"
            original = authority.exact_graph(folder)
            project = folder / authority.PROJECT
            scheme = project / authority.SCHEME
            old = scheme.read_bytes()
            scheme.write_bytes(old + b"<EnvironmentVariables/>")
            with self.assertRaises(ValueError):
                authority.quarantine_project(folder, build, quarantine, original)
            scheme.write_bytes(old)
            extra = folder / "Foreign.mm"
            extra.touch()
            with self.assertRaises(ValueError):
                authority.quarantine_project(folder, build, quarantine, original)
            extra.unlink()
            with self.assertRaises(ValueError):
                authority.quarantine_project(folder, build, build / "within-resolver", original)
            alias = safety / "guard-alias"
            alias.symlink_to(safety)
            with self.assertRaises(ValueError):
                authority.quarantine_project(folder, build, alias / "outside", original)
            moved = root / "outside-scheme"
            scheme.rename(moved)
            scheme.symlink_to(moved)
            with self.assertRaises(ValueError):
                authority.quarantine_project(folder, build, quarantine, original)
            self.assertFalse(quarantine.exists())

    @staticmethod
    def stock_receipt():
        return {"__xctestrun_metadata__": {"FormatVersion": 1, "OpaqueMetadata": {"not": "executed"}},
                binding.TEST: {
                    "TestHostPath": binding.ROOT + binding.APP,
                    "TestBundlePath": "__TESTHOST__/PlugIns/SmokeTests.xctest",
                    "TestingEnvironmentVariables": {"DYLD_FRAMEWORK_PATH": binding.ROOT + binding.CONFIG,
                                                    "StockGeneratedMarker": "value"},
                }}

    def test_one_fresh_receipt_is_quarantined_and_not_launch_authority(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work).resolve()
            launch = root / "Products"
            launch.mkdir()
            generated = launch / "stock.xctestrun"
            generated.write_bytes(plistlib.dumps(self.stock_receipt()))
            raw = generated.read_bytes()
            quarantine = root / "evidence.plist"
            other = launch / "other.xctestrun"
            other.write_bytes(raw)
            with self.assertRaises(ValueError):
                authority.receipt(launch, quarantine)
            other.unlink()
            self.assertEqual(authority.receipt(launch, quarantine), (binding.NESTED, authority.digest(quarantine)))
            self.assertEqual(quarantine.read_bytes(), raw)
            self.assertEqual(list(launch.iterdir()), [])
            uuid = "22222222-3333-4444-5555-666666666666"
            argv = scheme_verify.arguments(uuid, root / "derived", launch)
            self.assertNotIn("-xctestrun", argv)
            self.assertNotIn(str(quarantine), argv)
            self.assertIn("SYMROOT=" + str(launch), argv)
            self.assertEqual(argv[:6], ["-project", "Preview.xcodeproj", "-scheme", "Preview", "-configuration", "Debug"])

    def test_receipt_external_or_override_does_not_authorize(self):
        for override in (
            {"TestHostPath": "/other.app"}, {"TestBundlePath": "__TESTROOT__/../a.xctest"},
            {"TestBundleIdentifier": "foreign.app"}, {"UseDestinationArtifacts": True},
            {"TestingEnvironmentVariables": {"DYLD_INSERT_LIBRARIES": "/other"}},
            {"TestingEnvironmentVariables": {"DYLD_DEFAULT_INJECT": "attacker"}},
            {"TestingEnvironmentVariables": {"XCTestGeneratedMarker": "/other"}},
            {"TestingEnvironmentVariables": {"SIMCTL_CHILD_ANY": "yes"}},
            {"EnvironmentVariables": {"PATH": "/other"}},
            {"SkipTestIdentifiers": ["other"]}, {"CommandLineArguments": ["--custom"]},
        ):
            doc = self.stock_receipt()
            doc[binding.TEST].update(override)
            with self.subTest(keys=tuple(override)), self.assertRaises(ValueError):
                authority.classify_receipt(doc)

    def test_product_identities_and_extra_dylib_or_runner_denied(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work).resolve()
            for location, executable, ident, mode in ((binding.APP, "Demo", binding.APP_ID, "APPL"),
                                                       (binding.NESTED, binding.TEST, binding.TEST_ID, "BNDL")):
                app = root / location
                app.mkdir(parents=True)
                (app / executable).write_bytes(b"mach-o fixture")
                (app / "_CodeSignature").mkdir()
                (app / "_CodeSignature/CodeResources").write_bytes(b"signature fixture")
                (app / "Info.plist").write_bytes(plistlib.dumps({
                    "CFBundleExecutable": executable, "CFBundleIdentifier": ident, "CFBundlePackageType": mode}))
            host, tests = authority.product_paths(root, binding.NESTED)
            self.assertEqual(host, root / binding.HOST)
            self.assertIn(binding.NESTED, tests)
            authority.sysroot_inventory(root, binding.NESTED, root / "unused-installed")
            for name in ("Injected.dylib", "Runner.app", "Alternative.xctest", "renamed-control", "Global.plist"):
                path = root / binding.CONFIG / name
                path.write_bytes(b"other")
                with self.assertRaises(ValueError):
                    authority.sysroot_inventory(root, binding.NESTED, root / "unused-installed")
                path.unlink()
            with tempfile.TemporaryDirectory() as install:
                prefix = Path(install).resolve()
                origin = prefix / "ios-arm64-simulator/MadLink.framework"
                origin.mkdir(parents=True)
                (origin / "MadLink").write_bytes(b"!<arch>\ninstalled static")
                staged = root / binding.CONFIG / "MadLink.framework"
                shutil.copytree(origin, staged)
                authority.sysroot_inventory(root, binding.NESTED, prefix)
                (staged / "MadLink").write_bytes(b"!<arch>\nnot installed contents")
                with self.assertRaises(ValueError):
                    authority.sysroot_inventory(root, binding.NESTED, prefix)
                shutil.rmtree(staged)
            pkg = root / binding.APP / "PkgInfo"
            pkg.write_bytes(b"APPL????")
            authority.sysroot_inventory(root, binding.NESTED, root / "unused-installed")
            pkg.write_bytes(b"APPL????hidden")
            with self.assertRaises(ValueError):
                authority.sysroot_inventory(root, binding.NESTED, root / "unused-installed")
            pkg.unlink()
            wrong = root / binding.NESTED / "Info.plist"
            value = plistlib.loads(wrong.read_bytes())
            wrong.write_bytes(plistlib.dumps({**value, "LSEnvironment": {"DYLD_INSERT_LIBRARIES": "/other"}}))
            with self.assertRaises(ValueError):
                authority.product_paths(root, binding.NESTED)
            wrong.write_bytes(plistlib.dumps({"CFBundleExecutable": binding.TEST}))
            with self.assertRaises(ValueError):
                authority.product_paths(root, binding.NESTED)

    def test_snapshot_detects_receipt_ca_or_product_change(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work).resolve()
            folder = self.shell(root)
            products = root / "Products"
            products.mkdir()
            evidence = root / "evidence.plist"
            evidence.write_bytes(plistlib.dumps(self.stock_receipt()))
            for location, name, ident, mode in ((binding.APP, "Demo", binding.APP_ID, "APPL"),
                                                (binding.NESTED, binding.TEST, binding.TEST_ID, "BNDL")):
                product = products / location
                product.mkdir(parents=True, exist_ok=True)
                (product / name).write_bytes(b"signed fixture bytes")
                (product / "_CodeSignature").mkdir()
                (product / "_CodeSignature/CodeResources").write_bytes(b"signature fixture")
                (product / "Info.plist").write_bytes(plistlib.dumps({
                    "CFBundleExecutable": name, "CFBundleIdentifier": ident, "CFBundlePackageType": mode}))
            evaluate = lambda: authority.snapshot(folder, products, binding.NESTED, evidence, tracked.fingerprint)
            initial = evaluate()
            for path in (folder / "LoopbackJob.inc", evidence, products / binding.HOST,
                         products / binding.NESTED / binding.TEST):
                saved = path.read_bytes()
                path.write_bytes(saved + b"mutation")
                self.assertNotEqual(evaluate(), initial)
                path.write_bytes(saved)
            binary = products / binding.HOST
            old_binary = root / "same-byte-other-inode"
            original_contents = binary.read_bytes()
            binary.rename(old_binary)
            binary.write_bytes(original_contents)
            self.assertNotEqual(evaluate(), initial)
            (products / "unexpected.xctestrun").touch()
            with self.assertRaises(ValueError):
                evaluate()

    def test_dependency_and_rpath_policy(self):
        line = "  @rpath/XCTest.framework/XCTest (compatibility version 1.0.0, current version 2.0.0)"
        self.assertEqual(authority.dependencies("binary:\n" + line), {"@rpath/XCTest.framework/XCTest"})
        with self.assertRaises(ValueError):
            authority.dependencies("binary:\n" + line.replace("@rpath/XCTest.framework/XCTest", "@rpath/other.dylib"))
        for path in ("@executable_path/Frameworks", "/elsewhere"):
            text = f"          cmd LC_RPATH\n      cmdsize 64\n         path {path} (offset 12)"
            if path == "/elsewhere":
                with self.assertRaises(ValueError):
                    authority.rpaths(text)
            else:
                authority.rpaths(text)

    def test_pinned_stock_signature_identity_and_resolution(self):
        with tempfile.TemporaryDirectory() as work:
            app = Path(work).resolve() / "Xcode_26.2.app"
            info = app / "Contents/Info.plist"
            info.parent.mkdir(parents=True)
            info.write_bytes(plistlib.dumps({"CFBundleIdentifier": authority.XCODE_ID}))
            tool = str(app / "Contents/Developer/usr/bin/xcodebuild")
            req = 'designated => identifier "com.apple.dt.Xcode" and anchor apple'
            version = "Xcode 26.2\nBuild version 17C52"
            authority.stock_identity(app, tool, req, version)
            for resolution, identity, build in (
                ("/usr/bin/xcodebuild", req, version),
                (tool, req.replace("dt.Xcode", "dt.XcodeOther"), version),
                (tool, req, version.replace("17C52", "17C53")),
            ):
                with self.assertRaises(ValueError):
                    authority.stock_identity(app, resolution, identity, build)
            info.write_bytes(plistlib.dumps({"CFBundleIdentifier": "other"}))
            with self.assertRaises(ValueError):
                authority.stock_identity(app, tool, req, version)

    def test_signature_verification_is_mandatory_before_using_resolved_tools(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work).resolve()
            app = root / "Xcode_26.2.app"
            xcode = app / "Contents/Developer/usr/bin/xcodebuild"
            xcode.parent.mkdir(parents=True)
            xcode.touch()
            tools = {"xcodebuild": str(xcode), "xcrun": str(root / "xcrun"), "codesign": str(root / "codesign")}
            for name in ("xcrun", "codesign"):
                Path(tools[name]).touch()
            with patch.object(authority, "XCODE_APP", str(app)), patch.object(authority, "TOOLS", tools), \
                 patch.object(scheme_verify, "stock", side_effect=RuntimeError("signature rejected")) as invoke:
                with self.assertRaises(RuntimeError):
                    scheme_verify.stock_preflight()
                invoke.assert_called_once_with("codesign", ["--verify", "--strict",
                    '-R=identifier "com.apple.dt.Xcode" and anchor apple', app], "version", timeout=90)
            alias = root / "alias.app"
            alias.symlink_to(app)
            with patch.object(authority, "XCODE_APP", str(alias)), patch.object(scheme_verify, "stock") as invoke:
                with self.assertRaises(tracked.Failure):
                    scheme_verify.stock_preflight()
                invoke.assert_not_called()

    def test_macho_payload_loader_controls_reject(self):
        prefix = "Load command 0\n          cmd "
        for name in ("0x81", "LC_DYLD_ENVIRONMENT", "LC_DYLD_UNREVIEWED", "LC_REEXPORT_DYLIB", "LC_LOAD_UPWARD_DYLIB",
                     "LC_LAZY_LOAD_DYLIB", "LC_LINKER_OPTION", "LC_ID_DYLINKER"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                authority.loader_controls(prefix + name + "\n      cmdsize 32\n         name synthetic (offset 12)")
        for resource, ok in (("/usr/lib/dyld", True), ("/foreign/dyld", False)):
            text = prefix + "LC_LOAD_DYLINKER\n      cmdsize 32\n         name " + resource + " (offset 12)"
            if ok:
                authority.loader_controls(text)
            else:
                with self.assertRaises(ValueError):
                    authority.loader_controls(text)
        authority.loader_controls(prefix + "LC_DYLD_CHAINED_FIXUPS")
        with self.assertRaises(ValueError):
            authority.loader_controls(prefix + "LC_LOAD_WEAK_DYLIB\n      cmdsize 32\n         name /foreign/lib (offset 12)")


if __name__ == "__main__":
    unittest.main()
