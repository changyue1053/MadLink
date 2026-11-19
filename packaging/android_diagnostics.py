"""Emit fixed diagnostic vocabulary only, never arbitrary build output."""
import re
import subprocess
import tempfile

STAGES = {'tool-preflight','producer-build','aar-inspection','consumer-build','consumer-apk-build','consumer-test-apk-build',
          'zip-alignment','elf-inspection','dependency-inspection','evidence'}
# Match ordinary build failures, but deliberately do not echo their dynamic suffix.
# Paths, URLs, source snippets, credentials and artifact content never pass through.
PATTERNS = (
 ('cmake-error', re.compile(r'CMake Error')),
 ('gradle-task-failed', re.compile(r'Execution failed for task')),
 ('gradle-project-evaluation', re.compile(r'A problem occurred evaluating project')),
 ('gradle-dependency-resolution', re.compile(r'Could not resolve')),
 ('cmake-package-not-found', re.compile(r'Could not find a package configuration file')),
 ('native-undefined-symbol', re.compile(r'undefined (reference|symbol)')),
 ('compiler-fatal-error', re.compile(r'fatal error:')),
 ('compiler-error', re.compile(r'\berror:')),
 ('missing-file', re.compile(r'No such file or directory')),
 ('gradle-build-failed', re.compile(r'BUILD FAILED')),
 ('native-build-failed', re.compile(r'ninja: build stopped')),
 ('sdk-license-required', re.compile(r'licenses? (have not been accepted|not accepted)', re.I)),
)
# Only enumerated generated tasks from this project's two fixed modules.
TASKS = {':module:'+name for name in (
    'assembleDebug','assembleDebugAndroidTest','preDebugBuild','checkDebugAarMetadata',
    'processDebugMainManifest','processDebugManifest','processDebugResources',
    'mergeDebugResources','compileDebugJavaWithJavac','mergeDebugNativeLibs',
    'stripDebugDebugSymbols','packageDebug','configureCMakeDebug[arm64-v8a]',
    'buildCMakeDebug[arm64-v8a]','externalNativeBuildDebug',
    'compileDebugAndroidTestJavaWithJavac','processDebugAndroidTestManifest',
    'processDebugAndroidTestResources','checkDebugAndroidTestAarMetadata',
    'mergeDebugAndroidTestResources','mergeDebugAndroidTestNativeLibs',
    'packageDebugAndroidTest','dexBuilderDebug','dexBuilderDebugAndroidTest')}
TASKS.add(':madlink:assembleRelease')
def failed_tasks(lines):
    found=[]
    for line in lines:
        match=re.fullmatch(r"\s*> Task (:[^\s]+) FAILED\s*",line)
        if not match:
            match=re.fullmatch(r"\s*Execution failed for task '(:[^']+)'\.?\s*",line)
        if match and match[1] in TASKS and match[1] not in found:
            found.append(match[1])
            if len(found)==4: break
    return found

def log_edges(stream):
    # Failure is commonly at the tail after Gradle progress/dependency output.
    # Read at most 512 KiB per stream, not the whole raw build log.
    stream.seek(0,2);size=stream.tell();stream.seek(0)
    head=stream.read(256*1024)
    if size<=len(head): return head
    stream.seek(max(len(head),size-256*1024))
    return head+b"\n"+stream.read(256*1024)

def bounded_errors(lines):
    found=[]
    for line in lines:
        for label, pattern in PATTERNS:
            if pattern.search(line) and label not in found:
                found.append(label)
                if len(found)==8: return found
    return found

def report(stage, error, lines=()):
    if stage not in STAGES: stage='tool-preflight'
    kind=type(error).__name__
    if kind not in {'CalledProcessError','TimeoutExpired','AssertionError','FileNotFoundError',
                    'ValueError','BadZipFile','PermissionError','RuntimeError','SystemExit'}: kind='Exception'
    code=error.returncode if isinstance(error,subprocess.CalledProcessError) else None
    print('ANDROID FAIL stage='+stage+' exception='+kind+((' exit='+str(int(code))) if code is not None else ''),flush=True)
    for label in bounded_errors(lines): print('ANDROID TOOL ERROR '+label,flush=True)
    for task in failed_tasks(lines): print('ANDROID FAILED TASK '+task,flush=True)

def run_checked(args, cwd, env, stage, timeout=600, capture_stdout=False):
    # Both streams are disk-backed. Only bounded stdout is returned for parsing;
    # stderr is never returned or forwarded, including success and timeout paths.
    with tempfile.TemporaryFile(mode='w+b') as out, tempfile.TemporaryFile(mode='w+b') as err:
        try:
            subprocess.run([str(x) for x in args],cwd=cwd,env=env,check=True,
                           timeout=timeout,stdout=out,stderr=err)
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
            text=(log_edges(out)+b"\n"+log_edges(err)).decode('utf-8',errors='replace')
            report(stage,error,text.splitlines())
            raise
        if capture_stdout:
            out.seek(0)
            data=out.read(65537)
            if len(data)>65536: raise ValueError('version output exceeds bound')
            return data.decode('utf-8',errors='replace')
        return None
