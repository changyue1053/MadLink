"""Native host compiler gate. Exit 2 means missing coverage, NOT a passing matrix."""
import glob
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
base = root / "build" / "compiler-matrix"
base.mkdir(parents=True, exist_ok=True)
run = Path(tempfile.mkdtemp(prefix="matrix-", dir=base))

def find(name):
    discovered = shutil.which(name)
    if discovered:
        return discovered
    # Only standard public system-tool locations, not home/private trees.
    for pattern in (f"/usr/bin/{name}-*", f"/usr/lib/llvm-*/bin/{name}",
                    f"/usr/local/bin/{name}", f"/usr/local/swift/usr/bin/{name}"):
        for candidate in sorted(glob.glob(pattern)):
            if Path(candidate).is_file() and shutil.which(candidate):
                return candidate
    return None

compilers = {"gcc": {"cc": find("gcc"), "cxx": find("g++")},
             "clang": {"cc": find("clang"), "cxx": find("clang++")}}
cases = []
for producer in ("gcc", "clang"):
    for consumer in ("gcc", "clang"):
        label = f"{producer}-to-{consumer}"
        p, c = compilers[producer], compilers[consumer]
        case = {"case": label}
        if not p["cxx"] or not c["cc"] or not c["cxx"]:
            case.update(status="not_run", reason="required compiler unavailable; nothing installed")
        else:
            command = [sys.executable, str(root / "packaging/test-relocation.py"),
                       "--producer-cxx", p["cxx"], "--consumer-cc", c["cc"], "--consumer-cxx", c["cxx"]]
            result = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log = run / f"{label}.log"
            log.write_text(result.stdout)
            case.update(status="pass" if result.returncode == 0 else "fail", exit=result.returncode,
                        command=command, log=str(log))
            if result.returncode == 0:
                case["evidence"] = result.stdout.split("; evidence ")[-1].strip()
        cases.append(case)
        print(f"{label}: {case['status']}")
summary = {"compilers": compilers, "cases": cases, "complete": all(c["status"] == "pass" for c in cases),
           "scope": "native host ABI only; each executed case deletes disposable producer, relocates prefix and tests three C consumers (including repeated two-instance recovery)"}
evidence = run / "matrix.json"
evidence.write_text(json.dumps(summary, indent=2)+"\n")
print(f"Matrix evidence: {evidence}")
if any(c["status"] == "fail" for c in cases):
    sys.exit(1)
if not summary["complete"]:
    print("INCOMPLETE: missing compiler coverage; cross-compiler compatibility is NOT verified")
    sys.exit(2)
print("PASS: all four host producer/consumer directions")
