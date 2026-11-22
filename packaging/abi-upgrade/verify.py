"""Frozen Linux x86-64 legacy C object -> independently relocated static SDKs."""
from collections import Counter
import argparse
import hashlib
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OLD = "0f33e1383503babe7d489fc3f771fc622d7cff75"
OLD_TREE = "b009e48a3a07099c96c32fe62d735ddba9765f0b"
NEW = "a6d869efd8a5b3f2eb1f31e9b5c1a37392251867"
NEW_TREE = "e6ee8b6ef2c8f8bfd30e5ac90ae05d7811a12350"
V1 = frozenset("ml_create_v1 ml_connect_v1 ml_send_v1 ml_tick_v1 ml_cancel_v1 ml_close_v1 ml_next_event_v1 ml_destroy_v1".split())
ADD = frozenset("ml_create_tracked_v1 ml_send_tracked_v1 ml_next_completion_v1".split())
CASES = {
    "legacy-send": ("consumers/app_a/main.c", "c07a7125a70bc80371b2ad5258424ca4c099ed2f",
                    V1 - {"ml_cancel_v1"}, b"PASS: independent C consumer A send lifecycle\n"),
    "legacy-isolation": ("consumers/app_b/main.c", "e31f833d42c447b2cc009e034d5d84b9720212b2",
                         V1 - {"ml_close_v1"}, b"PASS: independent C consumer B receive, cancellation and isolation\n"),
    "legacy-generations": ("tests/test_c_generation.c", "c9ab8dd2a675a28827309151b5e30a180b693a55",
                           V1 - {"ml_next_event_v1"}, b"PASS: C ABI stale malformed events are isolated across reconnect\n"),
}
TRACKED = ("consumers/tracked_completion/main.c", "93fe95ef1f602757c20c4492dcd2fc2eca69fdef",
           b"PASS: installed tracked C SDK capacity, terminal results, and handle isolation\n")
TOOLS = {name: "/usr/bin/" + name for name in ("ar", "gcc", "g++", "git", "nm", "readelf", "tar")}
TOOLS["sh"] = "/bin/sh"


class Rejected(ValueError):
    pass


def require(good, stage):
    if not good:
        raise Rejected(stage)


def command(args, stage, *, timeout=30, fail=False, cwd=ROOT, stdout=subprocess.PIPE):
    argv = [str(TOOLS.get(args[0], args[0])), *map(str, args[1:])]
    try:
        proc = subprocess.run(argv, cwd=cwd, env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
                                                   "CC": TOOLS["gcc"], "CXX": TOOLS["g++"], "AR": TOOLS["ar"],
                                                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
                              stdin=subprocess.DEVNULL, stdout=stdout, stderr=subprocess.PIPE,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Rejected(stage) from None
    require((proc.returncode > 0 if fail else proc.returncode == 0) and
            len(proc.stdout or b"") <= 512 * 1024 and len(proc.stderr) <= 512 * 1024, stage)
    return proc


def git(*args):
    return command(["git", "-C", ROOT, *args], "pinned-input").stdout


def resolve(ref, tree):
    require(re.fullmatch(r"[0-9a-f]{40}", ref) and git("cat-file", "-t", ref) == b"commit\n" and
            git("rev-parse", ref + "^{tree}").decode("ascii").strip() == tree, "pinned-input-tree")
    return ref


def bytes_for(ref, path, blob):
    require(git("rev-parse", f"{ref}:{path}").decode("ascii").strip() == blob, "pinned-input-blob")
    data = git("show", f"{ref}:{path}")
    calculated = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    require(calculated == blob, "pinned-input-blob")
    return data


def identity(path):
    require(path.is_file() and path.resolve(strict=True) == path, "file-containment")
    info = path.stat()
    with path.open("rb") as file:
        return (info.st_dev, info.st_ino, info.st_size, hashlib.file_digest(file, "sha256").hexdigest())


def erase_source(root, source, build, prefix, moved):
    prefix.rename(moved)
    shutil.rmtree(source)
    shutil.rmtree(build)
    require(moved.parent == root and moved.is_dir() and
            all(not p.exists() and not p.is_symlink() for p in (source, build, prefix)), "producer-removed")


def install(root, label, revision, header_blob):
    source, build = root / (label + "-source"), root / (label + "-build")
    prefix, moved = root / (label + "-prefix"), root / (label + " moved SDK")
    source.mkdir()
    tar = root / (label + ".tar")
    with tar.open("wb") as stream:
        command(["git", "-C", ROOT, "archive", "--format=tar", revision], "snapshot-source", stdout=stream)
    command(["tar", "-xf", tar, "-C", source], "materialize-source")
    tar.unlink()
    expected_header = bytes_for(revision, "include/madlink_c.h", header_blob)
    command(["sh", source / "packaging/install-core.sh", prefix, build], "install-sdk", cwd=source, timeout=90)
    erase_source(root, source, build, prefix, moved)
    header, archive = moved / "include/madlink_c.h", moved / "lib/libmadlink.a"
    identity(header)
    require(header.read_bytes() == expected_header, "installed-header")
    identity(archive)
    with archive.open("rb") as lib:
        require(lib.read(8) == b"!<arch>\n", "installed-archive")
    members = command(["ar", "t", archive], "archive-members").stdout.splitlines()
    require(members == [b"madlink.o", b"madlink_c.o"], "archive-members")
    return header, archive


def validate_exports(text, expected):
    # Global/weak public non-C++ definitions in an archive must be exactly
    # the public C functions. Catch extra objects/IFUNCs and unprefixed C
    # exports too. Decorated C++ implementation symbols are not C ABI.
    names = []
    for line in text.splitlines():
        m = re.fullmatch(r"\s*\d+:\s+[0-9a-fA-F]+\s+\d+\s+(\S+)\s+(GLOBAL|WEAK|UNIQUE)\s+(DEFAULT|PROTECTED)\s+(\S+)\s+(\S+)\s*", line)
        if m:
            kind, binding, _, index, name = m.groups()
            if index != "UND" and not name.startswith("_Z"):
                require(binding == "GLOBAL" and kind == "FUNC", "unexpected-c-export-kind")
                names.append(name)
    require(Counter(names) == Counter(expected), "public-c-exports")


def undefined(text):
    return frozenset(m[1] for line in text.splitlines()
                     if (m := re.fullmatch(r"(ml_[a-z0-9_]+)\s+U\s*", line)))


def verify_deps(text, fixture, header):
    head, sep, deps = text.replace("\\\n", "").partition(":")
    require(sep and head == "frozen" and shlex.split(deps) == [str(fixture), str(header)], "compiler-header-proof")


def compile_once(folder, case, source, header, symbols=None):
    fixture, obj, dep = (folder / (case + ext) for ext in (".c", ".o", ".d"))
    fixture.write_bytes(source)
    require(not obj.exists(), "object-already-produced")
    command(["gcc", "-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
             "-fno-lto", "-fno-pie", "-UNDEBUG", "-ffile-prefix-map=" + str(folder) + "=madlink-frozen-fixtures",
             "-MMD", "-MF", dep, "-MT", "frozen",
             "-I" + str(header.parent), "-c", fixture, "-o", obj], "compile-c")
    verify_deps(dep.read_text(encoding="ascii"), fixture, header)
    elf = command(["readelf", "-W", "-h", obj], "object-elf").stdout.decode("ascii")
    require(re.search(r"(?m)^\s*Type:\s+REL ", elf) and re.search(r"(?m)^\s*Class:\s+ELF64\s*$", elf) and
            re.search(r"(?m)^\s*Machine:\s+Advanced Micro Devices X86-64\s*$", elf), "object-elf")
    actual = undefined(command(["nm", "-P", "-u", obj], "object-symbols").stdout.decode("ascii"))
    require(actual == symbols if symbols is not None else ADD <= actual <= (V1 | ADD), "object-symbols")
    obj.chmod(0o444)
    frozen = identity(obj)
    print(f"OBJECT {case} SHA256={frozen[-1]} C_REFERENCES={','.join(sorted(actual))}", flush=True)
    return obj, frozen


def link_command(obj, archive, out):
    return ["g++", "-fno-lto", "-no-pie", obj, archive, "-o", out]


def link_and_run(obj, frozen, archive, archive_identity, out, expected_exports, expected_output):
    require(identity(obj) == frozen and identity(archive) == archive_identity and not out.exists(),
            "link-input-identity")
    command(link_command(obj, archive, out), "link-frozen-object")
    elf = command(["readelf", "-W", "-s", out], "linked-elf").stdout.decode("ascii")
    present = frozenset(m[1] for line in elf.splitlines() if
                        (m := re.search(r"\bFUNC\s+GLOBAL\s+(?:DEFAULT|PROTECTED)\s+\d+\s+(ml_[a-z0-9_]+)$", line)))
    require(present == expected_exports, "linked-c-symbol-set")
    actual = command([out], "execute-installed-consumer")
    require(actual.stdout == expected_output and actual.stderr == b"" and identity(obj) == frozen and
            identity(archive) == archive_identity, "consumer-result-or-input-mutation")


def verify_missing_additions(stderr):
    names = re.findall(rb"undefined reference to [`']([^`'\r\n]+)'", stderr)
    expected = {name.encode("ascii") for name in ADD}
    require(set(names) == expected and stderr.count(b"undefined reference to") == len(names) and
            b"collect2: error: ld returned 1 exit status" in stderr, "negative-old-missing-exact-additions")


def old_archive_rejects(obj, frozen, archive, archive_identity, out):
    require(identity(obj) == frozen and identity(archive) == archive_identity and not out.exists(),
            "link-input-identity")
    proc = command(link_command(obj, archive, out), "negative-old-archive", fail=True)
    verify_missing_additions(proc.stderr)
    require(not out.exists() and identity(obj) == frozen and identity(archive) == archive_identity,
            "negative-old-input-mutation")


def main(old_ref, new_ref):
    require(platform.system() == "Linux" and platform.machine() == "x86_64" and
            all(Path(path).is_file() and os.access(path, os.X_OK) for path in TOOLS.values()), "linux-existing-toolchain")
    gcc = command(["gcc", "-dumpmachine"], "compiler-target").stdout
    gxx = command(["g++", "-dumpmachine"], "compiler-target").stdout
    version = command(["gcc", "-dumpfullversion"], "compiler-version").stdout
    require(gcc == gxx and gcc.startswith(b"x86_64-") and
            re.fullmatch(rb"[0-9]+(?:\.[0-9]+)*\n", version) and
            version == command(["g++", "-dumpfullversion"], "compiler-version").stdout, "compiler-identity")
    old, new = resolve(old_ref, OLD_TREE), resolve(new_ref, NEW_TREE)
    print("INPUTS exact public trees; GCC x86-64 " + version.decode("ascii").strip(), flush=True)
    with tempfile.TemporaryDirectory(prefix="madlink-frozen-c-abi-") as tmp:
        root = Path(tmp).resolve()
        old_header, old_archive = install(root, "old", old, "85525cdc4db5d2890deaf012659e9ba2185e65b8")
        new_header, new_archive = install(root, "new", new, "edccaf6e5525b005aedbf9aeab6e7ebfe9ee35c2")
        old_archive_id, new_archive_id = identity(old_archive), identity(new_archive)
        for archive, symbols in ((old_archive, V1), (new_archive, V1 | ADD)):
            validate_exports(command(["readelf", "-W", "-s", archive], "archive-symbols").stdout.decode("ascii"), symbols)
        print("PASS: exact eight old and only three additive tracked C archive symbols", flush=True)
        for case, (path, blob, symbols, output) in CASES.items():
            source = bytes_for(old, path, blob)
            require(source == bytes_for(new, path, blob), "legacy-source-not-identical")
            folder = root / case
            folder.mkdir()
            obj, frozen = compile_once(folder, case, source, old_header, symbols)
            link_and_run(obj, frozen, old_archive, old_archive_id, folder / "old-run", V1, output)
            link_and_run(obj, frozen, new_archive, new_archive_id, folder / "new-run", V1 | ADD, output)
            print(f"PASS: {case} old object linked and ran unchanged with both archives", flush=True)
        folder = root / "tracked-only"
        folder.mkdir()
        path, blob, output = TRACKED
        obj, frozen = compile_once(folder, "tracked-positive", bytes_for(new, path, blob), new_header)
        old_archive_rejects(obj, frozen, old_archive, old_archive_id, folder / "must-not-link")
        link_and_run(obj, frozen, new_archive, new_archive_id, folder / "tracked-run", V1 | ADD, output)
        print("PASS: same tracked object rejected by old linker and executed with new archive", flush=True)
    print("PASS: three unchanged legacy objects; six same-toolchain static relink runs; tracked negative and positive", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-ref", default=OLD, help="exact public old commit or explicit same-tree local commit")
    parser.add_argument("--new-ref", default=NEW, help="exact public new commit or explicit same-tree local commit")
    ns = parser.parse_args()
    try:
        main(ns.old_ref, ns.new_ref)
    except Rejected as error:
        raise SystemExit("FAIL: " + str(error)) from None
    except Exception:
        raise SystemExit("FAIL: abi-upgrade-infrastructure") from None
