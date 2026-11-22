#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ "$#" -ne 1 ]; then echo 'usage: sh run-madobs-tests.sh MADOBS_API_PREFIX' >&2;exit 2;fi
api=$(CDPATH= cd -- "$1" && pwd)
# Exact public 79fd8ced API blobs, not a similarly named local/private header.
test "$(git hash-object "$api/include/madobs/observer.h")" = 2fd8c8cc81b2e38569c2b2ce3cd5fec03ffcf001
test "$(git hash-object "$api/include/madobs/privacy.h")" = 178de015b9854fe8aa84e9cf470f3de599c2a356
mkdir -p build/madobs-adapter
work=$(mktemp -d "$(pwd)/build/madobs-adapter/check.XXXXXX")
${CXX:-c++} -std=c++17 -Wall -Wextra -Wpedantic -Werror ${EXTRA_CXXFLAGS:-} \
  -Iinclude -Ioptional/madobs -I"$api/include" src/madlink.cpp tests/madobs/test_adapter.cpp -o "$work/test-adapter"
"$work/test-adapter"
sh packaging/install-core.sh "$work/installed-core" "$work/core-build"
mkdir -p "$work/optional-prefix/include/madlink_madobs" "$work/consumer"
cp optional/madobs/queued_observer.hpp "$work/optional-prefix/include/madlink_madobs/"
cp tests/madobs/installed_consumer.cpp "$work/consumer/main.cpp"
(cd "$work/consumer"; ${CXX:-c++} -std=c++17 -Wall -Wextra -Wpedantic -Werror ${EXTRA_CXXFLAGS:-} \
  -I"$work/installed-core/include" -I"$work/optional-prefix/include" -I"$api/include" \
  -MMD -MF consumer.d main.cpp "$work/installed-core/lib/libmadlink.a" -o consumer
  ./consumer
  ldd consumer > dependencies.txt)
if grep -E 'libcurl|libssl|libcrypto|madobs_runtime' "$work/consumer/dependencies.txt";then exit 1;fi
if grep 'madlink.hpp' "$work/consumer/consumer.d";then exit 1;fi
printf 'API-only evidence directory: %s\n' "$work"
printf 'NOT RUN: official MadObs CMake install, runtime admission/WAL/exporter, cross-thread or mobile integration\n'
