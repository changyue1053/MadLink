"""Build/package only. Never discovers devices or installs SDKs/accepts licenses."""
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile
from android_diagnostics import report, run_checked

stage='tool-preflight'
try:
    root = Path(__file__).resolve().parents[1]
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError('invalid CLI')
    p = SafeParser()
    p.add_argument('--sdk', required=True, type=Path)
    p.add_argument('--gradle', required=True, type=Path)
    a = p.parse_args()
    sdk, gradle = a.sdk.resolve(), a.gradle.resolve()
    for path in (gradle, sdk/'ndk/28.2.13676358/build/cmake/android.toolchain.cmake',
                 sdk/'cmake/3.22.1/bin/cmake', sdk/'platforms/android-35/android.jar',
                 sdk/'build-tools/35.0.0/zipalign'):
        if not path.is_file(): raise FileNotFoundError('required pinned tool unavailable')
    version = run_checked([gradle, '--version'], root, os.environ.copy(), stage,
                          timeout=30, capture_stdout=True)
    if '\nGradle 8.9\n' not in version: p.error('Gradle 8.9 required')
    base=root/'build/android-preview';base.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='check-',dir=base))
    env=os.environ.copy();env.update(ANDROID_HOME=str(sdk),ANDROID_SDK_ROOT=str(sdk))
    def run(args,cwd):
        run_checked(args,cwd,env,stage)
    def build(cwd,*tasks): run([gradle,'--no-daemon','--console=plain',*tasks],cwd)
    with tempfile.TemporaryDirectory(prefix='producer-',dir=work) as temp:
        producer=Path(temp)/'project'
        shutil.copytree(root/'android/producer',producer)
        core=producer/'module/core';core.mkdir()
        for name in ('madlink.cpp','madlink_c.cpp'): shutil.copyfile(root/'src'/name,core/name)
        for name in ('madlink.hpp','madlink_c.h'): shutil.copyfile(root/'include'/name,core/name)
        public=producer/'module/public';public.mkdir();shutil.copyfile(root/'include/madlink_c.h',public/'madlink_c.h')
        notices=producer/'module/src/main/resources/META-INF';notices.mkdir(parents=True)
        for name in ('LICENSE','THIRD_PARTY_NOTICES.md'): shutil.copyfile(root/name,notices/name)
        stage='producer-build'
        build(producer,':madlink:assembleRelease')
        artifact=work/'relocated package';artifact.mkdir()
        aar=artifact/'madlink.aar';shutil.copyfile(producer/'module/build/outputs/aar/madlink-release.aar',aar)
    assert not producer.exists()
    stage='aar-inspection'
    with zipfile.ZipFile(aar) as z:
        names=z.namelist()
        assert 'prefab/modules/madlink/include/madlink_c.h' in names
        assert 'prefab/modules/madlink/libs/android.arm64-v8a/libmadlink.a' in names
        assert not any(n.endswith('madlink.hpp') or n.endswith('.so') for n in names)
    consumer=work/'independent consumer';shutil.copytree(root/'android/consumer',consumer)
    libs=consumer/'module/libs';libs.mkdir();shutil.copyfile(aar,libs/'madlink.aar')
    stage='consumer-apk-build'
    build(consumer,':module:assembleDebug')
    stage='consumer-test-apk-build'
    build(consumer,':module:assembleDebugAndroidTest')
    apk=consumer/'module/build/outputs/apk/debug/module-debug.apk'
    stage='zip-alignment'
    run([sdk/'build-tools/35.0.0/zipalign','-c','-P','16','-v','4',apk],consumer)
    # Inspect actual final ELF LOAD alignment and uncompressed ZIP payload alignment.
    stage='elf-inspection'
    with zipfile.ZipFile(apk) as z, apk.open('rb') as f:
        native=[i for i in z.infolist() if i.filename.endswith('.so')]
        assert [i.filename for i in native]==['lib/arm64-v8a/libsmoke.so']
        for info in native:
            assert info.compress_type==zipfile.ZIP_STORED
            f.seek(info.header_offset);header=f.read(30)
            n,x=struct.unpack_from('<HH',header,26)
            assert (info.header_offset+30+n+x)%16384==0
            elf=z.read(info)
            assert elf[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',elf,18)[0]==183
            offset=struct.unpack_from('<Q',elf,32)[0]
            size,count=struct.unpack_from('<HH',elf,54)
            loads=0
            for i in range(count):
                pos=offset+i*size
                if struct.unpack_from('<I',elf,pos)[0]==1:
                    loads+=1;assert struct.unpack_from('<Q',elf,pos+48)[0]>=16384
            assert loads>0
    # Imported archive path must appear in the independent native link build.
    stage='dependency-inspection'
    files=list((consumer/'module/.cxx').rglob('build.ninja'))
    assert files
    text='\n'.join(f.read_text() for f in files)
    assert 'libmadlink.a' in text and str(producer) not in text and str(root/'include') not in text
    stage='evidence'
    (work/'evidence.json').write_text(json.dumps({'producer_removed':True,'aar_consumed':True,
     'abi':'arm64-v8a','elf_and_zip_16k':True,'runtime_executed':False,'device_test':'NOT RUN'},indent=2)+'\n')
    print('PASS Android ARM64 Prefab consumption and APK alignment; runtime NOT RUN')
except Exception as error:
    report(stage,error)
    raise SystemExit(1) from None
