#!/bin/sh
# Local package assembly, not a system tool installer. Requires existing toolchain.
set -eu
if [ "$#" -ne 2 ]; then echo 'usage: sh packaging/install-core.sh ABS_PREFIX ABS_BUILD_DIR' >&2; exit 2; fi
case "$1:$2" in /*:/*) ;; *) echo 'absolute paths required' >&2; exit 2;; esac
prefix=$1
build=$2
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$build" "$prefix/include" "$prefix/lib/pkgconfig" "$prefix/share/doc/madlink"
for source in madlink madlink_c; do
  (cd "$root"; ${CXX:-c++} -std=c++17 -O2 -Wall -Wextra -Wpedantic -Werror ${EXTRA_CXXFLAGS:-} \
    -ffile-prefix-map="$root"=madlink-source -ffile-prefix-map="$build"=madlink-build \
    -Iinclude -c "src/$source.cpp" -o "$build/$source.o")
done
# Build a fresh archive in a fresh staging directory, never append old members.
stage=$(mktemp -d "$build/archive.XXXXXX")
${AR:-ar} rcs "$stage/libmadlink.a" "$build/madlink.o" "$build/madlink_c.o"
cp "$stage/libmadlink.a" "$prefix/lib/libmadlink.a"
cp "$root/include/madlink_c.h" "$prefix/include/"
cp "$root/packaging/madlink.pc" "$prefix/lib/pkgconfig/"
cp "$root/packaging/INSTALLED.md" "$prefix/share/doc/madlink/README.md"
cp "$root/LICENSE" "$prefix/share/doc/madlink/LICENSE"
cp "$root/THIRD_PARTY_NOTICES.md" "$prefix/share/doc/madlink/THIRD_PARTY_NOTICES.md"
printf 'Installed local core SDK at %s\n' "$prefix"
