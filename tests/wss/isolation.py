#!/usr/bin/env python3
"""Unwrapped Linux WSS client against two bounded, synthetic loopback TLS peers."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
import hashlib
import os
from pathlib import Path
import shlex
import socket
import ssl
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]


def require(valid):
    if not valid:
        raise ValueError('fixture expectation')


def exact(conn, count, deadline):
    data = bytearray()
    while len(data) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        conn.settimeout(remaining)
        part = conn.recv(count - len(data))
        if not part:
            raise EOFError()
        data.extend(part)
    return bytes(data)


def listener():
    conn = socket.socket(socket.AF_INET)
    try:
        conn.bind(('127.0.0.1', 0))
        conn.listen(2)
        conn.settimeout(6)
        return conn
    except Exception:
        conn.close()
        raise


def handshake_request(conn):
    deadline = time.monotonic() + 4
    request = bytearray()
    while not request.endswith(b'\r\n\r\n'):
        require(len(request) < 8192)
        request += exact(conn, 1, deadline)
    line, *headers = bytes(request).split(b'\r\n')
    require(line == b'GET /isolation HTTP/1.1')
    fields = {}
    for header in filter(None, headers):
        k, v = header.split(b':', 1)
        k = k.lower()
        require(k not in fields)
        fields[k] = v.strip()
    require(fields[b'upgrade'].lower() == b'websocket')
    require(b'upgrade' in [part.strip() for part in fields[b'connection'].lower().split(b',')])
    require(fields[b'sec-websocket-version'] == b'13')
    key = fields[b'sec-websocket-key']
    require(len(base64.b64decode(key, validate=True)) == 16)
    digest = hashlib.sha1(key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest()
    return base64.b64encode(digest)


def upgrade(conn, accept):
    conn.settimeout(4)
    conn.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n'
                 b'Connection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + b'\r\n\r\n')


def send(conn, response):
    conn.settimeout(4)
    conn.sendall(bytes([0x82, len(response)]) + response)


def exchange(conn, expected, response):
    deadline = time.monotonic() + 4
    require(exact(conn, 2, deadline) == bytes([0x82, 0x80 | len(expected)]))
    mask = exact(conn, 4, deadline)
    actual = exact(conn, len(expected), deadline)
    require(bytes(byte ^ mask[i % 4] for i, byte in enumerate(actual)) == expected)
    send(conn, response)


def quiet(conn):
    conn.settimeout(0.12)
    try:
        conn.recv(1)
    except socket.timeout:
        return
    # Both extra data and premature disconnect fail.
    raise ValueError('unexpected data or close')


def eof(conn):
    conn.settimeout(4)
    require(conn.recv(1) == b'')


def accept(listener, context):
    raw, addr = listener.accept()
    try:
        require(addr[0] == '127.0.0.1')
        raw.settimeout(4)
        return context.wrap_socket(raw, server_side=True)
    except Exception:
        raw.close()
        raise


def scenario(work, context):
    a_upgrade_request, b_mid_confirm = threading.Event(), threading.Event()
    with closing(listener()) as a, closing(listener()) as b:
        def peer_a():
            with accept(a, context) as conn:
                upgrade(conn, handshake_request(conn))
                exchange(conn, b'A\x00\x01', b'a\x00\x01')
                eof(conn)
            with accept(a, context) as conn:
                nonce = handshake_request(conn)
                a_upgrade_request.set()
                require(b_mid_confirm.wait(4))
                upgrade(conn, nonce)
                quiet(conn)  # No A2 traffic allowed before fresh send authorization.
                send(conn, b'go')
                exchange(conn, b'A\x00\x02', b'a\x00\x02')
                quiet(conn)  # No replay, duplicate fresh send, or trailing frame.
                send(conn, b'done')
                eof(conn)

        def peer_b():
            with accept(b, context) as conn:
                upgrade(conn, handshake_request(conn))
                exchange(conn, b'B\x00\x01', b'b\x00\x01')
                require(a_upgrade_request.wait(4))
                exchange(conn, b'B\x00\x02', b'b\x00\x02')
                # This is issued only after the client received B2's reply,
                # while A's TLS session is waiting for the HTTP upgrade.
                exchange(conn, b'B\x00\x04', b'b\x00\x04')
                b_mid_confirm.set()
                exchange(conn, b'B\x00\x03', b'b\x00\x03')
                eof(conn)

        with ThreadPoolExecutor(max_workers=2) as workers:
            peers = [('peer-a', workers.submit(peer_a)), ('peer-b', workers.submit(peer_b))]
            ports = [str(s.getsockname()[1]) for s in (a, b)]
            result = subprocess.run([str(work/'client'), *ports, str(work/'cert.pem')], timeout=22)
            for label, peer in peers:
                try:
                    peer.result()
                except Exception:
                    print('FAIL: WSS isolation ' + label, flush=True)
                    raise
            require(result.returncode == 0)


def command(args, timeout):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          check=True, text=True, timeout=timeout).stdout


def main():
    stage = 'setup'
    try:
        with tempfile.TemporaryDirectory(prefix='madlink-wss-isolation-') as tmp:
            work = Path(tmp)
            stage = 'compile'
            cflags = shlex.split(command(['pkg-config', '--cflags', 'libcurl'], 5))
            libs = shlex.split(command(['pkg-config', '--libs', 'libcurl'], 5))
            command([os.environ.get('CXX', 'c++'), '-std=c++17', '-Wall', '-Wextra',
                     '-Wpedantic', '-Werror', '-I'+str(ROOT/'include'), '-I'+str(ROOT/'optional/curl'),
                     *cflags, ROOT/'src/madlink.cpp', ROOT/'optional/curl/curl_transport.cpp',
                     ROOT/'tests/wss/isolation_client.cpp', *libs, '-o', work/'client'], 45)
            stage = 'certificate'
            command(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                     '-keyout', work/'key.pem', '-out', work/'cert.pem', '-days', '1',
                     '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'], 15)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(work/'cert.pem', work/'key.pem')
            stage = 'loopback'
            scenario(work, context)
        print('PASS: two localhost TLS/WSS peers, A cancellation/no replay and B roundtrip during A upgrade')
        return 0
    except Exception:
        print('FAIL: WSS isolation stage=' + stage)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
