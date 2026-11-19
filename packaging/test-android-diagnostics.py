import contextlib
import io
import subprocess
import sys
import tempfile
from android_diagnostics import bounded_errors, report, run_checked

hostile='secret_value /home/person/project https://user:password@example.invalid token=ghp_sensitive'
output=io.StringIO()
with contextlib.redirect_stdout(output):
 report('consumer-build',subprocess.CalledProcessError(7,['secret-command']),
        ['CMake Error at '+hostile,'fatal error: '+hostile,'Execution failed for task '+hostile]*20)
s=output.getvalue()
assert 'stage=consumer-build' in s and 'exit=7' in s
assert 'cmake-error' in s and 'compiler-fatal-error' in s
assert hostile not in s and '/home' not in s and 'secret' not in s and 'https:' not in s
assert len(s.splitlines())<=9
assert bounded_errors(['unrecognized '+hostile])==[]
with tempfile.TemporaryDirectory() as cwd, contextlib.redirect_stdout(output):
 try:
  run_checked([sys.executable,'-c',"print('CMake Error at /private/token');raise SystemExit(9)"],cwd,{},'producer-build')
 except subprocess.CalledProcessError as e: assert e.returncode==9
 else: raise AssertionError('failure swallowed')
assert '/private' not in output.getvalue()
print('PASS: bounded fixed-vocabulary diagnostics; sensitive suffixes removed; child failure preserved')
# Success stderr cannot pollute version parsing or public output.
with tempfile.TemporaryDirectory() as cwd, contextlib.redirect_stdout(output):
 version=run_checked([sys.executable,'-c',"import sys;print('Gradle 8.9');print('/secret-success token=abc',file=sys.stderr)"],cwd,{},'tool-preflight',timeout=2,capture_stdout=True)
 assert version=='Gradle 8.9\n'
 for script in ["import sys;print('fatal error: /secret-failure',file=sys.stderr);sys.exit(3)",
                "import sys,time;print('/secret-timeout',file=sys.stderr,flush=True);time.sleep(5)"]:
  try: run_checked([sys.executable,'-c',script],cwd,{},'tool-preflight',timeout=0.1,capture_stdout=True)
  except (subprocess.CalledProcessError,subprocess.TimeoutExpired): pass
  else: raise AssertionError('expected failure')
 try: run_checked([sys.executable,'-c',"print('x'*70000)"],cwd,{},'tool-preflight',timeout=2,capture_stdout=True)
 except ValueError: pass
 else: raise AssertionError('unbounded stdout')
assert '/secret' not in output.getvalue() and 'token=' not in output.getvalue()
print('PASS: version stdout-only, stderr suppressed on success/failure/timeout, output bound enforced')
# Whole-driver check ensures Python/argparse does not forward input in errors.
r=subprocess.run([sys.executable, 'packaging/test-android-preview.py','--unexpected-private-value'],capture_output=True,text=True)
assert r.returncode==1 and 'unexpected-private' not in r.stdout+r.stderr and 'Traceback' not in r.stderr
print('PASS: driver invalid CLI emits fixed diagnostic only')
from android_diagnostics import failed_tasks, log_edges
assert failed_tasks(['> Task :module:configureCMakeDebug[arm64-v8a] FAILED',
 "Execution failed for task ':module:compileDebugAndroidTestJavaWithJavac'."])==[
 ':module:configureCMakeDebug[arm64-v8a]',':module:compileDebugAndroidTestJavaWithJavac']
assert failed_tasks(['> Task :secret:token FAILED',
 '> Task :module:assembleDebug FAILED /secret',
 "Execution failed for task ':module:assembleDebug-secret'."])==[]
with tempfile.TemporaryFile() as log:
 log.write(b'x'*1500000+b'\n> Task :module:packageDebug FAILED\n')
 data=log_edges(log)
 assert len(data)<=512*1024+1
 assert failed_tasks(data.decode().splitlines())==[':module:packageDebug']
print('PASS: exact task allowlist, suffix rejection and bounded failure-tail scan')
