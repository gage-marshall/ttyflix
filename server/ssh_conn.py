"""SSH transport: wraps a paramiko Channel."""

from typing import Callable

from .connection import Connection


class SSHConnection(Connection):
    def __init__(
        self,
        channel,
        addr: tuple[str, int],
        terminal_size: tuple[int, int] | None,
    ) -> None:
        self._channel = channel
        self._addr = addr
        self._terminal_size = terminal_size
        channel.settimeout(None)

    def send(self, data: bytes) -> None:
        try:
            self._channel.sendall(data)
        except EOFError:
            raise OSError('SSH channel closed')

    def recv(self, n: int) -> bytes:
        data = self._channel.recv(n)
        return data if data else b''

    def recv_ready(self) -> bool:
        return self._channel.recv_ready()

    def settimeout(self, timeout: float | None) -> None:
        self._channel.settimeout(timeout)

    def close(self) -> None:
        self._channel.close()

    @property
    def addr(self) -> tuple[str, int]:
        return self._addr

    @property
    def terminal_size(self) -> tuple[int, int] | None:
        return self._terminal_size

    @property
    def input_filter(self) -> Callable[[bytes], bytes]:
        return lambda x: x
