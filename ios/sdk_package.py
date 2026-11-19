"""Build/inspect relocated SDK only. Never executes or claims a runtime test."""
from pathlib import Path
import platform
import plistlib
import shutil
import tempfile
from project import generate
from diagnostics import run

def build_package(root):
 if platform.system()!='Darwin' or platform.machine()!='arm64':
     raise SystemExit('NOT RUN: Apple ARM64 host required')
 if 'Xcode 26.2' not in run(['xcodebuild','-version'],'version',capture=True,timeout=30):
     raise SystemExit('NOT RUN: pinned Xcode 26.2 required')
 base=root/'build/ios-preview';base.mkdir(parents=True,exist_ok=True)
 work=Path(tempfile.mkdtemp(prefix='check-',dir=base))
 with tempfile.TemporaryDirectory(prefix='producer-',dir=work) as tmp:
     producer=Path(tmp)
     for directory,names in [('src',['madlink.cpp','madlink_c.cpp']),('include',['madlink.hpp','madlink_c.h'])]:
         for name in names:shutil.copyfile(root/directory/name,producer/name)
     (producer/'module.modulemap').write_text('framework module MadLink { umbrella header "madlink_c.h" export * module * { export * } }\n')
     generate(producer,True)
     archives=[]
     for label,dest in [('device','generic/platform=iOS'),('simulator','generic/platform=iOS Simulator')]:
         archive=producer/(label+'.xcarchive');archives.append(archive)
         run(['xcodebuild','archive','-project','Preview.xcodeproj','-scheme','Preview','-destination',dest,'-archivePath',archive,'-derivedDataPath',producer/(label+'-build'),'SKIP_INSTALL=NO','BUILD_LIBRARY_FOR_DISTRIBUTION=YES','CODE_SIGNING_ALLOWED=NO'],'archive-'+label,cwd=producer)
     artifact=work/'relocated package';artifact.mkdir()
     xc=artifact/'MadLink.xcframework'
     run(['xcodebuild','-create-xcframework','-framework',archives[0]/'Products/Library/Frameworks/MadLink.framework','-framework',archives[1]/'Products/Library/Frameworks/MadLink.framework','-output',xc],'create-xcframework')
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
 return work,xc
