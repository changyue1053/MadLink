"""Closed launch authority for the pinned, disposable Xcode project."""
import hashlib
import os
from pathlib import Path
import plistlib
import re
import stat
import struct

import binding

XCODE_APP = "/Applications/Xcode_26.2.app"
DEVELOPER = XCODE_APP + "/Contents/Developer"
XCODE_ID = "com.apple.dt.Xcode"
PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
TOOLS = {"xcodebuild": DEVELOPER + "/usr/bin/xcodebuild",
         "xcrun": "/usr/bin/xcrun", "codesign": "/usr/bin/codesign"}
PROJECT = "Preview.xcodeproj"
SCHEME = "xcshareddata/xcschemes/Preview.xcscheme"
LEGACY_SCHEME_HASH = "e50f8ba280e12b8526b31c83ba3b6607e955439c11cef601ebe82d4ad0946432"
GRAPH = {
    "project.pbxproj": "0b9af8524b3b8c1644002e7c1a6ba50b94ec0be57d5510c2fb58cfed43621900",
    SCHEME: "bead3f5b63ee6c33f9f96e885736f403a0c30834fd9f394e648830101ba9a63a",
}
GRAPH_LIMIT = 128 * 1024
STOCK_DEPS = {
    "/usr/lib/libSystem.B.dylib", "/usr/lib/libobjc.A.dylib", "/usr/lib/libc++.1.dylib",
    "@rpath/XCTest.framework/XCTest",
    *{f"/System/Library/Frameworks/{name}.framework/{name}" for name in
      ("UIKit", "Foundation", "CoreFoundation", "Network", "Security", "XCTest")},
    *{f"/System/Library/Frameworks/{name}.framework/Versions/A/{name}" for name in
      ("UIKit", "Foundation", "CoreFoundation", "Network", "Security", "XCTest")},
}
SOURCES = {"App.mm", "Smoke.mm", "Tests.mm", "SessionTests.mm", "SessionLifecycle.inc",
           "SessionLifecycle.c", "TrackedTests.mm", "TrackedAcceptance.c", "TrackedFixture.c",
           "WssTests.mm", "LoopbackJob.inc"}


def need(ok, label):
    if not ok:
        raise ValueError(label)


def clean_environment(home, scratch):
    # No inherited test selectors, PATH, XCCONFIG, loader, proxy, credentials,
    # toolchains or custom Xcode environment. The stock runner HOME retains its
    # existing CoreSimulator service; the temp and build roots belong to this job.
    return {"PATH": PATH, "HOME": str(home), "TMPDIR": str(scratch),
            "LANG": "C", "LC_ALL": "C", "DEVELOPER_DIR": DEVELOPER}


def stock_identity(app, resolution, requirement, version):
    need(resolution.splitlines() == [str(app / "Contents/Developer/usr/bin/xcodebuild")],
         "scheme-xcode-tool-resolution")
    info = binding.load(binding.exact(app, "Contents/Info.plist"), 1024 * 1024)
    need(info.get("CFBundleIdentifier") == XCODE_ID, "scheme-xcode-bundle-identity")
    designated = [line for line in requirement.splitlines() if line.startswith("designated =>")]
    need(len(designated) == 1 and re.match(
        r'^designated => identifier (?:"com\.apple\.dt\.Xcode"|com\.apple\.dt\.Xcode)(?: |$)',
        designated[0]), "scheme-xcode-designated-identity")
    need(version.splitlines() == ["Xcode 26.2", "Build version 17C52"], "scheme-xcode-version")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def members(directory, expected, label):
    unseen = set(expected)
    with os.scandir(directory) as entries:
        for entry in entries:
            need(entry.name in unseen, label)
            unseen.remove(entry.name)
    need(not unseen, label)


def project_root(folder):
    need(folder.resolve(strict=True) == folder, "scheme-graph-location")
    members(folder, SOURCES | {PROJECT, "MadLink.xcframework"}, "scheme-graph-root")
    binding.exact(folder, "MadLink.xcframework", directory=True)
    for name in SOURCES:
        binding.exact(folder, name)
    return binding.exact(folder, PROJECT, directory=True)


def bounded(path):
    with path.open("rb") as file:
        data = file.read(GRAPH_LIMIT + 1)
    need(len(data) <= GRAPH_LIMIT, "scheme-graph-size")
    return data


def payload(folder):
    # After build, check only the authoritative file names and their known
    # parent components. Never enumerate or read the generated sidecars.
    project = project_root(folder)
    authored = {rel: bounded(binding.exact(project, rel)) for rel in GRAPH}
    need({rel: hashlib.sha256(data).hexdigest() for rel, data in authored.items()} == GRAPH,
         "scheme-graph-digest")
    return authored, {name: digest(folder / name) for name in SOURCES}


def exact_graph(folder):
    project = project_root(folder)
    shared = binding.exact(project, "xcshareddata", directory=True)
    schemes = binding.exact(project, "xcshareddata/xcschemes", directory=True)
    members(project, {"project.pbxproj", "xcshareddata"}, "scheme-graph-member")
    members(shared, {"xcschemes"}, "scheme-graph-member")
    members(schemes, {"Preview.xcscheme"}, "scheme-graph-member")
    return payload(folder)


def close_launch_inheritance(folder):
    # Apply the one known-byte edit before the first invocation on this graph.
    project = project_root(folder)
    scheme = binding.exact(project, SCHEME)
    data = bounded(scheme)
    prior = b'shouldUseLaunchSchemeArgsEnv="YES"'
    need(hashlib.sha256(data).hexdigest() == LEGACY_SCHEME_HASH and data.count(prior) == 1,
         "scheme-graph-parent-scheme")
    closed = data.replace(prior, b'shouldUseLaunchSchemeArgsEnv="NO"')
    need(hashlib.sha256(closed).hexdigest() == GRAPH[SCHEME], "scheme-graph-digest")
    scheme.write_bytes(closed)
    return exact_graph(folder)


def quarantine_project(folder, build, tomb, expected):
    # The caller owns a canonical private sibling directory outside every
    # resolver root. Move the entire old project with one rename, regardless of
    # whether any Xcode sidecars are present; none are walked or interpreted.
    project = project_root(folder)
    need(payload(folder) == expected, "scheme-graph-build-mutation")
    need(tomb.parent.is_dir() and tomb.parent.resolve(strict=True) == tomb.parent and
         not (tomb.parent.stat().st_mode & 0o077) and not tomb.exists() and not tomb.is_symlink() and
         all(root.resolve(strict=True) == root and not tomb.is_relative_to(root) and not root.is_relative_to(tomb)
             for root in (folder, build)), "scheme-project-quarantine")
    project.rename(tomb)
    need(tomb.resolve(strict=True) == tomb and not project.exists(), "scheme-project-quarantine")
    project.mkdir(mode=0o700)
    (project / "xcshareddata").mkdir(mode=0o700)
    (project / "xcshareddata/xcschemes").mkdir(mode=0o700)
    for relative, original in expected[0].items():
        with (project / relative).open("xb") as file:
            file.write(original)
            os.fchmod(file.fileno(), 0o600)
    need(exact_graph(folder) == expected, "scheme-project-restore")


def locations(paths):
    # Detect even same-byte inode substitution on the canonical launch route.
    out = {}
    for path in paths:
        need(path.resolve(strict=True) == path, "scheme-launch-location")
        info = path.stat()
        out[path.as_posix()] = (info.st_dev, info.st_ino)
    return out


def classify_receipt(doc):
    """Validate product/selection evidence; never consume opaque launch data."""
    meta = doc.get("__xctestrun_metadata__", {})
    # The observed stock no-plan shape has v1 plus one opaque metadata key.
    # It is neither parsed nor copied to a command/file Xcode can discover.
    need(isinstance(meta, dict) and type(meta.get("FormatVersion")) is int and
         meta["FormatVersion"] == 1 and len(meta) in (1, 2), "scheme-evidence-format")
    selected = binding.bundle_path({**doc, "__xctestrun_metadata__": {"FormatVersion": 1},
                                    binding.TEST: neutral_evidence(doc.get(binding.TEST))})
    return selected


def neutral_evidence(item):
    need(isinstance(item, dict), "scheme-evidence-target")
    stock = item.get("TestingEnvironmentVariables", {})
    need(isinstance(stock, dict) and len(stock) <= 32, "scheme-evidence-loader")
    loader_keys = {"DYLD_FRAMEWORK_PATH", "DYLD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
                   "XCInjectBundleInto", "XCInjectBundle"}
    known = {}
    for key, value in stock.items():
        need(isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", key) and
             isinstance(value, str) and len(value) <= 1024 and not any(ord(x) < 32 for x in value),
             "scheme-evidence-loader")
        if key in loader_keys:
            known[key] = value  # Existing validator checks exact stock paths.
        else:
            # The untouched generated file is quarantined before launch.
            # Unknown stock annotations never become execution overrides.
            # Still fail on any additional explicit path/loader authority.
            upper = key.upper()
            need(not upper.startswith(("DYLD", "LD_", "SIMCTL_CHILD", "XCINJECT", "XCODE_XCCONFIG")) and
                 "/" not in value and "\\" not in value and "__" not in value and ":" not in value,
                 "scheme-evidence-loader-override")
    return {**item, "TestingEnvironmentVariables": known}


def receipt(products, quarantine):
    files = list(products.glob("*.xctestrun"))
    need(len(files) == 1 and not quarantine.exists() and not quarantine.is_symlink(), "scheme-evidence-count")
    source = binding.exact(products, files[0].name)
    relative = classify_receipt(binding.load(source, 1024 * 1024))
    expected = digest(source)
    source.rename(quarantine)
    need(quarantine.resolve(strict=True) == quarantine and digest(quarantine) == expected and
         not list(products.rglob("*.xctestrun")), "scheme-evidence-quarantine")
    return relative, expected


def product_paths(products, selected):
    need(products.resolve(strict=True) == products and selected in (binding.TOP, binding.NESTED),
         "scheme-products-root")
    host = binding.exact(products, binding.HOST)
    tests = {}
    for path in (binding.TOP, binding.NESTED):
        if (products / path).exists() or (products / path).is_symlink():
            tests[path] = binding.exact(products, path + "/" + binding.TEST)
    need(selected in tests and len({digest(p) for p in tests.values()}) == 1, "scheme-test-product")
    for relative, name, ident, mode in ((binding.APP, "Demo", binding.APP_ID, "APPL"),
                                         *((path, binding.TEST, binding.TEST_ID, "BNDL") for path in tests)):
        info = binding.load(binding.exact(products, relative + "/Info.plist"), 65536)
        need((info.get("CFBundleExecutable"), info.get("CFBundleIdentifier"),
              info.get("CFBundlePackageType")) == (name, ident, mode), "scheme-product-identity")
        need(not set(info) & {"LSEnvironment", "NSPrincipalClass", "NSExtension", "CFBundleURLTypes"} and
             not any(key.upper().startswith(("DYLD", "LD_", "SIMCTL_CHILD", "XCINJECT")) for key in info),
             "scheme-product-launch-metadata")
    return host, tests


def dependencies(text):
    lines = text.splitlines()[1:]
    deps = []
    for line in lines:
        match = re.fullmatch(r"\s+(\S+) \(compatibility version [0-9.]+, current version [0-9.]+\)", line)
        need(match is not None and match[1] in STOCK_DEPS, "scheme-product-dependency")
        deps.append(match[1])
    need(deps and len(set(deps)) == len(deps), "scheme-product-dependency")
    return set(deps)


def snapshot(folder, products, selected, evidence, fingerprint):
    sysroot_inventory(products, selected, folder / "MadLink.xcframework")
    graph = exact_graph(folder)
    host, tests = product_paths(products, selected)
    need(evidence.resolve(strict=True) == evidence and evidence.is_file() and
         not list(products.rglob("*.xctestrun")), "scheme-evidence-quarantine")
    known = [folder, folder / PROJECT, *(folder / PROJECT / rel for rel in GRAPH),
             *(folder / name for name in SOURCES), folder / "MadLink.xcframework",
             products, host, host.parent, evidence, *tests.values(), *(p.parent for p in tests.values())]
    return (graph, locations(known), digest(evidence), fingerprint(host.parent),
            {key: fingerprint(path.parent) for key, path in tests.items()})


def rpaths(text):
    allowed = {"@executable_path/Frameworks", "@loader_path/Frameworks", "@loader_path/../../Frameworks",
               DEVELOPER + "/Platforms/iPhoneSimulator.platform/Developer/Library/Frameworks"}
    lines = text.splitlines()
    for number, line in enumerate(lines):
        if line.strip() == "cmd LC_RPATH":
            need(number + 2 < len(lines), "scheme-product-rpath")
            m = re.fullmatch(r"\s*path (\S+) \(offset [0-9]+\)", lines[number + 2])
            need(m is not None and m[1] in allowed, "scheme-product-rpath")

def nodes(root):
    files, directories = set(), set()
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        need(path.resolve(strict=True) == path, "scheme-inventory-canonical")
        if stat.S_ISDIR(mode):
            directories.add(rel)
        elif stat.S_ISREG(mode):
            files.add(rel)
        else:
            raise ValueError("scheme-inventory-type")
    return files, directories


def prefix_group(path, files, dirs):
    return ({item[len(path) + 1:] for item in files if item.startswith(path + "/")},
            {item[len(path) + 1:] for item in dirs if item.startswith(path + "/")})


def debug_symbols(path, contents, dirs, binary):
    dwarf = "Contents/Resources/DWARF/" + binary
    need(dirs == {"Contents", "Contents/Resources", "Contents/Resources/DWARF"} and
         contents == {"Contents/Info.plist", dwarf}, "scheme-inventory-debug-layout")
    image = path / dwarf
    with image.open("rb") as stream:
        header = stream.read(16)
    # Match real little-endian 64-bit Mach-O dSYM, not executable content
    # relabeled as a tolerated debug file.
    need(len(header) == 16 and struct.unpack_from("<I", header, 0)[0] == 0xfeedfacf and
         struct.unpack_from("<I", header, 12)[0] == 10 and not (image.stat().st_mode & 0o111),
         "scheme-inventory-debug-format")
    info = path / "Contents/Info.plist"
    need(binding.load(info, 65536).get("CFBundlePackageType") == "dSYM", "scheme-inventory-debug-format")


def sysroot_inventory(products, selected, installed):
    _, tests = product_paths(products, selected)
    files, dirs = nodes(products)
    permitted_files, permitted_dirs = set(), {binding.CONFIG, binding.APP}
    for base, binary in ((binding.APP, "Demo"), *((path, binding.TEST) for path in tests)):
        permitted_dirs.update({base, base + "/_CodeSignature"})
        permitted_files.update(base + "/" + rel for rel in
                               (binary, "Info.plist", "_CodeSignature/CodeResources"))
        if base + "/PkgInfo" in files:
            with (products / base / "PkgInfo").open("rb") as stream:
                expected = b"APPL????" if base == binding.APP else b"BNDL????"
                need(stream.read(9) == expected, "scheme-inventory-pkginfo")
            permitted_files.add(base + "/PkgInfo")
    if binding.NESTED in tests:
        permitted_dirs.add(binding.APP + "/PlugIns")
    for name, stem in (("Demo.app.dSYM", "Demo"), ("SmokeTests.xctest.dSYM", "SmokeTests")):
        group = binding.CONFIG + "/" + name
        if group in dirs:
            subfiles, subdirs = prefix_group(group, files, dirs)
            debug_symbols(products / group, subfiles, subdirs, stem)
            permitted_dirs.add(group)
            permitted_dirs.update(group + "/" + rel for rel in subdirs)
            permitted_files.update(group + "/" + rel for rel in subfiles)
    # ProcessXCFramework may leave an exact static staging framework in
    # SYMROOT. Only bytes/roles from the installed static slice are admitted.
    staging = binding.CONFIG + "/MadLink.framework"
    if staging in dirs:
        source = binding.exact(installed, "ios-arm64-simulator/MadLink.framework", directory=True)
        subfiles, subdirs = prefix_group(staging, files, dirs)
        source_files, source_dirs = nodes(source)
        need("MadLink" in subfiles and subfiles <= source_files and subdirs <= source_dirs,
             "scheme-inventory-static-layout")
        archive = products / staging / "MadLink"
        with archive.open("rb") as stream:
            need(stream.read(8) == b"!<arch>\n", "scheme-inventory-static-format")
        need(all(digest(products / staging / relative) == digest(source / relative) for relative in subfiles),
             "scheme-inventory-static-format")
        permitted_dirs.add(staging)
        permitted_dirs.update(staging + "/" + rel for rel in subdirs)
        permitted_files.update(staging + "/" + rel for rel in subfiles)
    need(files == permitted_files and dirs == permitted_dirs, "scheme-inventory-closed")


def loader_controls(text):
    rpaths(text)
    lines = text.splitlines()
    approved_commands = {
        "LC_SEGMENT_64", "LC_SYMTAB", "LC_DYSYMTAB", "LC_UUID", "LC_BUILD_VERSION",
        "LC_SOURCE_VERSION", "LC_MAIN", "LC_FUNCTION_STARTS", "LC_DATA_IN_CODE",
        "LC_CODE_SIGNATURE", "LC_DYLD_INFO", "LC_DYLD_INFO_ONLY", "LC_DYLD_EXPORTS_TRIE",
        "LC_DYLD_CHAINED_FIXUPS", "LC_RPATH", "LC_LOAD_DYLINKER", "LC_LOAD_DYLIB",
        "LC_LOAD_WEAK_DYLIB",
    }
    headers = [i for i, line in enumerate(lines) if re.fullmatch(r"Load command [0-9]+", line)]
    need(headers and [lines[i] for i in headers] == [f"Load command {i}" for i in range(len(headers))],
         "scheme-loader-control")
    for column in headers:
        index = column + 1
        need(index < len(lines), "scheme-loader-control")
        match = re.fullmatch(r"\s*cmd (LC_[A-Z0-9_]+)", lines[index])
        need(match is not None and match[1] in approved_commands, "scheme-loader-control")
        cmd = match[1]
        if cmd in ("LC_LOAD_DYLINKER", "LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB"):
            need(index + 2 < len(lines), "scheme-loader-control")
            name = re.fullmatch(r"\s*name (\S+) \(offset [0-9]+\)", lines[index + 2])
            approved = {"/usr/lib/dyld"} if cmd == "LC_LOAD_DYLINKER" else STOCK_DEPS
            need(name is not None and name[1] in approved, "scheme-loader-control")
