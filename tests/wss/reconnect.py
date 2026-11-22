"""Two real localhost TLS sessions; only post-prefix EAGAIN is injected client-side."""
from loopback import base64, hashlib, socket, ssl, struct, subprocess, threading, time
from loopback import context, exact, frame, receive, work, cert

listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen(2)
listener.settimeout(6)
url = f"wss://localhost:{listener.getsockname()[1]}/reconnect"
errors = []

def accept_session():
    raw, _ = listener.accept()
    raw.settimeout(4)
    conn = context.wrap_socket(raw, server_side=True)
    header = b""
    while not header.endswith(b"\r\n\r\n"):
        header += exact(conn, 1)
        if len(header)>8192:
            raise ValueError("header limit")
    fields = dict(line.split(b":",1) for line in header.split(b"\r\n")[1:] if b":" in line)
    nonce = next(v.strip() for k,v in fields.items() if k.lower()==b"sec-websocket-key")
    accept = base64.b64encode(hashlib.sha1(nonce+b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
    conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "+accept+b"\r\n\r\n")
    return conn

def serve():
    try:
        with listener:
            with accept_session() as first:
                # Incomplete inbound message must be discarded across reconnect.
                first.sendall(frame(2,b"start")+frame(2,b"STALE",False))
                a,b=exact(first,2)
                assert a==0x82 and b==0xfe
                declared=struct.unpack("!H",exact(first,2))[0]
                assert declared==32768
                mask=exact(first,4)
                partial=b""
                while True:
                    try:
                        chunk=first.recv(8192)
                    except (ssl.SSLError,ConnectionError):
                        break
                    if not chunk:
                        break
                    partial+=chunk
                    assert len(partial)<=4096, "remainder sent despite injected AGAIN"
                assert 0<len(partial)<=4096
                decoded=bytes(v^mask[i%4] for i,v in enumerate(partial))
                assert decoded==bytes(i%251 for i in range(len(decoded)))
                print(f"PASS: server received {len(partial)} real payload bytes of declared 32768-byte frame before client timeout")
            with accept_session() as second:
                # Observe a quiet window before authorizing a fresh application send.
                # Any replay/old frame continuation would violate it.
                second.settimeout(0.05)
                try:
                    data=second.recv(1)
                except socket.timeout:
                    data=None
                assert data is None, "replayed bytes or premature close on fresh session"
                second.settimeout(4)
                second.sendall(frame(2,b"go"))
                opcode,payload=receive(second)
                assert opcode==2 and payload==b"fresh"
                second.sendall(frame(2,payload))
                # Ensure no trailing old-message data or duplicate fresh send.
                second.settimeout(0.05)
                try:
                    data=second.recv(1)
                except socket.timeout:
                    data=None
                assert data is None, "unexpected duplicate/trailing frame"
                second.sendall(frame(8,struct.pack("!H",1000)))
                time.sleep(0.03)
    except Exception as exc:
        errors.append(repr(exc))

worker=threading.Thread(target=serve)
worker.start()
run=subprocess.run([str(work/"client"),url,str(cert),"reconnect"],timeout=8)
worker.join(7)
if worker.is_alive() or errors or run.returncode:
    raise RuntimeError(f"reconnect client={run.returncode}, server={errors}, alive={worker.is_alive()}")
print("PASS: server independently verified fresh-session silence, no replay, fresh payload only")
