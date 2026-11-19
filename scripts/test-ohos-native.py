#!/usr/bin/env python3
"""Local structural/negative tests only; no SDK authenticity or cross-build claim."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('gate', Path(__file__).with_name('check-ohos-native.py'))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def elf():
    data = bytearray(120)
    data[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HH', data, 16, 3, 183)
    struct.pack_into('<Q', data, 32, 64)
    struct.pack_into('<HH', data, 54, 56, 1)
    struct.pack_into('<IIQQQQQQ', data, 64, 1, 5, 0, 0, 0, 120, 120, 4096)
    return data


class Tests(unittest.TestCase):
    def test_elf(self):
        gate.elf(elf())

    def test_elf_rejects(self):
        for offset, fmt, value in [(0,'B',0), (16,'H',2), (18,'H',62), (54,'H',55),
                                   (56,'H',0), (64,'I',3), (68,'I',7), (80,'Q',1),
                                   (96,'Q',121), (104,'Q',119), (112,'Q',2048)]:
            data = elf()
            struct.pack_into('<' + fmt, data, offset, value)
            with self.assertRaises(ValueError):
                gate.elf(data)
        for length in (0,63,119):
            with self.assertRaises(ValueError):
                gate.elf(elf()[:length])

    def test_receipt_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdk = root/'native'
            for name in ('build/cmake/ohos.toolchain.cmake', 'llvm/bin/clang', 'llvm/bin/clang++', 'llvm/bin/llvm-nm', 'llvm/bin/llvm-readelf'):
                p = sdk/name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('SYNTHETIC NONEXECUTABLE TEST FILE')
            (sdk/'sysroot').mkdir()
            (sdk/'oh-uni-package.json').write_text(json.dumps({'version':gate.VERSION, 'apiVersion':20, 'path':'native'}))
            archive = root/'synthetic.archive'
            archive.write_text('NOT AN SDK')
            receipt = root/'receipt.json'
            data = {'schema':1,'version':gate.VERSION,'api':20,'component':'native','provenance_verified':True,
                    'official_archive_url':'https://repo.huaweicloud.com/openharmony/synthetic-test-only',
                    'official_archive_sha256':gate.digest(archive),'native_files':gate.manifest(sdk)}
            receipt.write_text(json.dumps(data))
            trusted = gate.digest(receipt)
            gate.receipt(sdk,archive,receipt,trusted)  # Integrity mechanics only, caller attestation is assumed.
            with self.assertRaises(ValueError): gate.receipt(sdk,archive,receipt,'0'*64)
            (sdk/'llvm/bin/clang').write_text('changed')
            with self.assertRaises(ValueError): gate.receipt(sdk,archive,receipt,trusted)
            for key, value in [('api',19), ('provenance_verified',False), ('official_archive_url','https://example.com/sdk')]:
                broken = dict(data)
                broken[key] = value
                receipt.write_text(json.dumps(broken))
                with self.assertRaises(ValueError): gate.receipt(sdk,archive,receipt,gate.digest(receipt))

    def test_external_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sdk = root/'native'
            sdk.mkdir()
            (root/'external').write_text('outside')
            (sdk/'escape').symlink_to(root/'external')
            with self.assertRaises(ValueError): gate.manifest(sdk)

    def commands(self):
        return [dict(directory='/build', file='/source/consumer.c', arguments=[
            '/sdk/llvm/bin/clang', '--target=aarch64-linux-ohos', '--sysroot=/sdk/sysroot',
            '-o', 'consumer.o', '-c', '/source/consumer.c'])]

    def verify_commands(self, commands):
        gate.check_commands(commands, Path('/build'), Path('/sdk'), [Path('/source/consumer.c')])

    def test_actual_command_forms(self):
        import shlex
        self.verify_commands(self.commands())
        commands = self.commands()
        commands[0]['command'] = shlex.join(commands[0].pop('arguments'))
        self.verify_commands(commands)
        commands = self.commands()
        commands[0]['arguments'][1:3] = ['-target','aarch64-linux-ohos','--sysroot','/sdk/sysroot','-march=armv8-a']
        self.verify_commands(commands)
        commands = self.commands()
        commands[0]['file'] = '/source/core.cpp'
        commands[0]['arguments'][0] += '++'
        commands[0]['arguments'][-1] = '/source/core.cpp'
        gate.check_commands(commands,Path('/build'),Path('/sdk'),[Path('/source/core.cpp')])

    def test_command_rejections(self):
        for mode in ('compiler','target','sysroot','source','output','missing','duplicate','response','override','foreigncpu','language'):
            commands = self.commands()
            args = commands[0]['arguments']
            if mode == 'compiler': args[0] = '/usr/bin/clang'
            elif mode == 'target': args[1] = '--target=aarch64-linux-android24'
            elif mode == 'sysroot': args[2] = '--sysroot=/other'
            elif mode == 'source': commands[0]['file'] = '/source/foreign.c'
            elif mode == 'output': args[4] = '/outside/file.o'
            elif mode == 'missing': del args[1]
            elif mode == 'duplicate': args.append('--target=aarch64-linux-ohos')
            elif mode == 'response': args.append('@hidden')
            elif mode == 'override': args.extend(['-Xclang','hidden'])
            elif mode == 'foreigncpu': args.append('-march=native')
            else: args[0] += '++'
            with self.assertRaises(ValueError): self.verify_commands(commands)

    def test_generated_records_without_compiler_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build, sdk = root/'build', root/'sdk'
            records = build/'CMakeFiles/3.22.1'
            records.mkdir(parents=True)
            (build/'CMakeCache.txt').write_text('OHOS_ARCH:STRING=arm64-v8a\nOHOS_STL:STRING=c++_shared\nCMAKE_TOOLCHAIN_FILE:FILEPATH='+str(sdk/'build/cmake/ohos.toolchain.cmake')+'\n')
            gate.cache(build/'CMakeCache.txt', sdk)
            for language, driver in [('C','clang'),('CXX','clang++')]:
                (records/('CMake'+language+'Compiler.cmake')).write_text('set(CMAKE_'+language+'_COMPILER "'+str(sdk/'llvm/bin'/driver)+'")\n')
            commands = self.commands()
            commands[0]['directory'] = str(build)
            commands[0]['arguments'][0] = str(sdk/'llvm/bin/clang')
            commands[0]['arguments'][2] = '--sysroot='+str(sdk/'sysroot')
            (build/'compile_commands.json').write_text(json.dumps(commands))
            gate.compiler_proof(build,sdk,[Path('/source/consumer.c')])
            (records/'CMakeCXXCompiler.cmake').write_text('set(CMAKE_CXX_COMPILER "/usr/bin/clang++")')
            with self.assertRaises(ValueError): gate.compiler_proof(build,sdk,[Path('/source/consumer.c')])
            (records/'CMakeCXXCompiler.cmake').unlink()
            with self.assertRaises(ValueError): gate.compiler_proof(build,sdk,[Path('/source/consumer.c')])

    def test_only_manifest_bound_cmake(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdk = Path(tmp)/'native'
            bundled = sdk/'build-tools/cmake/bin/cmake'
            bundled.parent.mkdir(parents=True)
            bundled.write_text('synthetic not executed')
            bundled.chmod(0o700)
            gate.trusted_cmake(bundled,sdk)
            with self.assertRaises(ValueError): gate.trusted_cmake(Path('/usr/bin/cmake'),sdk)
            with self.assertRaises(ValueError): gate.trusted_cmake(Path(tmp)/'cmake',sdk)
            (sdk/'absolute').symlink_to(bundled)
            with self.assertRaises(ValueError): gate.manifest(sdk)

    def test_cmake_scope(self):
        self.assertIn('MADLINK_WITH_MADOBS',gate.PRODUCER)
        self.assertIn('NO_DEFAULT_PATH',gate.CONSUMER)
        self.assertIn('MadLink::madlink',gate.CONSUMER)
        self.assertIn('LINKER_LANGUAGE CXX',gate.CONSUMER)
        self.assertNotIn('add_subdirectory',gate.PRODUCER)
        self.assertNotIn('optional/',gate.PRODUCER)
        self.assertIn('include("\\${CMAKE_CURRENT_LIST_DIR}',gate.PRODUCER.replace('\\"','"'))

    def test_no_opt_in_rejects_before_receipt_or_command(self):
        from types import SimpleNamespace
        with patch.object(gate,'receipt',side_effect=AssertionError('must not run')):
            with self.assertRaises(ValueError): gate.run_gate(SimpleNamespace(run=False))

    def test_fixed_failure_output(self):
        with patch('sys.argv',['gate','--sdk','unused','--archive','unused','--receipt','unused',
                              '--receipt-sha256','secret','--expected-sha','secret','--cmake','unused']):
            out = io.StringIO()
            with contextlib.redirect_stdout(out): self.assertEqual(gate.main(),1)
            self.assertEqual(out.getvalue(),'FAIL: OpenHarmony opt-in gate; no raw diagnostics\n')


if __name__ == '__main__':
    unittest.main()
