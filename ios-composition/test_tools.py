import contextlib,io,sys,tempfile
from pathlib import Path
from tools import run,readable_archive
out=io.StringIO()
with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(out):
 p=Path(d)/'private-name'
 try:readable_archive(p)
 except FileNotFoundError:pass
 else:raise AssertionError('missing archive accepted')
 p.write_bytes(b'!<arch>\n');readable_archive(p)
 try:run([sys.executable,'-c',"import sys;print('No such file or directory /private secret=abc',file=sys.stderr);sys.exit(2)"],'runtime-architecture')
 except RuntimeError:pass
 else:raise AssertionError('failure accepted')
assert 'private' not in out.getvalue() and 'secret' not in out.getvalue()
assert 'stage=installed-archive' in out.getvalue() and 'stage=runtime-architecture' in out.getvalue()
assert 'COMPOSITION EXIT 2' in out.getvalue()
print('PASS: distinct stages, archive guard, fixed diagnostics and no raw output')
