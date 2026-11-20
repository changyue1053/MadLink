"""Build and test standalone GCC host consumers of a relocated MadLink C SDK."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--ubsan", action="store_true", help="instrument producer and consumers with UBSan")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
flags = ["-fsanitize=undefined", "-fno-sanitize-recover=undefined"] if args.ubsan else []
env = {key: value for key, value in os.environ.items() if key in ("PATH", "HOME", "TMPDIR")}
env.update(LC_ALL="C", UBSAN_OPTIONS="halt_on_error=1", EXTRA_CXXFLAGS=" ".join(flags))
cc = shutil.which("gcc")
cxx = shutil.which("g++")
if not (cc and cxx and shutil.which("ar")):
    parser.error("existing gcc, g++ and ar are required; no tools are installed")
env.update(CC=cc, CXX=cxx)


def run(argv, cwd):
    subprocess.run(argv, cwd=cwd, env=env, check=True, timeout=60)


def digest(path):
    return hashlib.sha256(path.read_bytes()).digest()


with tempfile.TemporaryDirectory(prefix="madlink-tracked-") as base:
    work = Path(base).resolve()
    sdk = work / "standalone installed SDK"
    with tempfile.TemporaryDirectory(prefix="producer-", dir=work) as tmp:
        producer = Path(tmp)
        for item in ("src", "include", "packaging"):
            shutil.copytree(root / item, producer / item)
        for item in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            shutil.copyfile(root / item, producer / item)
        install = producer / "install"
        run(["sh", "packaging/install-core.sh", str(install), str(producer / "build")], producer)
        shutil.move(install, sdk)
    if producer.exists():
        raise SystemExit("FAIL: disposable producer not removed")
    header = sdk / "include/madlink_c.h"
    archive = sdk / "lib/libmadlink.a"
    before = [digest(p) for p in (header, archive)]
    cases = (
        ("legacy", root / "consumers/app_a/main.c", cc, "c11"),
        ("tracked", root / "consumers/tracked_completion/main.c", cc, "c11"),
        ("fault", root / "consumers/tracked_completion/oom.cpp", cxx, "c++17"),
    )
    for name, source, compiler, standard in cases:
        consumer = work / name
        consumer.mkdir()
        shutil.copyfile(source, consumer / source.name)
        run([compiler, f"-std={standard}", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
             *flags, "-I", str(header.parent), "-MMD", "-MF", "deps", "-c", source.name, "-o", "main.o"],
            consumer)
        dependencies = (consumer / "deps").read_text().replace("\\ ", " ")
        if str(header) not in dependencies or "madlink.hpp" in dependencies or str(producer) in dependencies:
            raise SystemExit("FAIL: consumer dependency is not the relocated public C header")
        run([cxx, *flags, "main.o", str(archive), "-o", "consumer"], consumer)
        run(["./consumer"], consumer)
    if before != [digest(p) for p in (header, archive)]:
        raise SystemExit("FAIL: consumers changed the installed SDK inputs")
print("PASS: unchanged legacy, tracked C and allocation-fault consumers on one relocated archive")
