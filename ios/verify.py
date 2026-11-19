"""Builds disposable native archives and executes the requested synthetic simulator XCTest suite."""
import argparse
import json
from pathlib import Path
import shutil
from project import generate
from diagnostics import run
from sdk_package import build_package
from session_results import verify_session_results
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--session-acceptance',action='store_true')
args=parser.parse_args()
try:
 root=Path(__file__).resolve().parents[1]
 work,xc=build_package(root)
 consumer=work/'independent consumer';consumer.mkdir()
 for name in ['App.mm','Smoke.mm','Tests.mm']:shutil.copyfile(root/'ios'/name,consumer/name)
 shutil.copytree(xc,consumer/'MadLink.xcframework')
 mobile_sources=()
 if args.session_acceptance:
     shutil.copyfile(root/'consumers/session_lifecycle/main.c',consumer/'SessionLifecycle.inc')
     shutil.copyfile(root/'ios/SessionTests.mm',consumer/'SessionTests.mm')
     # Compile the exact host fixture as C, with only an entry point/header spelling shim.
     (consumer/'SessionLifecycle.c').write_text(
         '#define MADLINK_SESSION_XCTEST 1\n#define main madlinkSessionAcceptance\n'
         '#include "SessionLifecycle.inc"\n')
     mobile_sources=('SessionTests.mm','SessionLifecycle.c')
 generate(consumer,test_sources=mobile_sources)
 # Explicitly create only our own ephemeral simulator, never select attached hardware.
 udid=run(['xcrun','simctl','create','MadLinkSyntheticPreview','com.apple.CoreSimulator.SimDeviceType.iPhone-17','com.apple.CoreSimulator.SimRuntime.iOS-26-2'],'sim-create',capture=True,timeout=60).strip()
 try:
     run(['xcrun','simctl','boot',udid],'sim-boot');run(['xcrun','simctl','bootstatus',udid,'-b'],'sim-ready')
     result=work/'result.xcresult'
     common=['-project','Preview.xcodeproj','-scheme','Preview','-destination','platform=iOS Simulator,id='+udid,
             '-derivedDataPath',work/'consumer-build','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES',
             '-parallel-testing-enabled','NO','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','CODE_SIGNING_REQUIRED=NO']
     run(['xcodebuild','build-for-testing',*common],'build-for-testing',cwd=consumer)
     run(['xcodebuild','test-without-building',*common,'-resultBundlePath',result],'test-without-building',cwd=consumer)
     summary=json.loads(run(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)],'test-summary',capture=True,timeout=60))
     assert summary['passedTests']>=1 and summary['failedTests']==0 and summary['skippedTests']==0
     if args.session_acceptance:
         cases=json.loads(run(['xcrun','xcresulttool','get','test-results','tests','--path',str(result)],'test-cases',capture=True,timeout=60))
         verify_session_results(summary,cases)
 finally:
     run(['xcrun','simctl','delete',udid],'sim-delete')
 (work/'evidence.json').write_text(json.dumps({'producer_removed':True,'simulator_arm64':True,'passed_tests':summary['passedTests'],'scope':('shared 32-cycle C ABI session recovery; synthetic only' if args.session_acceptance else 'synthetic connect/send/written/close; no real network or physical device')}))
 if args.session_acceptance:print('PASS: testSyntheticLifecycle and testInstalledSessionRecovery32Cycles')
 print('PASS: native ARM64 XCFramework and independent simulator App XCTest')
except Exception as error:
 print('IOS FAIL: validation-or-tool-error')
 raise SystemExit(1) from None
