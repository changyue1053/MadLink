"""Opt-in installed runtime check. No fetch/install/network export in this driver."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

PIN = "79fd8ced44a18bca574598ff683cd706ded16a60"
PUBLIC = "https://github.com/changyue1053/MadObs.git"
root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("madobs_checkout", type=Path)
args = parser.parse_args()
for tool in ("cmake", "make", "git", "pkg-config", "c++", "ldd"):
    if not shutil.which(tool):
        parser.error(f"required tool unavailable: {tool}; nothing installed; runtime NOT RUN")
source = args.madobs_checkout.resolve()
def git(*args):
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()
if git("rev-parse", "HEAD") != PIN or git("remote", "get-url", "origin") != PUBLIC:
    parser.error("requires exact pinned public MadObs checkout; no alternate/private fallback")
if git("status", "--porcelain"):
    parser.error("upstream checkout must be clean")
versions = {name: subprocess.check_output(command, text=True).splitlines()[0]
            for name, command in {"cmake": ["cmake", "--version"],
                                  "cxx": [os.environ.get("CXX", "c++"), "--version"],
                                  "zlib": ["pkg-config", "--modversion", "zlib"]}.items()}
base = root / "build" / "madobs-runtime"
base.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix="verify-", dir=base))
env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "TMPDIR", "LANG", "CC", "CXX", "AR")}
env["LC_ALL"] = "C"
def run(command, cwd=work):
    subprocess.run([str(x) for x in command], cwd=cwd, env=env, check=True, timeout=300)

# Delete ONLY generated producer copies, never the supplied checkout or SDK sources.
with tempfile.TemporaryDirectory(prefix="producers-", dir=work) as tmp:
    producers = Path(tmp)
    obs = producers / "madobs"
    obs.mkdir()
    archive = producers / "upstream.tar"
    run(["git", "-C", source, "archive", "--format=tar", "-o", archive, PIN])
    with tarfile.open(archive) as tar:
        # Python 3.12+ hosted runtime; data filter rejects escaping paths/links.
        tar.extractall(obs, filter="data")
    link = producers / "madlink"
    link.mkdir()
    for directory in ("include", "src", "packaging"):
        shutil.copytree(root / directory, link / directory)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(root / name, link / name)
    obs_build = producers / "obs-build"
    # No JNI, tests/server demos, BoringSSL source fetch or provider auto-discovery.
    run(["cmake", "-S", obs, "-B", obs_build, "-DCMAKE_BUILD_TYPE=Release",
         "-DBUILD_TESTING=OFF", "-DMADOBS_BUILD_RUNTIME=ON", "-DMADOBS_BUILD_SHARED=OFF",
         "-DMADOBS_BUILD_JNI=OFF", "-DMADOBS_PACKAGE_BORINGSSL=OFF",
         "-DIMOBS_BORINGSSL_ROOT=", "-DIMOBS_BORINGSSL_INCLUDE=", "-DIMOBS_BORINGSSL_CRYPTO_LIB="])
    run(["cmake", "--build", obs_build, "--parallel", "2"])
    run(["cmake", "--install", obs_build, "--prefix", producers / "obs-prefix"])
    run(["sh", link / "packaging/install-core.sh", producers / "link-prefix", producers / "link-build"])
    # Space-containing relocation tests quoting and imported-target relocation.
    obs_prefix = work / "relocated obs"
    link_prefix = work / "relocated link"
    shutil.move(str(producers / "obs-prefix"), obs_prefix)
    shutil.move(str(producers / "link-prefix"), link_prefix)
assert not producers.exists()
optional = work / "optional-prefix"
(optional / "include/madlink_madobs").mkdir(parents=True)
shutil.copyfile(root / "optional/madobs/queued_observer.hpp", optional / "include/madlink_madobs/queued_observer.hpp")
consumer = work / "consumer"
shutil.copytree(root / "tests/madobs-runtime", consumer)
consumer_build = work / "consumer-build"
run(["cmake", "-S", consumer, "-B", consumer_build, "-DCMAKE_BUILD_TYPE=Release",
     f"-DMADOBS_PREFIX={obs_prefix}", f"-DMADLINK_PREFIX={link_prefix}", f"-DOPTIONAL_PREFIX={optional}",
     "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF", "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF"])
run(["cmake", "--build", consumer_build, "--parallel", "2"])
# Check generated dependency edges, not just the test's include statements.
dependency_files = list(consumer_build.rglob("*.o.d"))
assert dependency_files, "compiler dependency evidence missing"
for path in dependency_files:
    deps = path.read_text()
    assert "madlink_c.h" in deps and "madobs/runtime.h" in deps
    assert "madlink.hpp" not in deps and str(producers) not in deps
    assert str(root / "include") not in deps
for prefix in (obs_prefix, link_prefix):
    for path in prefix.rglob("*.cmake"):
        assert str(producers) not in path.read_text(), "producer path in installed CMake metadata"
# No socket/export configuration exists in the consumer. WAL is synthetic local output.
wal = work / "wal"
wal.mkdir(mode=0o700)
subprocess.run([str(consumer_build / "consumer"), str(wal)], env=env, check=True, timeout=30)
dynamic = subprocess.check_output(["ldd", str(consumer_build / "consumer")], text=True, env=env)
assert not any(name in dynamic for name in ("libcurl", "libssl", "libcrypto")), "unexpected network/crypto runtime dependency"
evidence = {"madobs_commit": PIN, "tool_versions": versions, "producer_removed": not producers.exists(),
            "scope": "installed real runtime admission/drain and local synthetic batch validation; no network export/restart/mobile claim",
            "null_crypto_provider": True, "runtime_executed": True}
(work / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
print("PASS: relocated installed MadLink/MadObs runtime consumer; no remote export")
