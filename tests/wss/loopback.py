"""New stdlib-only localhost fixture, NOT a production WebSocket implementation."""
import base64
import hashlib
import pathlib
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time

root = pathlib.Path(__file__).resolve().parents[2]
work = root / "build" / "wss"
work.mkdir(parents=True, exist_ok=True)
cert, key = work / "cert.pem", work / "key.pem"
subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=localhost",
                "-addext", "subjectAltName=DNS:localhost"], check=True, stdout=subprocess.DEVNULL,
               stderr=subprocess.DEVNULL)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(cert, key)

def exact(conn, length):
    result = b""
    while len(result) < length:
        chunk = conn.recv(length-len(result))
        if not chunk:
            raise EOFError("peer closed")
        result += chunk
    return result

def frame(opcode, data, final=True):
    header = bytes([(128 if final else 0) | opcode])
    size = len(data)
    header += bytes([size]) if size < 126 else b"\x7e" + struct.pack("!H", size)
    return header + data

def receive(conn):
    first, second = exact(conn, 2)
    size = second & 127
    if size == 126:
        size = struct.unpack("!H", exact(conn, 2))[0]
    elif size == 127:
        size = struct.unpack("!Q", exact(conn, 8))[0]
    if not second & 128 or size > 65536:
        raise ValueError("invalid client masking/size")
    mask = exact(conn, 4)
    payload = exact(conn, size)
    return first & 15, bytes(x ^ mask[i % 4] for i, x in enumerate(payload))

def scenario(mode, hostname="localhost", trusted=True):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(10)
    errors = []
    def serve():
        try:
            with listener:
                raw, _ = listener.accept()
                raw.settimeout(8)
                try:
                    conn = context.wrap_socket(raw, server_side=True)
                except (ssl.SSLError, ConnectionError):
                    raw.close()
                    if mode != "reject":
                        raise
                    return
                with conn:
                    if mode == "reject":
                        # Hostname verification can fail after TLS server-side
                        # handshake completion, but before any HTTP request.
                        try:
                            if conn.recv(1):
                                raise ValueError("HTTP data despite certificate rejection")
                        except (ssl.SSLError, ConnectionError):
                            pass
                        return
                    header = b""
                    while not header.endswith(b"\r\n\r\n"):
                        header += exact(conn, 1)
                        if len(header) > 8192:
                            raise ValueError("header too large")
                    fields = dict(line.split(b":", 1) for line in header.split(b"\r\n")[1:] if b":" in line)
                    nonce = next(v.strip() for k, v in fields.items() if k.lower() == b"sec-websocket-key")
                    accept = base64.b64encode(hashlib.sha1(nonce+b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
                    conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "+accept+b"\r\n\r\n")
                    if mode in ("stall", "stall-close"):
                        # Send-side EAGAIN is injected in the real TLS client.
                        # Inbound data or peer CLOSE remains unread while its
                        # outbound frame is stalled. Wait for client teardown.
                        conn.sendall(frame(2,b"peer-data") if mode=="stall" else frame(8,struct.pack("!H",1000)))
                        try:
                            if conn.recv(1):
                                raise ValueError("unexpected payload despite forced EAGAIN")
                        except (ssl.SSLError, ConnectionError):
                            pass
                        return
                    if mode == "oversize":
                        conn.sendall(b"\x82\x7f"+struct.pack("!Q", 65537)+b"x")
                        # Keep the server open: client must reject and close first.
                        # A timeout is a failure, not evidence of client rejection.
                        try:
                            if conn.recv(1):
                                raise ValueError("unexpected data after oversize frame")
                        except (ssl.SSLError, ConnectionError):
                            pass
                        return
                    conn.sendall(frame(2, b"abc\x00", False)+frame(9,b"ping")+frame(0,b"xyz"))
                    pong = False
                    payload = None
                    for _ in range(3):
                        opcode, data = receive(conn)
                        if opcode == 10:
                            pong = data == b"ping"
                        elif opcode == 2:
                            payload = data
                        else:
                            raise ValueError("unexpected client frame")
                        if pong and payload is not None:
                            break
                    assert pong and payload == bytes(i % 251 for i in range(32768))
                    packed = frame(2, payload)
                    for start in range(0, len(packed), 1000):
                        conn.sendall(packed[start:start+1000])
                        time.sleep(0.001)
                    conn.sendall(frame(8, struct.pack("!H", 1000)))
                    time.sleep(0.05)
        except Exception as exc:
            errors.append(repr(exc))
    worker = threading.Thread(target=serve)
    worker.start()
    url = f"wss://{hostname}:{listener.getsockname()[1]}/test"
    run = subprocess.run([str(work / "client"), url, str(cert) if trusted else "", mode], timeout=12)
    worker.join(11)
    if worker.is_alive() or errors or run.returncode:
        raise RuntimeError(f"{mode}: client={run.returncode}, server={errors}, alive={worker.is_alive()}")

if __name__ == "__main__":
    scenario("normal")
    scenario("core")
    scenario("oversize")
    scenario("stall")
    scenario("stall-close")
    scenario("reject", "127.0.0.1")
    scenario("reject", trusted=False)
    print("PASS: localhost-only trusted echo, fragmentation/PING, oversized frame, wrong hostname, untrusted certificate")
