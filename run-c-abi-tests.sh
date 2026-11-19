#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p build/sdk/include build/sdk/lib build/app_a build/app_b
cp include/madlink_c.h build/sdk/include/
for source in madlink madlink_c; do
  ${CXX:-c++} -std=c++17 -Wall -Wextra -Wpedantic -Werror ${EXTRA_CXXFLAGS:-} -Iinclude -c "src/$source.cpp" -o "build/$source.o"
done
ar rcs build/sdk/lib/libmadlink.a build/madlink.o build/madlink_c.o
${CXX:-c++} -std=c++17 -Wall -Wextra -Wpedantic -Werror ${EXTRA_CXXFLAGS:-} -Ibuild/sdk/include tests/test_c_oom.cpp build/sdk/lib/libmadlink.a -o build/c-oom-test
./build/c-oom-test
${CC:-cc} -std=c11 -Wall -Wextra -Wpedantic -Werror ${EXTRA_CFLAGS:-} -Ibuild/sdk/include -c tests/test_c_generation.c -o build/c-generation.o
${CXX:-c++} ${EXTRA_CXXFLAGS:-} build/c-generation.o build/sdk/lib/libmadlink.a -o build/c-generation-test
./build/c-generation-test
for app in app_a app_b; do
  ${CC:-cc} -std=c11 -Wall -Wextra -Wpedantic -Werror ${EXTRA_CFLAGS:-} -Ibuild/sdk/include -c "consumers/$app/main.c" -o "build/$app/main.o"
  ${CXX:-c++} ${EXTRA_CXXFLAGS:-} "build/$app/main.o" build/sdk/lib/libmadlink.a -o "build/$app/consumer"
  "./build/$app/consumer"
done
