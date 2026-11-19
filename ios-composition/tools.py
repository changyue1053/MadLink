"""Composition-only fixed stages; no external log text is emitted."""
import re
import subprocess
import tempfile
STAGES={'git-pin','git-origin','git-clean','off-gate','sdk-path','sdk-version',
        'source-archive','runtime-configure','runtime-build','runtime-install',
        'installed-archive','runtime-architecture','sim-create','sim-boot','sim-ready',
        'sim-architecture','on-build','on-test','on-summary','on-cases','sim-delete'}
CATEGORIES={'missing-file':('No such file or directory',),
 'git-revision':('not a valid object name','bad object','unknown revision'),
 'cmake-error':('CMake Error',),'archive-format':('not an object file','not a valid archive'),
 'xcrun-tool':('unable to find utility',),'build-failed':('BUILD FAILED','BUILD FOR TESTING FAILED'),
 'test-failed':('TEST FAILED',)}
def compiler_categories(text):
 found=[]
 def add(x):
  if x not in found and len(found)<12:found.append(x)
 failed=False
 for line in text.splitlines():
  line=line.strip()
  # Anchor to a compiler error, not a successful command containing these words.
  if re.search(r':(?:[0-9]+:){1,2}\s*(?:fatal )?error:',line):
   for label,pattern in [('unknown-identifier',r'undeclared identifier|unknown type name'),
                         ('no-header',r'file not found'),('no-module',r'module .* not found|could not build module'),
                         ('arc',r'ARC|ownership|retainable|bridged cast'),
                         ('signature',r'no matching function|incompatible|cannot initialize|cannot convert')]:
    if re.search(pattern,line):add(label)
   for header in ['madobs/runtime.h','madlink_madobs/queued_observer.hpp','MadLink/madlink_c.h','imobs/imobs_c.h']:
    if ("'"+header+"' file not found") in line:add('missing-header-'+header)
  if line=='The following build commands failed:':failed=True;continue
  if failed:
   m=re.match(r"^(CompileC|Ld|CodeSign|ProcessXCFramework) .*\(in target '(Demo|SmokeTests)' from project 'Preview'\)$",line)
   if m:add('failed-'+m[1]+'-'+m[2])
 return found

def mark(kind,stage):
 if stage not in STAGES:raise ValueError('invalid stage')
 print('COMPOSITION '+kind+' stage='+stage,flush=True)
def readable_archive(path):
 stage='installed-archive';mark('START',stage)
 try:
  with path.open('rb') as f:
   if f.read(8)!=b'!<arch>\n':raise ValueError('unexpected archive')
 except Exception:
  mark('FAIL',stage);raise
 mark('PASS',stage)
def run(args,stage,cwd=None,capture=False,timeout=600):
 mark('START',stage)
 with tempfile.TemporaryFile() as log:
  try:
   subprocess.run([str(x) for x in args],cwd=cwd,stdout=log,stderr=log,check=True,timeout=timeout)
  except (subprocess.SubprocessError,OSError) as error:
   mark('FAIL',stage)
   if isinstance(error,subprocess.CalledProcessError):print('COMPOSITION EXIT '+str(error.returncode),flush=True)
   log.seek(0,2);log.seek(max(0,log.tell()-512*1024))
   text=log.read(512*1024).decode('utf-8',errors='replace')
   for label,terms in CATEGORIES.items():
    if any(term in text for term in terms):print('COMPOSITION CATEGORY '+label,flush=True)
   for label in compiler_categories(text):print('COMPOSITION CLASS '+label,flush=True)
   raise RuntimeError('tool failure') from None
  result=None
  if capture:
   log.seek(0);data=log.read(1024*1024+1)
   if len(data)>1024*1024:mark('FAIL',stage);raise ValueError('output bound')
   result=data.decode('utf-8')
  mark('PASS',stage)
  return result
