"""Builds disposable native archives and executes one synthetic simulator XCTest."""
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import tempfile
from project import generate
root=Path(__file__).resolve().parents[1]
if platform.system()!='Darwin' or platform.machine()!='arm64':
    raise SystemExit('NOT RUN: Apple ARM64 host required')
if 'Xcode 26.2' not in subprocess.check_output(['xcodebuild','-version'],text=True):
    raise SystemExit('NOT RUN: pinned Xcode 26.2 required')
base=root/'build/ios-preview';base.mkdir(parents=True,exist_ok=True)
work=Path(tempfile.mkdtemp(prefix='check-',dir=base))
def run(args,cwd=work):
    with tempfile.TemporaryFile() as log:
        try:subprocess.run([str(x) for x in args],cwd=cwd,stdout=log,stderr=log,check=True,timeout=600)
        except subprocess.SubprocessError as e:
            raise RuntimeError('iOS stage failed: '+str(args[0])+' '+type(e).__name__) from None
with tempfile.TemporaryDirectory(prefix='producer-',dir=work) as tmp:
    producer=Path(tmp)
    for directory,names in [('src',['madlink.cpp','madlink_c.cpp']),('include',['madlink.hpp','madlink_c.h'])]:
        for name in names:shutil.copyfile(root/directory/name,producer/name)
    (producer/'module.modulemap').write_text('framework module MadLink { umbrella header "madlink_c.h" export * module * { export * } }\n')
    generate(producer,True)
    archives=[]
    for label,dest in [('device','generic/platform=iOS'),('simulator','generic/platform=iOS Simulator')]:
        archive=producer/(label+'.xcarchive');archives.append(archive)
        run(['xcodebuild','archive','-project','Preview.xcodeproj','-scheme','Preview','-destination',dest,'-archivePath',archive,'-derivedDataPath',producer/(label+'-build'),'SKIP_INSTALL=NO','BUILD_LIBRARY_FOR_DISTRIBUTION=YES','CODE_SIGNING_ALLOWED=NO'],producer)
    artifact=work/'relocated package';artifact.mkdir()
    xc=artifact/'MadLink.xcframework'
    run(['xcodebuild','-create-xcframework','-framework',archives[0]/'Products/Library/Frameworks/MadLink.framework','-framework',archives[1]/'Products/Library/Frameworks/MadLink.framework','-output',xc])
assert not producer.exists()
info=plistlib.loads((xc/'Info.plist').read_bytes());entries=info['AvailableLibraries']
assert len(entries)==2
assert {(e['SupportedPlatform'],e.get('SupportedPlatformVariant','')) for e in entries}=={('ios',''),('ios','simulator')}
for e in entries:
    assert e['SupportedArchitectures']==['arm64']
    framework=xc/e['LibraryIdentifier']/e['LibraryPath']
    assert (framework/'Headers/madlink_c.h').is_file()
    assert not (framework/'Headers/madlink.hpp').exists()
    assert (framework/'Modules/module.modulemap').is_file()
    assert (framework/'MadLink').read_bytes().startswith(b'!<arch>\n')
for name in ['LICENSE','THIRD_PARTY_NOTICES.md']:shutil.copyfile(root/name,artifact/name)
consumer=work/'independent consumer';consumer.mkdir()
for name in ['App.mm','Smoke.mm','Tests.mm']:shutil.copyfile(root/'ios'/name,consumer/name)
shutil.copytree(xc,consumer/'MadLink.xcframework');generate(consumer)
# Explicitly create only our own ephemeral simulator, never select attached hardware.
udid=subprocess.check_output(['xcrun','simctl','create','MadLinkSyntheticPreview','com.apple.CoreSimulator.SimDeviceType.iPhone-17','com.apple.CoreSimulator.SimRuntime.iOS-26-2'],text=True).strip()
try:
    run(['xcrun','simctl','boot',udid]);run(['xcrun','simctl','bootstatus',udid,'-b'])
    result=work/'result.xcresult'
    run(['xcodebuild','test','-project','Preview.xcodeproj','-scheme','Preview','-destination','platform=iOS Simulator,id='+udid,'-derivedDataPath',work/'consumer-build','-resultBundlePath',result,'CODE_SIGNING_ALLOWED=NO'],consumer)
    summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)],text=True))
    assert summary['passedTests']>=1 and summary['failedTests']==0 and summary['skippedTests']==0
finally:
    run(['xcrun','simctl','delete',udid])
assert not producer.exists()
(work/'evidence.json').write_text(json.dumps({'producer_removed':True,'simulator_arm64':True,'passed_tests':summary['passedTests'],'scope':'synthetic connect/send/written/close; no real network or physical device'}))
print('PASS: native ARM64 XCFramework and independent simulator App XCTest')
