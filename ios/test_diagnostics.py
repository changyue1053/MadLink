import contextlib
import io
import sys
import tempfile
from diagnostics import run,categories
out=io.StringIO()
with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(out):
 try:run([sys.executable,'-c',"import sys;print('Undefined symbols /private/secret token=abc',file=sys.stderr);sys.exit(7)"],'build-for-testing',cwd=tmp)
 except RuntimeError:pass
 else:raise AssertionError('failure swallowed')
 try:run([sys.executable,'-c',"import time;time.sleep(5)"],'test-without-building',cwd=tmp,timeout=.05)
 except RuntimeError:pass
 else:raise AssertionError('timeout swallowed')
assert 'exit=7' in out.getvalue() and 'IOS CATEGORY link' in out.getvalue()
assert '/private' not in out.getvalue() and 'token' not in out.getvalue()
assert categories('unknown secret')==[]
print('PASS: typed failure/timeout and fixed category redaction')
