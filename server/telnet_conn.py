"""Telnet transport: wraps a raw socket and performs IAC/NAWS negotiation."""

import select
import socket
import time
from typing import Callable

from .connection import Connection
from .protocol import NEGOTIATE, parse_naws, strip_iac


class TelnetConnection(Connection):
    def __init__(self, sock: socket.socket, addr: tuple[str, int]) -> None:
        self._sock = sock
        self._addr = addr
        self._terminal_size: tuple[int, int] | None = None

        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(30)
            sock.sendall(NEGOTIATE)
            time.sleep(0.15)

            sock.settimeout(0.1)
            buf = b''
            try:
                while True:
                    chunk = sock.recv(256)
                    if not chunk:
                        break
                    buf += chunk
            except socket.timeout:
                pass

            self._terminal_size = parse_naws(buf)
            sock.settimeout(None)
        except OSError:
            sock.close()
            raise

    def send(self, data: bytes) -> None:
        self._sock.sendall(data)

    def recv(self, n: int) -> bytes:
        return self._sock.recv(n)

    def recv_ready(self) -> bool:
        r, _, _ = select.select([self._sock], [], [], 0)
        return bool(r)

    def settimeout(self, timeout: float | None) -> None:
        self._sock.settimeout(timeout)

    def close(self) -> None:
        self._sock.close()

    @property
    def addr(self) -> tuple[str, int]:
        return self._addr

    @property
    def terminal_size(self) -> tuple[int, int] | None:
        return self._terminal_size

    @property
    def input_filter(self) -> Callable[[bytes], bytes]:
        return strip_iac
