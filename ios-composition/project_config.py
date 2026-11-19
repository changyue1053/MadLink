"""Explicit optional test target configuration, not serialized project surgery."""
import plistlib
from pathlib import Path
from project import generate

def generate_composition(consumer,installed):
 generate(consumer,test_settings={
  'MADOBS_PREFIX':str(installed),
  # Quoting here survives build-setting expansion of the deliberately spaced prefix.
  'HEADER_SEARCH_PATHS':['$(inherited)','"$(MADOBS_PREFIX)/include"','"$(SRCROOT)/optional"'],
  # Explicit absolute archive operand after build-setting expansion. No custom
  # PBX source-tree lookup, -l name search, or duplicate archive reference.
  'OTHER_LDFLAGS':['-lc++','-framework','Foundation','-framework','XCTest',
                   '"$(MADOBS_PREFIX)/lib/libmadobs_runtime.a"','-lz'],
 })

def fixture_compile_args(consumer,installed,sdk,platform_dir):
 consumer=Path(consumer);installed=Path(installed)
 xc=consumer/'MadLink.xcframework'
 entries=plistlib.loads((xc/'Info.plist').read_bytes())['AvailableLibraries']
 matches=[e for e in entries if e['SupportedPlatform']=='ios' and e.get('SupportedPlatformVariant')=='simulator' and e['SupportedArchitectures']==['arm64']]
 assert len(matches)==1
 framework_dir=xc/matches[0]['LibraryIdentifier']
 assert (framework_dir/'MadLink.framework/Headers/madlink_c.h').is_file()
 assert (installed/'include/madobs/runtime.h').is_file()
 apple_frameworks=Path(platform_dir)/'Developer/Library/Frameworks'
 assert (apple_frameworks/'XCTest.framework').is_dir()
 return ['xcrun','--sdk','iphonesimulator','clang++','-fsyntax-only','-x','objective-c++',
         '-std=c++17','-fobjc-arc','-fmodules','-fcxx-exceptions',
         '-target','arm64-apple-ios15.0-simulator','-isysroot',sdk,
         '-F',framework_dir,'-F',apple_frameworks,
         '-I',installed/'include','-I',consumer/'optional',
         '-fmodules-cache-path='+str(consumer/'fixture-module-cache'),consumer/'Tests.mm']
