"""Builds disposable native archives and executes one synthetic simulator XCTest."""
import json
from pathlib import Path
import shutil
from project import generate
from diagnostics import run
from sdk_package import build_package
try:
 root=Path(__file__).resolve().parents[1]
 work,xc=build_package(root)
 consumer=work/'independent consumer';consumer.mkdir()
 for name in ['App.mm','Smoke.mm','Tests.mm']:shutil.copyfile(root/'ios'/name,consumer/name)
 shutil.copytree(xc,consumer/'MadLink.xcframework');generate(consumer)
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
 finally:
     run(['xcrun','simctl','delete',udid],'sim-delete')
 (work/'evidence.json').write_text(json.dumps({'producer_removed':True,'simulator_arm64':True,'passed_tests':summary['passedTests'],'scope':'synthetic connect/send/written/close; no real network or physical device'}))
 print('PASS: native ARM64 XCFramework and independent simulator App XCTest')
except Exception as error:
 print('IOS FAIL: validation-or-tool-error')
 raise SystemExit(1) from None
