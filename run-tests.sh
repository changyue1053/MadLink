#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p build
${CXX:-c++} -std=c++17 -Wall -Wextra -Wpedantic -Werror ${EXTRA_CXXFLAGS:-} \
  -Iinclude src/madlink.cpp tests/test_main.cpp -o build/lifecycle-tests
./build/lifecycle-tests
${CXX:-c++} -std=c++17 -Wall -Wextra -Wpedantic -Werror ${EXTRA_CXXFLAGS:-} \
  -Iinclude src/madlink.cpp tests/test_allocation.cpp -o build/allocation-tests
./build/allocation-tests
