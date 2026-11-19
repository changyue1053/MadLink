#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p build/wss
# Opt-in only; uses existing system packages, never downloads/installs dependencies.
${CXX:-c++} -std=c++17 -Wall -Wextra -Wpedantic -Werror ${EXTRA_CXXFLAGS:-} \
  -Iinclude -Ioptional/curl $(pkg-config --cflags libcurl) \
  src/madlink.cpp optional/curl/curl_transport.cpp tests/wss/client.cpp \
  $(pkg-config --libs libcurl) -Wl,--wrap=curl_ws_send -Wl,--wrap=curl_ws_recv -o build/wss/client
python3 tests/wss/loopback.py
python3 tests/wss/reconnect.py
