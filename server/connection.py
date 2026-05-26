"""Abstract transport interface shared by Telnet and SSH connections."""

from abc import ABC, abstractmethod
from typing import Callable


class Connection(ABC):
    @abstractmethod
    def send(self, data: bytes) -> None: ...

    @abstractmethod
    def recv(self, n: int) -> bytes: ...

    @abstractmethod
    def recv_ready(self) -> bool:
        """Return True if data is available without blocking."""
        ...

    @abstractmethod
    def settimeout(self, timeout: float | None) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def addr(self) -> tuple[str, int]: ...

    @property
    @abstractmethod
    def terminal_size(self) -> tuple[int, int] | None:
        """Reported terminal dimensions, or None if unknown."""
        ...

    @property
    @abstractmethod
    def input_filter(self) -> Callable[[bytes], bytes]:
        """Strip transport-layer framing from raw received bytes."""
        ...
