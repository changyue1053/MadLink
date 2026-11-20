"""Portable gate and real host-side peer fixtures, not Apple execution proof."""
from pathlib import Path
import plistlib
import socket
import ssl
import tempfile
import time
import unittest

from peer import REPLY, REQUEST, exact, peers
import binding
import verify


class StructuralTests(unittest.TestCase):
    def summary(self):
        return {"totalTestCount": 4, "passedTests": 4, "failedTests": 0, "skippedTests": 0}

    def cases(self, names):
        return {"testNodes": [{"nodeType": "Test Case", "nodeIdentifier": name + "()", "result": "Passed"}
                              for name in names]}

    def test_exact_four_cases(self):
        prior = sorted(verify.tracked.TESTS)
        verify.exact_results(self.summary(), self.cases([*prior, verify.NAME]))
        for names in ([*prior], [*prior, prior[0]], [*prior, "different"]):
            with self.assertRaises(verify.tracked.Failure):
                verify.exact_results(self.summary(), self.cases(names))

    def test_failed_or_skipped_never_passes(self):
        prior = sorted(verify.tracked.TESTS)
        for key in ("failedTests", "skippedTests", "expectedFailures"):
            summary = self.summary()
            summary[key] = 1
            with self.assertRaises(verify.tracked.Failure):
                verify.exact_results(summary, self.cases([*prior, verify.NAME]))

    def test_public_inputs_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verify.write_fixture(root, b"\xAB" * 256, (30100, 30200))
            header = (root / "LoopbackJob.inc").read_text()
            self.assertIn("kValidPort=30100, kWrongPort=30200", header)
            self.assertEqual(header.count("0xab"), 256)
            for cert, ports in ((b"\xAB", (101, 102)), (b"\xAB" * 256, (70, 70)),
                                (b"\xAB" * 256, (0, 102)), (b"\xAB" * 256, (True, 102))):
                with self.assertRaises(verify.tracked.Failure):
                    verify.write_fixture(root, cert, ports)


    def test_generated_consumer_keeps_old_sources_and_single_wss_lane(self):
        with tempfile.TemporaryDirectory(prefix="wss layout ") as directory:
            root = Path(directory)
            xc = root / "relocated package" / "MadLink.xcframework"
            xc.mkdir(parents=True)
            (xc / "placeholder-not-a-package").write_text("structure only")
            consumer = root / "consumer"
            installed = verify.prepare(consumer, xc, b"\xAD" * 256, (30100, 30200))
            self.assertEqual(installed, consumer / "MadLink.xcframework")
            project = (consumer / "Preview.xcodeproj" / "project.pbxproj").read_text()
            for name in ("Tests.mm", "SessionTests.mm", "SessionLifecycle.c", "TrackedTests.mm",
                         "TrackedFixture.c", "WssTests.mm"):
                self.assertTrue((consumer / name).is_file())
                self.assertEqual(project.count(f'"path" = "{name}";'), 1)
            for framework in ("Network", "Security"):
                self.assertEqual(project.count(f'"-framework","{framework}"'), 2)  # Debug/Release XCTest
            self.assertNotIn("NSAppTransportSecurity", project)
            self.assertNotIn("NSAllowsArbitraryLoads", project)
            self.assertNotIn("root.key", project)


class ReceiptTests(unittest.TestCase):
    @staticmethod
    def target(nested):
        return {
            "BlueprintName": binding.TEST,
            "TestHostPath": binding.ROOT + (binding.APP if nested else binding.HOST),
            "TestBundlePath": "__TESTHOST__/PlugIns/SmokeTests.xctest" if nested else binding.ROOT + binding.TOP,
            "TestHostBundleIdentifier": binding.APP_ID,
            "TestBundleIdentifier": binding.TEST_ID,
            "UITargetAppPath": binding.ROOT + binding.APP,
            "SystemAttachmentLifetime": "deleteOnSuccess",
            "UserAttachmentLifetime": "deleteOnSuccess",
            "ParallelizationEnabled": False,
            "DependentProductPaths": [binding.ROOT + binding.TOP, binding.ROOT + binding.APP],
            "TestingEnvironmentVariables": {
                "DYLD_FRAMEWORK_PATH": binding.ROOT + binding.CONFIG,
                "DYLD_LIBRARY_PATH": binding.ROOT + binding.CONFIG + ":" + binding.PLATFORM + "/usr/lib",
            },
        }

    @staticmethod
    def wrap(target, v2):
        if not v2:
            return {binding.TEST: target}
        return {"__xctestrun_metadata__": {"FormatVersion": 2},
                "TestPlan": {"Name": "Preview", "IsDefault": True},
                "TestConfigurations": [{"Name": "Debug", "IsEnabled": True, "TestTargets": [target]}]}

    def fixture(self, root, nested):
        products, folder = root / "Products", root / "Consumer"
        products.mkdir()
        folder.mkdir()
        receipt = products / "Preview_iphonesimulator26.2-arm64.xctestrun"
        receipt.write_bytes(plistlib.dumps(self.wrap(self.target(nested), nested)))
        bundle = binding.NESTED if nested else binding.TOP
        for relative, name, identifier, package_type in (
            (binding.APP, "Demo", binding.APP_ID, "APPL"),
            (bundle, binding.TEST, binding.TEST_ID, "BNDL"),
        ):
            (products / relative).mkdir(parents=True, exist_ok=True)
            (products / relative / name).write_bytes(b"binary fixture")
            (products / relative / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleExecutable": name, "CFBundleIdentifier": identifier, "CFBundlePackageType": package_type,
            }))
        (folder / "Preview.xcodeproj").mkdir()
        (folder / "Preview.xcodeproj/project.pbxproj").write_bytes(b"generated project")
        (folder / "LoopbackJob.inc").write_bytes(b"public CA include")
        return products, folder, receipt, bundle

    def test_exact_supported_receipts_and_fingerprint(self):
        for nested in (False, True):
            with self.subTest(nested=nested), tempfile.TemporaryDirectory() as work:
                products, folder, receipt, bundle = self.fixture(Path(work).resolve(), nested)
                picked = binding.select(products)
                self.assertEqual(picked, (receipt, products / binding.HOST, products / bundle / binding.TEST))
                fingerprint = verify.tracked.fingerprint
                before = binding.snapshot(folder, picked, fingerprint)
                mutations = (receipt, picked[1], picked[2], folder / "LoopbackJob.inc",
                             folder / "Preview.xcodeproj/project.pbxproj")
                for path in mutations:
                    old = path.read_bytes()
                    path.write_bytes(old + b"delta")
                    self.assertNotEqual(binding.snapshot(folder, picked, fingerprint), before)
                    path.write_bytes(old)

    def test_path_launch_or_selection_overrides_deny(self):
        legitimate = self.target(True)
        for override in (
            {"TestHostPath": "__TESTROOT__/Other.app"},
            {"TestBundlePath": "__TESTROOT__/../SmokeTests.xctest"},
            {"TestBundleIdentifier": "other"}, {"TestHostBundleIdentifier": "other"},
            {"DependentProductPaths": ["/tmp/external"]},
            {"TestingEnvironmentVariables": {"DYLD_INSERT_LIBRARIES": "/tmp/injected"}},
            {"EnvironmentVariables": {"PATH": "/tmp/bin"}},
            {"CommandLineArguments": ["other"]}, {"OnlyTestIdentifiers": ["one"]},
            {"SkipTestIdentifiers": ["one"]}, {"UseDestinationArtifacts": True},
            {"ParallelizationEnabled": True}, {"UITargetAppPath": "__TESTROOT__/Other.app"},
            {"SystemAttachmentLifetime": "keepAlways"},
            {"UnknownLaunchFlag": "unreviewed"},
        ):
            with self.subTest(override=tuple(override)), self.assertRaises(ValueError):
                binding.bundle_path(self.wrap(legitimate | override, True))
        for level in ("root", "configuration"):
            document = self.wrap(legitimate, True)
            target = document if level == "root" else document["TestConfigurations"][0]
            target["EnvironmentVariables"] = {"PATH": "/tmp/bin"}
            with self.assertRaises(ValueError):
                binding.bundle_path(document)

    def test_duplicate_and_alias_receipts_or_binaries_deny(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work).resolve()
            products, _, receipt, bundle = self.fixture(root, True)
            clone = products / "other.xctestrun"
            clone.write_bytes(receipt.read_bytes())
            with self.assertRaises(ValueError):
                binding.select(products)
            clone.unlink()
            backup = root / "unalias.plist"
            receipt.rename(backup)
            receipt.symlink_to(backup)
            with self.assertRaises(ValueError):
                binding.select(products)
            receipt.unlink()
            backup.rename(receipt)
            executable = products / bundle / binding.TEST
            moved = root / "alternate"
            executable.rename(moved)
            executable.symlink_to(moved)
            with self.assertRaises(ValueError):
                binding.select(products)


class PeerTests(unittest.TestCase):
    def connect(self, context, port, hostname="127.0.0.1"):
        raw = socket.create_connection(("127.0.0.1", port), timeout=4)
        try:
            return context.wrap_socket(raw, server_hostname=hostname)
        except Exception:
            raw.close()
            raise

    def test_exact_signed_peer_and_wrong_san_rejection(self):
        with tempfile.TemporaryDirectory() as directory, peers(Path(directory)) as (ca, ports, start):
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(cadata=ca)
            jobs = start()
            with self.connect(context, ports[0]) as tls:
                tls.sendall(f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{ports[0]}\r\nUpgrade: websocket\r\n"
                            "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
                            "Sec-WebSocket-Key: AAAAAAAAAAAAAAAAAAAAAA==\r\n\r\n".encode("ascii"))
                deadline = time.monotonic() + 4
                response = bytearray()
                while not response.endswith(b"\r\n\r\n"):
                    self.assertLess(len(response), 512)
                    response.extend(exact(tls, 1, deadline))
                self.assertTrue(response.startswith(b"HTTP/1.1 101 "))
                mask = b"TEST"
                frame = bytes((0x82, 128 + len(REQUEST))) + mask
                tls.sendall(frame + bytes(value ^ mask[i % 4] for i, value in enumerate(REQUEST)))
                self.assertEqual(exact(tls, 2 + len(REPLY), deadline), bytes((0x82, len(REPLY))) + REPLY)
            with self.assertRaises(ssl.SSLCertVerificationError) as caught:
                self.connect(context, ports[1])
            self.assertEqual(caught.exception.verify_code, 64)  # OpenSSL IP address mismatch
            for job in jobs:
                job.result(timeout=10)


if __name__ == "__main__":
    unittest.main()
