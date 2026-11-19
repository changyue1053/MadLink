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
 assert '"sourceTree" = "MADOBS_PREFIX"' not in text
 assert '"path" = "lib/libmadobs_runtime.a"' not in text
 assert text.count('"MADOBS_PREFIX" = ')==2
 assert text.count('"HEADER_SEARCH_PATHS" = ')==2
 assert text.count('"-lz"')==2
 assert text.count('lib/libmadobs_runtime.a')==2
 assert '\\"$(MADOBS_PREFIX)/include\\"' in text
 # Verify the quoted operand survives substitution/tokenization with spaces.
 import shlex
 captured={}
 def capture(*args,**kwargs):captured.update(kwargs)
 with patch.object(config,'generate',capture):config.generate_composition(consumer,installed)
 flags=captured['test_settings']['OTHER_LDFLAGS']
 expanded=' '.join(flags).replace('$(MADOBS_PREFIX)',str(installed))
 tokens=shlex.split(expanded)
 assert tokens.count(str(installed/'lib/libmadobs_runtime.a'))==1
 assert 'test_libraries' not in captured
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
print('PASS: single quoted archive operand, test-only settings, spaced prefix and fixture argv')
# Hashes measured against public 7bb583cb's unchanged default generator outputs.
import hashlib
expected={False:['9a3bab6a7c814eaf2c214cc10ce9046be567b4da73509315b35f3846acc127bd','79c033ec02e18f1a4aa06a92b5e6c382f81fef7b687e575d03e2fc42a61db338'],True:['f7f5dea738bfb12d5c5a47c2f9a387ceed85dfbc55c83179d1345784196409bf','268d1b0f2a4f9d12376d014f2d7d237eb00cb913d6901d79761eebdc1926e04a']}
with tempfile.TemporaryDirectory() as tmp:
 for producer,hashes in expected.items():
  folder=Path(tmp)/str(producer);folder.mkdir();generate(folder,producer)
  assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob('*')) if p.is_file()]==hashes
print('PASS: default standalone/producer project and scheme unchanged from public baseline')
