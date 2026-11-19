"""Configuration and argv tests only, not Xcode or runtime evidence."""
import sys, tempfile, plistlib, re
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ios'))
import project_config as config
from project import generate
with tempfile.TemporaryDirectory(prefix='composition paths ') as tmp:
 root=Path(tmp);consumer=root/'consumer';consumer.mkdir();installed=root/'relocated obs'
 config.generate_composition(consumer,installed)
 text=(consumer/'Preview.xcodeproj/project.pbxproj').read_text()
 assert text.count('"path" = "lib/libmadobs_runtime.a"; "lastKnownFileType" = "archive.ar"; "sourceTree" = "MADOBS_PREFIX";')==1
 assert text.count('"MADOBS_PREFIX" = ')==2
 assert text.count('"HEADER_SEARCH_PATHS" = ')==2
 assert text.count('"-lz"')==2
 assert str(installed/'lib/libmadobs_runtime.a') not in text
 assert '\\"$(MADOBS_PREFIX)/include\\"' in text
 # Static library file reference is used by one build file and one framework phase.
 ref=re.search(r'"([A-F0-9]{24})" = \{ "isa" = "PBXFileReference"; "path" = "lib/libmadobs_runtime.a"',text)[1]
 build=re.search(r'"([A-F0-9]{24})" = \{ "isa" = "PBXBuildFile"; "fileRef" = "'+ref+'"',text)[1]
 assert text.count('"'+build+'"')==2
 # argv keeps paths with spaces as single elements and uses exact installed headers.
 xc=consumer/'MadLink.xcframework';frame=xc/'ios-arm64-simulator/MadLink.framework'
 (frame/'Headers').mkdir(parents=True);(frame/'Headers/madlink_c.h').touch()
 (xc/'Info.plist').write_bytes(plistlib.dumps({'AvailableLibraries':[{'SupportedPlatform':'ios','SupportedPlatformVariant':'simulator','SupportedArchitectures':['arm64'],'LibraryIdentifier':'ios-arm64-simulator'}]}))
 (installed/'include/madobs').mkdir(parents=True);(installed/'include/madobs/runtime.h').touch()
 platform=root/'Simulator platform';(platform/'Developer/Library/Frameworks/XCTest.framework').mkdir(parents=True)
 args=config.fixture_compile_args(consumer,installed,root/'SDK path',platform)
 assert args[0:4]==['xcrun','--sdk','iphonesimulator','clang++']
 assert args[args.index('-target')+1]=='arm64-apple-ios15.0-simulator'
 assert installed/'include' in args and args[-1]==consumer/'Tests.mm'
 assert '-fsyntax-only' in args and '-fobjc-arc' in args
print('PASS: explicit static library reference, test-only settings, quoted prefix and fixture argv')
# Hashes measured against public 7bb583cb's unchanged default generator outputs.
import hashlib
expected={False:['9a3bab6a7c814eaf2c214cc10ce9046be567b4da73509315b35f3846acc127bd','79c033ec02e18f1a4aa06a92b5e6c382f81fef7b687e575d03e2fc42a61db338'],True:['f7f5dea738bfb12d5c5a47c2f9a387ceed85dfbc55c83179d1345784196409bf','268d1b0f2a4f9d12376d014f2d7d237eb00cb913d6901d79761eebdc1926e04a']}
with tempfile.TemporaryDirectory() as tmp:
 for producer,hashes in expected.items():
  folder=Path(tmp)/str(producer);folder.mkdir();generate(folder,producer)
  assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob('*')) if p.is_file()]==hashes
print('PASS: default standalone/producer project and scheme unchanged from public baseline')
