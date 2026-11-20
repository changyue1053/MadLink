"""Exactly two job-owned TCP/TLS loopback peers; no package provisioning."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, ExitStack, closing
import hashlib
import os
import shutil
import socket
import ssl
import subprocess
import time

REQUEST = bytes((0, 255, 77, 76))
REPLY = bytes((76, 77, 255, 0))


class Rejected(Exception):
    pass


def require(value):
    if not value:
        raise Rejected()


def run_openssl(root, *args):
    executable = shutil.which("openssl")
    require(executable)
    env = {**os.environ, "OPENSSL_CONF": str(root / "cert.cnf")}
    subprocess.run([executable, *args], check=True, timeout=15, env=env, cwd=root,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def identities(root):
    # CA certificate public bytes go into the test. All keys stay host-only
    # in this runner-owned mode-0700 directory, with no downloads or artifacts.
    (root / "cert.cnf").write_text("""[req]
distinguished_name = dn
[dn]
[root]
basicConstraints = critical,CA:TRUE,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
[valid]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = IP:127.0.0.1
[wrong]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = IP:127.0.0.2
""")
    run_openssl(root, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256", "-days", "1",
                "-subj", "/CN=MadLink Job-Local Test Root", "-extensions", "root",
                "-keyout", "root.key", "-out", "root.pem")
    for serial, name in enumerate(("valid", "wrong"), 2):
        run_openssl(root, "req", "-new", "-newkey", "rsa:2048", "-nodes", "-sha256",
                    "-subj", "/CN=MadLink Job-Local Test Leaf", "-keyout", name + ".key",
                    "-out", name + ".csr")
        run_openssl(root, "x509", "-req", "-in", name + ".csr", "-CA", "root.pem", "-CAkey", "root.key",
                    "-set_serial", str(serial), "-days", "1", "-sha256", "-extfile", "cert.cnf",
                    "-extensions", name, "-out", name + ".pem")
    run_openssl(root, "x509", "-in", "root.pem", "-outform", "DER", "-out", "root.der")
    public = (root / "root.der").read_bytes()
    require(256 <= len(public) <= 2048)
    configs = []
    for name in ("valid", "wrong"):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(root / (name + ".pem"), root / (name + ".key"))
        configs.append(context)
    return public, *configs


def listen():
    listener = socket.socket(socket.AF_INET)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        return listener
    except Exception:
        listener.close()
        raise


def exact(conn, size, deadline):
    result = bytearray()
    while len(result) < size:
        remaining = deadline - time.monotonic()
        require(remaining > 0)
        conn.settimeout(remaining)
        part = conn.recv(size - len(result))
        require(part)
        result.extend(part)
    return bytes(result)


def upgrade(conn, port, deadline):
    request = bytearray()
    while not request.endswith(b"\r\n\r\n"):
        require(len(request) < 8192)
        request.extend(exact(conn, 1, deadline))
    initial, *headers = bytes(request[:-4]).split(b"\r\n")
    require(initial == b"GET / HTTP/1.1")
    fields = {}
    for line in headers:
        key, value = line.split(b":", 1)
        key = key.lower()
        require(key not in fields)
        fields[key] = value.strip()
    require(fields.get(b"host") == f"127.0.0.1:{port}".encode("ascii"))
    require(fields.get(b"upgrade", b"").lower() == b"websocket")
    require(b"upgrade" in [x.strip() for x in fields.get(b"connection", b"").lower().split(b",")])
    require(fields.get(b"sec-websocket-version") == b"13")
    key = fields[b"sec-websocket-key"]
    require(len(base64.b64decode(key, validate=True)) == 16)
    receipt = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
    conn.settimeout(4)
    conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                 b"Sec-WebSocket-Accept: " + receipt + b"\r\n\r\n")


def serve(listener, context, valid):
    child, addr = listener.accept()
    with closing(child):
        require(addr[0] == "127.0.0.1")
        child.settimeout(8)
        try:
            tls = context.wrap_socket(child, server_side=True)
        except ssl.SSLError:
            # Native client must also independently observe hostname denial.
            # A bare TCP close, timeout or missed connection does not suffice.
            require(not valid)
            return
        with tls:
            if not valid:
                # TLS1.3 may finish server-side before client's cert decision
                # is surfaced. Require alert (not a dry timeout or any bytes).
                try:
                    tls.recv(1)
                except ssl.SSLError:
                    return
                raise Rejected()
            deadline = time.monotonic() + 8
            upgrade(tls, listener.getsockname()[1], deadline)
            require(exact(tls, 2, deadline) == bytes((0x82, 0x80 | len(REQUEST))))
            mask = exact(tls, 4, deadline)
            wire = exact(tls, len(REQUEST), deadline)
            require(bytes(byte ^ mask[i % 4] for i, byte in enumerate(wire)) == REQUEST)
            tls.settimeout(4)
            tls.sendall(bytes((0x82, len(REPLY))) + REPLY)
            # Keep this connection open until the owner has checked its
            # receive/completion and canceled; an early peer close can hide
            # the distinction between round-trip and disconnect.
            require(tls.recv(1) == b"")


@contextmanager
def peers(cert_dir):
    public, valid, wrong = identities(cert_dir)
    with ExitStack() as clean:
        listeners = [clean.enter_context(listen()) for _ in range(2)]
        threads = clean.enter_context(ThreadPoolExecutor(max_workers=2))
        ports = tuple(listener.getsockname()[1] for listener in listeners)
        require(ports[0] != ports[1])
        def start():
            for listener in listeners:
                listener.settimeout(85)
            return [threads.submit(serve, listener, context, is_valid)
                    for listener, context, is_valid in zip(listeners, (valid, wrong), (True, False))]
        # Listener ports must be baked into the XCTest before build. Only start
        # accept deadlines once the inspected product is ready to run.
        try:
            yield public, ports, start
        finally:
            # Wake workers still in accept if Xcode/the client fails before
            # reaching one peer. Active child sockets have fixed deadlines.
            for listener in listeners:
                try:
                    listener.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                listener.close()
