import base64
import hashlib
import json
import os
import socket
import ssl
import struct
from typing import Dict, Optional
from urllib.parse import urlparse


class CdpError(RuntimeError):
    """Raised when Chrome DevTools Protocol communication fails."""


class CdpClient:
    def __init__(self, websocket_url: str) -> None:
        self.websocket_url = websocket_url
        self._socket = self._connect()
        self._message_id = 0

    def close(self) -> None:
        try:
            self._socket.close()
        except OSError:
            pass

    def send(self, method: str, params: Optional[Dict] = None) -> Dict:
        self._message_id += 1
        payload = {"id": self._message_id, "method": method, "params": params or {}}
        self._send_frame(json.dumps(payload))
        while True:
            message = self._read_json_message()
            if message.get("id") == self._message_id:
                if "error" in message:
                    raise CdpError(f"{method} failed: {message['error']}")
                return message.get("result", {})

    def _connect(self):
        parsed = urlparse(self.websocket_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        raw_sock = socket.create_connection((host, port), timeout=10)
        if parsed.scheme == "wss":
            context = ssl.create_default_context()
            sock = context.wrap_socket(raw_sock, server_hostname=host)
        else:
            sock = raw_sock

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                raise CdpError("WebSocket handshake failed: empty response.")
            response += chunk
        header_text = response.split(b"\r\n\r\n", 1)[0].decode("utf-8", errors="replace")
        if "101" not in header_text.splitlines()[0]:
            raise CdpError(f"WebSocket handshake failed: {header_text}")
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if expected not in header_text:
            raise CdpError("WebSocket handshake failed: Sec-WebSocket-Accept mismatch.")
        sock.settimeout(None)
        return sock

    def _send_frame(self, text: str) -> None:
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        first_byte = 0x81
        length = len(payload)
        if length < 126:
            header = bytes([first_byte, 0x80 | length])
        elif length < 65536:
            header = bytes([first_byte, 0x80 | 126]) + struct.pack(">H", length)
        else:
            header = bytes([first_byte, 0x80 | 127]) + struct.pack(">Q", length)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self._socket.sendall(header + mask + masked)

    def _read_json_message(self) -> Dict:
        while True:
            opcode, payload = self._read_frame()
            if opcode == 0x8:
                raise CdpError("WebSocket closed by remote peer.")
            if opcode != 0x1:
                continue
            return json.loads(payload.decode("utf-8"))

    def _read_frame(self):
        header = self._recv_exact(2)
        first, second = header[0], header[1]
        opcode = first & 0x0F
        masked = second & 0x80
        length = second & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length)
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return opcode, payload

    def _recv_exact(self, size: int) -> bytes:
        chunks = []
        remaining = size
        while remaining > 0:
            chunk = self._socket.recv(remaining)
            if not chunk:
                raise CdpError("Unexpected end of stream while reading WebSocket frame.")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
