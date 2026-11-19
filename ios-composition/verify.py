"""Opt-in local-only integration; no dependency fetch or tool installation here."""
import json, os, platform, plistlib, re, shutil, subprocess, sys, tarfile, tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'ios'))
from project import generate
from sdk_package import build_package
from tools import run, readable_archive, mark
from results import verify
PIN='4af77ffa464a48307e5ff2d95f10b835919d205b'
def main():
 if platform.system()!='Darwin' or platform.machine()!='arm64':raise SystemExit('NOT RUN: Apple ARM64 required')
 if len(sys.argv)!=2:raise ValueError('checkout required')
 source=Path(sys.argv[1]).resolve()
 def git(stage,*args):return run(['git','-C',source,*args],stage,capture=True,timeout=60).strip()
 assert git('git-pin','rev-parse','HEAD')==PIN
 assert git('git-origin','remote','get-url','origin')=='https://github.com/changyue1053/MadObs.git'
 assert not git('git-clean','status','--porcelain')
 # Build and inspect a fresh relocated package, without a nested OFF simulator.
 # The separate standalone workflow remains the mandatory OFF runtime gate.
 mark('START','core-package')
 try:
  _,xc=build_package(root)
 except BaseException:
  mark('FAIL','core-package');raise
 mark('PASS','core-package')
 base=root/'build/ios-composition';base.mkdir(parents=True,exist_ok=True)
 work=Path(tempfile.mkdtemp(prefix='check-',dir=base))
 sdk=run(['xcrun','--sdk','iphonesimulator','--show-sdk-path'],'sdk-path',capture=True).strip()
 assert run(['xcrun','--sdk','iphonesimulator','--show-sdk-version'],'sdk-version',capture=True).strip()=='26.2'
 assert (Path(sdk)/'usr/lib/libz.tbd').is_file()
 with tempfile.TemporaryDirectory(prefix='producer-',dir=work) as tmp:
  producer=Path(tmp);archive=producer/'source.tar';obs=producer/'source';obs.mkdir()
  run(['git','-C',source,'archive','--format=tar','-o',archive,PIN],'source-archive')
  with tarfile.open(archive) as tar:tar.extractall(obs,filter='data')
  build=producer/'build';prefix=producer/'installed'
  args=['cmake','-S',obs,'-B',build,'-G','Xcode','-DCMAKE_SYSTEM_NAME=iOS',f'-DCMAKE_OSX_SYSROOT={sdk}',
        '-DCMAKE_OSX_ARCHITECTURES=arm64','-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0',
        '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO',f'-DCMAKE_INSTALL_PREFIX={prefix}',
        '-DBUILD_TESTING=OFF','-DMADOBS_BUILD_RUNTIME=ON','-DMADOBS_BUILD_SHARED=OFF','-DMADOBS_BUILD_JNI=OFF',
        '-DMADOBS_PACKAGE_BORINGSSL=OFF','-DIMOBS_BORINGSSL_ROOT=','-DIMOBS_BORINGSSL_INCLUDE=',
        '-DIMOBS_BORINGSSL_CRYPTO_LIB=',f'-DZLIB_INCLUDE_DIR={sdk}/usr/include',f'-DZLIB_LIBRARY={sdk}/usr/lib/libz.tbd']
  run(args,'runtime-configure');run(['cmake','--build',build,'--config','Release','--target','imobs_core','--parallel','3'],'runtime-build')
  run(['cmake','--install',build,'--config','Release'],'runtime-install')
  installed=work/'relocated obs';shutil.move(prefix,installed)
 assert not producer.exists()
 readable_archive(installed/'lib/libmadobs_runtime.a')
 assert run(['xcrun','lipo','-archs',installed/'lib/libmadobs_runtime.a'],'runtime-architecture',capture=True).strip()=='arm64'
 consumer=work/'consumer';consumer.mkdir()
 for name in ['App.mm','Smoke.mm']:shutil.copyfile(root/'ios'/name,consumer/name)
 shutil.copyfile(root/'ios-composition/Tests.mm',consumer/'Tests.mm')
 shutil.copytree(xc,consumer/'MadLink.xcframework')
 # Only our optional header is staged. No upstream code becomes repository content.
 optional=consumer/'optional/madlink_madobs';optional.mkdir(parents=True)
 shutil.copyfile(root/'optional/madobs/queued_observer.hpp',optional/'queued_observer.hpp')
 generate(consumer)
 pbx=consumer/'Preview.xcodeproj/project.pbxproj';text=pbx.read_text()
 # Apply only to hosted test configs (two TEST_HOST entries), never App/core.
 insertion='"HEADER_SEARCH_PATHS" = ('+json.dumps(str(installed/'include'))+',"$(SRCROOT)/optional"); '
 text=text.replace('"TEST_HOST" =',insertion+'"TEST_HOST" =')
 text=text.replace('"-framework","XCTest"','"-framework","XCTest",'+json.dumps(str(installed/'lib/libmadobs_runtime.a'))+',"-lz"')
 assert text.count(str(installed/'lib/libmadobs_runtime.a'))==2
 assert str(producer) not in text
 pbx.write_text(text)
 udid=run(['xcrun','simctl','create','MadLinkObsSynthetic','com.apple.CoreSimulator.SimDeviceType.iPhone-17','com.apple.CoreSimulator.SimRuntime.iOS-26-2'],'sim-create',capture=True).strip()
 assert re.fullmatch(r'[0-9A-Fa-f-]{36}',udid)
 try:
  run(['xcrun','simctl','boot',udid],'sim-boot');run(['xcrun','simctl','bootstatus',udid,'-b'],'sim-ready')
  # Actual XCTest compilation enforces TARGET_OS_SIMULATOR and __arm64__.
  result=work/'result.xcresult'
  args=['-project','Preview.xcodeproj','-scheme','Preview','-destination','platform=iOS Simulator,id='+udid,
        '-derivedDataPath',work/'derived','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','-parallel-testing-enabled','NO',
        'CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','CODE_SIGNING_REQUIRED=NO',
        '-only-testing:SmokeTests/MadLinkCompositionTests/testSyntheticStatesReachRealRuntime']
  run(['xcodebuild','build-for-testing',*args],'on-build',cwd=consumer)
  run(['xcodebuild','test-without-building',*args,'-resultBundlePath',result],'on-test',cwd=consumer)
  summary=json.loads(run(['xcrun','xcresulttool','get','test-results','summary','--path',result],'on-summary',capture=True))
  tests=json.loads(run(['xcrun','xcresulttool','get','test-results','tests','--path',result],'on-cases',capture=True))
  verify(summary,tests)
 finally:run(['xcrun','simctl','delete',udid],'sim-delete')
 print('PASS: optional local composition; no network delivery or persistence claim')
try:main()
except Exception:
 print('FAIL: optional iOS composition validation');raise SystemExit(1) from None
