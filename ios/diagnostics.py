"""Fixed vocabulary only; subprocess output never forwarded."""
import re
import subprocess
import tempfile
STAGES={'version','archive-device','archive-simulator','create-xcframework','sim-create','sim-boot','sim-ready','build-for-testing','test-without-building','test-summary','test-cases','sim-delete'}
# Output consists only of constants below; never echo matched source/paths.
ERRORS = {
 'undefined-symbols': r'^Undefined symbols for architecture arm64:',
 'linker-failed': r'^(?:clang(?:\+\+)?|ld): error: .*linker command failed',
 'missing-framework': r'^ld: (?:framework .* not found|framework not found)',
 'missing-library': r'^ld: library .* not found',
 'compiler-error': r'^.+:[0-9]+:[0-9]+: (?:fatal )?error:',
 'module-error': r'^.+:[0-9]+:[0-9]+: (?:fatal )?error: .*?(?:module|file not found)',
 'signing-error': r'^.*(?:error:|Error:) .*?(?:signing|CodeSign|provisioning)',
 'test-host-error': r'^.*error: .*?(?:test host|TEST_HOST|BUNDLE_LOADER)',
 'build-failed': r'^\*\* BUILD(?: FOR TESTING)? FAILED \*\*$',
}
COMMANDS={'Ld','CompileC','CodeSign','ProcessXCFramework','GenerateDSYMFile','SwiftCompile'}
TARGETS={'Demo','SmokeTests','MadLink'}
SYMBOLS={'_madlinkSmoke','_ml_create_v1','_ml_connect_v1','_ml_tick_v1','_ml_send_v1',
         '_ml_next_event_v1','_ml_close_v1','_ml_destroy_v1','_UIApplicationMain',
         '_OBJC_CLASS_$_XCTestCase','_OBJC_CLASS_$_UIApplication','_OBJC_CLASS_$_UILabel'}
def categories(text):
 found=[];failed=False;undefined=False
 def add(label):
  if label not in found and len(found)<16:found.append(label)
 for raw in text.splitlines():
  line=raw.strip()
  for label,pattern in ERRORS.items():
   if re.search(pattern,line):add(label)
  if line.startswith('Undefined symbols for architecture arm64:'):undefined=True
  if undefined:
   match=re.match(r'^"([^"\n]+)", referenced from:$',line)
   if match and match[1] in SYMBOLS:add('symbol-'+match[1])
  if line=='The following build commands failed:':failed=True;continue
  if failed:
   match=re.match(r"^(\w+) .*\(in target '([^']+)' from project 'Preview'\)$",line)
   if match and match[1] in COMMANDS and match[2] in TARGETS:
    add('failed-command-'+match[1]+'-target-'+match[2])
 return found
def run(args,stage,cwd=None,capture=False,timeout=600):
 if stage not in STAGES:raise ValueError('invalid stage')
 with tempfile.TemporaryFile() as log:
  try:
   subprocess.run([str(x) for x in args],cwd=cwd,stdout=log,stderr=log,check=True,timeout=timeout)
  except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as e:
   log.seek(0,2);size=log.tell();log.seek(max(0,size-512*1024))
   text=log.read(512*1024).decode('utf-8',errors='replace')
   print('IOS FAIL stage='+stage+' exception='+type(e).__name__+((' exit='+str(e.returncode)) if isinstance(e,subprocess.CalledProcessError) else ''),flush=True)
   for label in categories(text):print('IOS CATEGORY '+label,flush=True)
   raise RuntimeError('bounded subprocess failure') from None
  if capture:
   log.seek(0);data=log.read(1024*1024+1)
   if len(data)>1024*1024:raise ValueError('output bound')
   return data.decode('utf-8')
