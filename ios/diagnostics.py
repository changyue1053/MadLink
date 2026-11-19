"""Fixed vocabulary only; subprocess output never forwarded."""
import subprocess
import tempfile
STAGES={'version','archive-device','archive-simulator','create-xcframework','sim-create','sim-boot','sim-ready','build-for-testing','test-without-building','test-summary','sim-delete'}
CATEGORIES={'signing':('CodeSign','code signing','codesign'),
 'compile':('CompileC','CompileSwift','compilation failed'),
 'link':('Undefined symbols','Linker command failed','linker command failed'),
 'module':('module not found','could not build module'),
 'test-failed':('TEST FAILED','Testing failed'),
 'build-failed':('BUILD FAILED','BUILD FOR TESTING FAILED'),
 'test-host':('Failed to load test bundle','Failed to launch','test host'),
 'destination':('Unable to find a destination','Ineligible destinations')}
def categories(text):
 return [key for key,needles in CATEGORIES.items() if any(n in text for n in needles)][:8]
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
