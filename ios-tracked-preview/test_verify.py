"""Portable exact-byte, artifact and XCTest guard tests; never invoke Xcode."""
from pathlib import Path
import tempfile
import unittest
import verify


class Guards(unittest.TestCase):
    def test_verified_old_fixture_bytes(self):
        verify.verify_legacy_inputs()

    def test_exact_symbols_and_linked_symbols(self):
        all_symbols = "".join(f"0000 T {name}\n" for name in verify.V1 | verify.TRACKED)
        verify.symbol_gate(all_symbols, exact=True)
        verify.symbol_gate(all_symbols)
        for bad in (all_symbols.replace("_ml_cancel_v1", "_ml_injected_v1"),
                    all_symbols + "0000 T _ml_extra_v1\n",
                    all_symbols + "0000 T _ml_send_tracked_v1\n"):
            with self.assertRaises(verify.Failure):
                verify.symbol_gate(bad, exact=True)
        with self.assertRaises(verify.Failure):
            verify.symbol_gate("     U _ml_send_tracked_v1\n")

    def test_platform_only(self):
        verify.platform_gate("platform IOS\n", False)
        verify.platform_gate("platform IOSSIMULATOR\n", True)
        verify.platform_gate("platform 7\n", True)
        for bad in ("platform IOS\n", "", "platform IOSSIMULATOR\nplatform IOS\n"):
            with self.assertRaises(verify.Failure):
                verify.platform_gate(bad, True)

    def test_exact_tests_and_no_extra(self):
        summary={"totalTestCount":3,"passedTests":3,"failedTests":0,"skippedTests":0}
        nodes=[{"nodeType":"Test Case","nodeIdentifier":name+"()","result":"Passed"} for name in sorted(verify.TESTS)]
        verify.check_results(summary, {"testNodes":[{"children":nodes}]})
        for bad_summary, bad_nodes in ((summary,nodes[1:]), (summary,nodes+[nodes[0]]),
                                       (summary|{"skippedTests":1},nodes),
                                       (summary,[nodes[0]|{"result":"Failed"},*nodes[1:]])):
            with self.assertRaises(verify.Failure):
                verify.check_results(bad_summary, {"testNodes":bad_nodes})

    def test_package_path_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home).resolve()
            (root/"safe").write_bytes(b"share")
            self.assertEqual(verify.contained(root,"safe"),root/"safe")
            (root/"link").symlink_to(root/"safe")
            with self.assertRaises(verify.Failure):
                verify.contained(root,"link")
            with self.assertRaises(verify.Failure):
                verify.fingerprint(root)

    def test_independent_device_simulator_source_shapes(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home).resolve()
            package=root/"package"
            package.mkdir()
            (package/"empty").touch()
            for simulator in (True,False):
                consumer=root/str(simulator)
                installed=verify.prepare_consumer(consumer,package,simulator)
                self.assertEqual(verify.fingerprint(installed),verify.fingerprint(package))
                project=(consumer/"Preview.xcodeproj/project.pbxproj").read_text()
                self.assertEqual(project.count('"path" = "MadLink.xcframework"'),2)
                self.assertNotIn("Frameworks/MadLink.framework",project)
                self.assertEqual("TrackedFixture.c" in project,simulator)
                self.assertEqual("TrackedTests.mm" in project,simulator)
                self.assertEqual("SessionLifecycle.c" in project,simulator)
                self.assertEqual('"sourcecode.c.c"' in project,simulator)
                actual=(consumer/"Smoke.mm").read_bytes()
                expected=verify.ROOT/"ios/Smoke.mm" if simulator else verify.HERE/"DeviceSmoke.mm"
                self.assertEqual(actual,expected.read_bytes())


if __name__=="__main__":
    unittest.main()
