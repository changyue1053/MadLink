#!/usr/bin/env python3
"""Opt-in, offline, preinstalled OpenHarmony SDK cross-link gate. Never runs target code."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import shlex
import struct
import subprocess
import tempfile
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
VERSION = '6.0.0.47'
REQUIRED = {'ml_create_v1', 'ml_connect_v1', 'ml_send_v1', 'ml_tick_v1',
            'ml_cancel_v1', 'ml_close_v1', 'ml_next_event_v1', 'ml_destroy_v1'}


def require(value):
    if not value:
        raise ValueError('validation failed')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def manifest(sdk):
    """Bind every installed file and internal symlink, not merely a version string."""
    entries = {}
    for p in sorted(sdk.rglob('*')):
        name = p.relative_to(sdk).as_posix()
        if p.is_symlink():
            require(not Path(os.readlink(p)).is_absolute())
            require(p.resolve().is_relative_to(sdk.resolve()) and p.exists())
            entries[name] = {'symlink': os.readlink(p)}
        elif p.is_file():
            entries[name] = {'sha256': digest(p)}
        else:
            require(p.is_dir())
    require(entries)
    return entries


def receipt(sdk, archive, path, trusted_hash):
    # trusted_hash is an out-of-band reviewed receipt identity, NOT a hash generated here.
    require(re.fullmatch('[0-9a-f]{64}', trusted_hash) and digest(path) == trusted_hash)
    data = json.loads(path.read_text())
    require(data['schema'] == 1 and data['version'] == VERSION and data['api'] == 20)
    require(data['component'] == 'native' and data['provenance_verified'] is True)
    # No fetching. The URL is recorded provenance; this allowlist alone proves nothing.
    url = urlparse(data['official_archive_url'])
    require(url.scheme == 'https' and url.hostname == 'repo.huaweicloud.com'
            and url.path.startswith('/openharmony/') and not url.username and not url.password)
    require(re.fullmatch('[0-9a-f]{64}', data['official_archive_sha256']))
    require(digest(archive) == data['official_archive_sha256'])
    require(data['native_files'] == manifest(sdk))
    metadata = json.loads((sdk / 'oh-uni-package.json').read_text())
    require(metadata['version'] == VERSION and str(metadata['apiVersion']) == '20'
            and metadata['path'] == 'native')
    for rel in ('build/cmake/ohos.toolchain.cmake', 'llvm/bin/clang',
                'llvm/bin/clang++', 'llvm/bin/llvm-nm', 'llvm/bin/llvm-readelf'):
        require((sdk / rel).is_file())
    require((sdk / 'sysroot').is_dir())


def elf(data):
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01')
    require(struct.unpack_from('<HH', data, 16) == (3, 183))
    start = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    require(start >= 64 and size == 56 and 1 <= count <= 128 and start + size * count <= len(data))
    loads = 0
    for i in range(count):
        kind, flags, offset, va, _, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', data, start + i * size)
        require(kind != 3)  # Shared link fixture, not an executable/interpreter.
        if kind == 1:
            loads += 1
            require(align >= 4096 and not align & (align - 1) and (va - offset) % align == 0)
            require(filesz <= memsz and offset + filesz <= len(data) and flags & 3 != 3)
    require(loads)


PRODUCER = '''cmake_minimum_required(VERSION 3.20)
project(MadLinkOHOS LANGUAGES C CXX)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "OHOS" OR NOT OHOS_ARCH STREQUAL "arm64-v8a")
 message(FATAL_ERROR "OHOS ARM64 required")
endif()
option(MADLINK_WITH_MADOBS "Not supported in this standalone gate" OFF)
if(MADLINK_WITH_MADOBS)
 message(FATAL_ERROR "Standalone only")
endif()
add_library(madlink STATIC src/madlink.cpp src/madlink_c.cpp)
set_target_properties(madlink PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_compile_features(madlink PRIVATE cxx_std_17)
target_include_directories(madlink PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include> $<INSTALL_INTERFACE:include>)
install(TARGETS madlink EXPORT MadLinkTargets ARCHIVE DESTINATION lib)
install(FILES include/madlink_c.h DESTINATION include)
install(FILES LICENSE THIRD_PARTY_NOTICES.md DESTINATION share/madlink)
install(EXPORT MadLinkTargets NAMESPACE MadLink:: DESTINATION lib/cmake/MadLink)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/MadLinkConfig.cmake" "include(\\"\\${CMAKE_CURRENT_LIST_DIR}/MadLinkTargets.cmake\\")\\n")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/MadLinkConfig.cmake" DESTINATION lib/cmake/MadLink)
'''
CONSUMER = '''cmake_minimum_required(VERSION 3.20)
project(IndependentConsumer LANGUAGES C CXX)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "OHOS" OR NOT OHOS_ARCH STREQUAL "arm64-v8a")
 message(FATAL_ERROR "OHOS ARM64 required")
endif()
find_package(MadLink CONFIG REQUIRED PATHS "${SDK_PREFIX}/lib/cmake/MadLink" NO_DEFAULT_PATH)
add_library(consumer SHARED consumer.c)
set_target_properties(consumer PROPERTIES LINKER_LANGUAGE CXX)
target_compile_features(consumer PRIVATE c_std_11)
target_link_libraries(consumer PRIVATE MadLink::madlink)
target_link_options(consumer PRIVATE -Wl,-z,defs)
'''


def cache(path, sdk):
    values = dict(re.findall(r'^([^#/:][^:=]*):[^=]+=(.*)$', path.read_text(), re.M))
    require(values.get('OHOS_ARCH') == 'arm64-v8a' and values.get('OHOS_STL') == 'c++_shared')
    require(Path(values.get('CMAKE_TOOLCHAIN_FILE', '')).resolve() == sdk / 'build/cmake/ohos.toolchain.cmake')
    for lang, tool in [('C', 'clang'), ('CXX', 'clang++')]:
        key = 'CMAKE_' + lang + '_COMPILER'
        if key in values:
            require(Path(values[key]).resolve() == (sdk / 'llvm/bin' / tool).resolve())


def compiler_proof(build, sdk, sources):
    """Mandatory generated compiler records + actual command database; no host inference."""
    for language, driver in [('C', 'clang'), ('CXX', 'clang++')]:
        records = list((build / 'CMakeFiles').glob('*/CMake' + language + 'Compiler.cmake'))
        require(len(records) == 1)
        matches = re.findall(r'set\(CMAKE_' + language + r'_COMPILER "([^"\n]+)"\)', records[0].read_text())
        require(len(matches) == 1)
        require(Path(matches[0]).resolve() == (sdk / 'llvm/bin' / driver).resolve())
    database = build / 'compile_commands.json'
    require(database.stat().st_size <= 1024 * 1024)
    commands = json.loads(database.read_text())
    check_commands(commands, build, sdk, sources)


def check_commands(commands, build, sdk, sources):
    require(isinstance(commands, list) and len(commands) == len(sources))
    expected = {p.resolve() for p in sources}
    seen = set()
    for entry in commands:
        require(isinstance(entry, dict) and isinstance(entry.get('directory'), str)
                and isinstance(entry.get('file'), str))
        directory = Path(entry['directory']).resolve()
        require(directory.is_relative_to(build.resolve()))
        source = (directory / entry['file']).resolve()
        require(source in expected and source not in seen)
        seen.add(source)
        args = entry.get('arguments')
        if args is None:
            require(isinstance(entry.get('command'), str))
            args = shlex.split(entry['command'])
        require(isinstance(args, list) and args and all(isinstance(a, str) for a in args))
        driver = 'clang' if source.suffix == '.c' else 'clang++'
        require(source.suffix in ('.c', '.cpp'))
        require(Path(args[0]).name == driver and Path(args[0]).is_absolute())
        require(Path(args[0]).resolve() == (sdk / 'llvm/bin' / driver).resolve())
        require(not any(a.startswith(('@', '-x=', '-target=', '-isysroot', '-mcpu='))
                        or a in ('-x', '-arch', '-m32', '-m64', '-Xclang', '-Xpreprocessor') for a in args))
        def values(option, alternate=None):
            result = []
            for i, arg in enumerate(args[1:], 1):
                if arg.startswith(option + '='):
                    result.append(arg[len(option) + 1:])
                elif arg == option or (alternate and arg == alternate):
                    require(i + 1 < len(args))
                    result.append(args[i + 1])
            return result
        require(values('-march') in ([], ['armv8-a']))
        require(values('--target', '-target') == ['aarch64-linux-ohos'])
        roots = values('--sysroot')
        require(len(roots) == 1 and Path(roots[0]).resolve() == (sdk / 'sysroot').resolve())
        compiled = values('-c')
        require(len(compiled) == 1 and (directory / compiled[0]).resolve() == source)
        outputs = values('-o')
        require(len(outputs) == 1 and (directory / outputs[0]).resolve().is_relative_to(build.resolve()))
    require(seen == expected)


def trusted_cmake(cmake, sdk):
    # This fixed bundled path and all resolved files were included in the reviewed receipt.
    expected = sdk / 'build-tools/cmake/bin/cmake'
    require(cmake == expected.resolve() and cmake.is_relative_to(sdk.resolve()))
    require(cmake.is_file() and os.access(cmake, os.X_OK))


def run_gate(args):
    require(args.run and platform.system() == 'Linux' and platform.machine() == 'x86_64')
    require(re.fullmatch('[0-9a-f]{40}', args.expected_sha))
    sdk, archive, receipt_path, cmake = (Path(x).resolve() for x in (args.sdk, args.archive, args.receipt, args.cmake))
    # Deliberately no network/download/extraction/install/license step.
    receipt(sdk, archive, receipt_path, args.receipt_sha256)
    trusted_cmake(cmake, sdk)
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == args.expected_sha)
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT))
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C'}
    stage = 'prepare'
    try:
        with tempfile.TemporaryDirectory(prefix='madlink-ohos-') as tmp:
            work = Path(tmp)
            def command(argv, label):
                nonlocal stage
                stage = label
                with tempfile.TemporaryFile() as log:
                    subprocess.run([str(v) for v in argv], env=env, cwd=work, stdout=log, stderr=log, check=True, timeout=600)
                print('PASS: ' + label)
            def configure(source, build, *extra):
                command([cmake, '-S', source, '-B', build, '-G', 'Unix Makefiles',
                         '-DCMAKE_TOOLCHAIN_FILE=' + str(sdk / 'build/cmake/ohos.toolchain.cmake'),
                         '-DOHOS_ARCH=arm64-v8a', '-DOHOS_PLATFORM=OHOS', '-DOHOS_STL=c++_shared',
                         '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', *extra], 'configure')
                cache(build / 'CMakeCache.txt', sdk)
            producer = work / 'producer'
            source = producer / 'source'
            for relative in ('src/madlink.cpp', 'src/madlink_c.cpp', 'include/madlink.hpp', 'include/madlink_c.h', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
                dest = source / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, dest)
            (source / 'CMakeLists.txt').write_text(PRODUCER)
            prefix = producer / 'installed'
            configure(source, producer / 'build', '-DCMAKE_INSTALL_PREFIX=' + str(prefix), '-DMADLINK_WITH_MADOBS=OFF')
            command([cmake, '--build', producer / 'build', '--parallel', '2'], 'native-build')
            stage = 'producer-compiler-proof'
            compiler_proof(producer / 'build', sdk, [source / 'src/madlink.cpp', source / 'src/madlink_c.cpp'])
            command([cmake, '--install', producer / 'build'], 'local-stage')
            moved = work / 'relocated sdk'
            shutil.move(prefix, moved)
            shutil.rmtree(producer)
            require(not producer.exists())
            for p in (moved / 'lib/cmake').rglob('*.cmake'):
                require(str(producer) not in p.read_text() and str(ROOT) not in p.read_text())
            require((moved / 'lib/libmadlink.a').read_bytes()[:8] == b'!<arch>\n')
            require((moved / 'include/madlink_c.h').read_bytes() == (ROOT / 'include/madlink_c.h').read_bytes())
            consumer = work / 'independent consumer'
            consumer.mkdir()
            (consumer / 'CMakeLists.txt').write_text(CONSUMER)
            shutil.copyfile(ROOT / 'tests/ohos/consumer.c', consumer / 'consumer.c')
            build = work / 'consumer-build'
            configure(consumer, build, '-DSDK_PREFIX=' + str(moved))
            command([cmake, '--build', build, '--parallel', '2'], 'independent-link')
            stage = 'consumer-compiler-proof'
            compiler_proof(build, sdk, [consumer / 'consumer.c'])
            stage = 'elf-symbols'
            so = build / 'libconsumer.so'
            elf(so.read_bytes())
            def output(tool, *options):
                return subprocess.check_output([str(sdk / 'llvm/bin' / tool), *map(str, options)], stderr=subprocess.DEVNULL, env=env, timeout=60, text=True)
            symbols = {line.split()[-1] for line in output('llvm-nm', '--defined-only', '--dynamic', so).splitlines() if line.split()}
            require(REQUIRED | {'madlink_ohos_link_probe'} <= symbols)
            dynamic = output('llvm-readelf', '--dynamic', so)
            needed = set(re.findall(r'\(NEEDED\).*?\[([^]]+)\]', dynamic))
            require(needed and needed <= {'libc.so', 'libm.so', 'libdl.so', 'libc++_shared.so'})
            require(not any(x in dynamic for x in ('(RPATH)', '(RUNPATH)', '(TEXTREL)')))
            require(not producer.exists())
        print('PASS: OpenHarmony ARM64 relocated native cross-link ONLY; no execution')
    except Exception:
        print('FAIL: ' + stage)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    for name in ('sdk', 'archive', 'receipt', 'receipt-sha256', 'expected-sha', 'cmake'):
        parser.add_argument('--' + name, required=True)
    try:
        run_gate(parser.parse_args())
    except Exception:
        print('FAIL: OpenHarmony opt-in gate; no raw diagnostics')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
