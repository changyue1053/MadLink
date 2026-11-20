import contextlib
import io
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

import binding
import receipt_probe as probe


class ProbeTests(unittest.TestCase):
    def test_finite_metadata_shapes_without_values(self):
        for metadata, labels in (
            (False, ("metadata:not-dictionary",)),
            ({}, ("metadata-extra:none", "format:absent")),
            ({"FormatVersion": True}, ("metadata-extra:none", "format:not-integer")),
            ({"FormatVersion": 2}, ("metadata-extra:none", "format:two")),
            ({"FormatVersion": 1}, ("metadata-extra:none", "format:one")),
            ({"FormatVersion": 314159}, ("metadata-extra:none", "format:unsupported-integer")),
            ({"FormatVersion": 1, "private-key": "raw-path"}, ("metadata-extra:one", "format:one")),
            ({"private-key": "raw-path", "another-field": "anything"}, ("metadata-extra:multiple", "format:absent")),
        ):
            with self.subTest(shape=labels):
                output = probe.describe({probe.METADATA: metadata})
                self.assertTrue(set(labels) <= set(output))
                self.assertNotRegex(" ".join(output), "private-key|raw-path|another-field|anything|314159")
        self.assertEqual(probe.describe([]), ["root:not-dictionary"])
        self.assertIn("metadata:absent", probe.describe({}))

    def test_v2_shape_independent_of_metadata_gate(self):
        sample = {probe.METADATA: {"FormatVersion": 2, "unreviewed": "never report"},
                  "TestConfigurations": [{"IsEnabled": True, "TestTargets": [{
                      "BlueprintName": binding.TEST,
                      "TestHostPath": "/do/not/report",
                      "TestBundlePath": binding.ROOT + binding.TOP,
                      "TestingEnvironmentVariables": {"not-allowed": "other"},
                  }]}]}
        output = probe.describe(sample)
        self.assertTrue({"policy:wss-receipt-format", "route-v2:single-dictionary", "v2-config:enabled",
                         "v2-target:single-dictionary", "target-host:other", "target-bundle:known",
                         "target-loader:other", "target-selection:none"} <= set(output))
        self.assertNotRegex(" ".join(output), "unreviewed|never report|not-allowed|/do/not/report")

    def test_reads_only_bounded_canonical_products(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            receipt = root / "Owned.xctestrun"
            self.assertEqual(probe.inspect(root), ["receipt:absent"])
            receipt.write_bytes(b"x" * (probe.MAX_RECEIPT + 1))
            self.assertIn("receipt:too-large", probe.inspect(root))
            receipt.write_bytes(plistlib.dumps([]))
            self.assertIn("root:not-dictionary", probe.inspect(root))
            host = root / binding.APP
            host.mkdir(parents=True)
            info = host / "Info.plist"
            info.write_bytes(plistlib.dumps([]))
            self.assertIn("host-info:not-dictionary", probe.inspect(root))
            alias = root / "Alias.xctestrun"
            alias.symlink_to(receipt)
            self.assertEqual(probe.inspect(root), ["receipt:multiple"])
            receipt.unlink()
            self.assertEqual(probe.inspect(root), ["receipt:noncanonical"])

    def test_wrapper_only_creates_builds_and_removes_owned_unbooted_sim(self):
        uuid = "22222222-3333-4444-5555-666666666666"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            logs = io.StringIO()
            with patch.object(probe, "prepare", return_value=root / "relocated") as setup, \
                 patch.object(probe, "run", side_effect=[uuid, None, None]) as run, \
                 patch.object(probe.tracked, "fingerprint", return_value={}), \
                 patch.object(probe, "inspect", return_value=["metadata:absent"]), \
                 contextlib.redirect_stdout(logs):
                probe.diagnose(root, root / "real package", {})
            self.assertEqual(setup.call_args.args[1:], (root / "real package", b"\0" * 256, (1, 2)))
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual([command[:3] for command in commands],
                             [["xcrun", "simctl", "create"], ["xcodebuild", "build-for-testing", "-project"],
                              ["xcrun", "simctl", "delete"]])
            self.assertEqual(run.call_args_list[0].kwargs, {"capture": True, "timeout": 120})
            self.assertIn("platform=iOS Simulator,id=" + uuid, commands[1])
            self.assertEqual(commands[2][-1], uuid)
            self.assertEqual(logs.getvalue().splitlines(),
                             [probe.PREFIX + "metadata:absent", probe.PREFIX + "build-only-finished-no-runtime"])


if __name__ == "__main__":
    unittest.main()
