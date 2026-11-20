from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import verify


def symbol(name, kind="FUNC", bind="GLOBAL", visibility="DEFAULT", index="12"):
    return f"  7: 0000000000000000  12 {kind} {bind} {visibility} {index} {name}\n"


class ProofTests(unittest.TestCase):
    def test_rejects_missing_duplicate_added_or_non_function_c_exports(self):
        old = "".join(symbol(name) for name in sorted(verify.V1))
        decorations = symbol("_ZN7madlink6Client5closeEv") + symbol("unresolved", index="UND")
        verify.validate_exports(old + decorations, verify.V1)
        for changed in (
            old + symbol("unexpected_plain_c_function"),
            old + symbol("unexpected_plain_c_data", kind="OBJECT"),
            old + symbol("unexpected_weak_export", bind="WEAK"),
            old + symbol("unexpected_ifunc", kind="IFUNC"),
            old + symbol("unexpected_protected_export", visibility="PROTECTED"),
            old + symbol("ml_close_v1"),
            old.replace(symbol("ml_close_v1"), ""),
            old.replace(symbol("ml_close_v1"), symbol("ml_close_v1", visibility="HIDDEN")),
        ):
            with self.assertRaises(verify.Rejected):
                verify.validate_exports(changed + decorations, verify.V1)

    def test_requires_actual_old_installed_header_not_other_include(self):
        c = Path("/tmp/fixture.c")
        header = Path("/tmp/old moved SDK/include/madlink_c.h")
        good = "frozen: /tmp/fixture.c \\\n /tmp/old\\ moved\\ SDK/include/madlink_c.h\n"
        verify.verify_deps(good, c, header)
        for bad in (good.replace("/old", "/new"), good + "/tmp/unapproved.h", good.replace("frozen:", "alt:")):
            with self.assertRaises(verify.Rejected):
                verify.verify_deps(bad, c, header)

    def test_rejects_same_bytes_substituted_object_or_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp).resolve()
            obj, archive = folder / "fixture.o", folder / "libmadlink.a"
            obj.write_bytes(b"same object contents")
            archive.write_bytes(b"static archive")
            frozen, archive_id = verify.identity(obj), verify.identity(archive)
            moved = folder / "other"
            obj.rename(moved)
            obj.write_bytes(moved.read_bytes())
            with patch.object(verify, "command") as launch:
                with self.assertRaisesRegex(verify.Rejected, "link-input-identity"):
                    verify.link_and_run(obj, frozen, archive, archive_id, folder / "consumer", verify.V1, b"")
                launch.assert_not_called()

    def test_link_line_has_no_source_include_or_compile(self):
        obj, library, result = map(Path, ("/path/frozen.o", "/path/libmadlink.a", "/path/test"))
        self.assertEqual(verify.link_command(obj, library, result), ["g++", "-fno-lto", "-no-pie", obj, library, "-o", result])

    def test_failure_must_be_exact_missing_added_c_symbols(self):
        found = b"".join(f"undefined reference to `{name}'\n".encode() for name in sorted(verify.ADD))
        code = b"collect2: error: ld returned 1 exit status\n"
        verify.verify_missing_additions(found + code)
        for bad in (found, code, found + code + b"undefined reference to `bad_libc_name'\n",
                    found.replace(b"ml_send_tracked_v1", b"ml_send_v1") + code):
            with self.assertRaises(verify.Rejected):
                verify.verify_missing_additions(bad)

    def test_tree_mismatch_never_materializes_a_source(self):
        with patch.object(verify, "git", side_effect=[b"commit\n", (verify.NEW_TREE + "\n").encode()]):
            with self.assertRaisesRegex(verify.Rejected, "pinned-input-tree"):
                verify.resolve(verify.OLD, verify.OLD_TREE)


if __name__ == "__main__":
    unittest.main()
