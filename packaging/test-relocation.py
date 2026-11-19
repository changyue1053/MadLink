"""Build producer in disposable copy, delete it, then build isolated C consumers."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--producer-cxx", default=os.environ.get("CXX", "c++"))
parser.add_argument("--consumer-cc", default=os.environ.get("CC", "cc"))
parser.add_argument("--consumer-cxx", default=os.environ.get("CXX", "c++"))
args = parser.parse_args()
for compiler in (args.producer_cxx, args.consumer_cc, args.consumer_cxx):
    if not shutil.which(compiler):
        parser.error(f"compiler unavailable: {compiler}")
base = root / "build" / "installed-package"
base.mkdir(parents=True, exist_ok=True)
run = Path(tempfile.mkdtemp(prefix="verify-", dir=base))
prefix = run / "relocated prefix"
env = {key: value for key, value in os.environ.items()
       if key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "CC", "CXX", "AR", "EXTRA_CXXFLAGS")}
env["LC_ALL"] = "C"
records = []
toolchains = {"producer_cxx": args.producer_cxx, "consumer_cc": args.consumer_cc,
              "consumer_cxx": args.consumer_cxx}
versions = {}

def command(args, cwd, extra=None):
    current = env.copy()
    current.update(extra or {})
    result = subprocess.run(args, cwd=cwd, env=current, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=True)
    records.append({"command": args, "cwd": str(cwd), "output": result.stdout})
    print(result.stdout, end="")
    return result.stdout

for role, compiler in toolchains.items():
    versions[role] = command([compiler, "--version"], run).splitlines()[0]

# Nothing from the actual checkout is removed; only this generated producer copy.
with tempfile.TemporaryDirectory(prefix="producer-", dir=run) as temp:
    producer = Path(temp)
    for folder in ("include", "src", "packaging"):
        shutil.copytree(root / folder, producer / folder)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(root / name, producer / name)
    original = producer / "prefix"
    command(["sh", "packaging/install-core.sh", str(original), str(producer / "objects")], producer,
            {"CXX": args.producer_cxx})
    shutil.move(str(original), prefix)
assert not producer.exists()  # Both generated source and build trees are gone.

pc_env = {"PKG_CONFIG_PATH": str(prefix / "lib/pkgconfig"),
          "PKG_CONFIG_LIBDIR": str(prefix / "lib/pkgconfig")}
for flag in ("--cflags", "--libs", "--modversion"):
    value = command(["pkg-config", flag, "madlink"], run, pc_env)
    assert str(producer) not in value and str(root / "src") not in value
for app in ("app_a", "app_b", "session_lifecycle"):
    consumer = run / app
    consumer.mkdir()
    for name in ("main.c", "Makefile"):
        shutil.copyfile(root / "consumers" / app / name, consumer / name)
    flags = env.get("EXTRA_CXXFLAGS", "")
    make_args = ["make", "test", f"SDK_PREFIX={prefix}", f"CFLAGS={flags}", f"LDFLAGS={flags}",
                 f"CC={args.consumer_cc}", f"CXX={args.consumer_cxx}"]
    command(make_args, consumer, pc_env)
    # Repeated standalone invocation also exercises dependency-file parsing with spaces.
    command(make_args, consumer, pc_env)
    deps = (consumer / "main.d").read_text()
    assert "madlink_c.h" in deps and "madlink.hpp" not in deps
    assert str(producer) not in deps and str(root / "include") not in deps
    # Test environment is Linux. Confirm optional libraries are not pulled in.
    dynamic = command(["ldd", "consumer"], consumer)
    assert not any(name in dynamic for name in ("libcurl", "libssl", "libcrypto"))
    rejected = subprocess.run(["make", "test", f"SDK_PREFIX={run / 'missing-sdk'}"],
                              cwd=consumer, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert rejected.returncode != 0, "missing prefix unexpectedly accepted"
    records.append({"negative_check": "missing SDK prefix rejected", "exit": rejected.returncode})

manifest = {}
for path in sorted(prefix.rglob("*")):
    if path.is_file():
        data = path.read_bytes()
        assert str(producer).encode() not in data, f"producer path leaked into {path}"
        manifest[str(path.relative_to(prefix))] = hashlib.sha256(data).hexdigest()
expected = {"include/madlink_c.h", "lib/libmadlink.a", "lib/pkgconfig/madlink.pc", "share/doc/madlink/README.md",
            "share/doc/madlink/LICENSE", "share/doc/madlink/THIRD_PARTY_NOTICES.md"}
assert set(manifest) == expected
evidence = {"prefix": str(prefix), "removed_producer": str(producer), "producer_exists": producer.exists(),
            "toolchains": toolchains, "compiler_versions": versions,
            "files_sha256": manifest, "commands": records,
            "scope": "Linux native relocated core C SDK, not mobile/cross-architecture/WSS/MadObs"}
(run / "evidence.json").write_text(json.dumps(evidence, indent=2)+"\n")
print(f"PASS: three standalone C consumers after producer deletion; evidence {run / 'evidence.json'}")
