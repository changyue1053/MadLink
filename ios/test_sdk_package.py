"""Control-flow/inspection regression only; not Apple build/runtime evidence."""
import ast
import plistlib
import tempfile
from pathlib import Path
from unittest.mock import patch
import sdk_package

root=Path(__file__).resolve().parents[1]
for malformed in (False,True):
 with tempfile.TemporaryDirectory() as tmp:
  fixture=Path(tmp); calls=[]; producers=[]
  for directory,names in [('src',['madlink.cpp','madlink_c.cpp']),('include',['madlink.hpp','madlink_c.h'])]:
   (fixture/directory).mkdir()
   for name in names:(fixture/directory/name).write_text('synthetic fixture')
  for name in ['LICENSE','THIRD_PARTY_NOTICES.md']:(fixture/name).write_text('fixture')
  def fake_run(args,stage,**kwargs):
   calls.append(stage)
   assert 'simctl' not in args and 'test-without-building' not in args
   if stage=='version':return 'Xcode 26.2'
   if stage.startswith('archive-'):producers.append(kwargs['cwd'])
   if stage=='create-xcframework':
    xc=Path(args[-1]);xc.mkdir();entries=[]
    for label,variant in [('ios-arm64',''),('ios-arm64-simulator','simulator')]:
     entry={'LibraryIdentifier':label,'LibraryPath':'MadLink.framework','SupportedArchitectures':['arm64'],'SupportedPlatform':'ios'}
     if variant:entry['SupportedPlatformVariant']=variant
     entries.append(entry);f=xc/label/'MadLink.framework'
     (f/'Headers').mkdir(parents=True);(f/'Modules').mkdir()
     (f/'Headers/madlink_c.h').write_text('fixture');(f/'Modules/module.modulemap').write_text('fixture')
     (f/'MadLink').write_bytes(b'invalid' if malformed else b'!<arch>\n')
    (xc/'Info.plist').write_bytes(plistlib.dumps({'AvailableLibraries':entries}))
  with patch.object(sdk_package.platform,'system',return_value='Darwin'),patch.object(sdk_package.platform,'machine',return_value='arm64'),patch.object(sdk_package,'run',fake_run):
   rejected=False
   try:
    work,xc=sdk_package.build_package(fixture)
    assert xc.is_dir() and (xc.parent/'LICENSE').is_file()
   except AssertionError:
    rejected=True
   assert rejected==malformed
  assert calls==['version','archive-device','archive-simulator','create-xcframework']
  assert producers and all(not p.exists() for p in producers)
# Mandatory real runtime paths remain in both drivers, without nesting OFF in ON.
standalone=(root/'ios/verify.py').read_text();composition=(root/'ios-composition/verify.py').read_text()
ast.parse(standalone);ast.parse(composition)
assert 'work,xc=build_package(root)' in standalone
for stage in ['build-for-testing','test-without-building','test-summary']:
 assert "'"+stage+"'" in standalone
assert "summary['passedTests']>=1" in standalone
assert "root/'ios/verify.py'" not in composition
assert "_,xc=build_package(root)" in composition
assert '-only-testing:SmokeTests/MadLinkCompositionTests/testSyntheticStatesReachRealRuntime' in composition
assert 'verify(summary,tests)' in composition
print('PASS: mocked package inspection/deletion, invalid archive rejection, separate runtime gates; no Apple execution')
