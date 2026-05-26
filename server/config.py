from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ServerConfig:
    output_dir: Path
    cols: int = 80
    rows: int = 25
    title: str = 'ANSI TELNET'
    host: str = '0.0.0.0'
    port: int = 23
    web_port: Optional[int] = 8080
    max_connections: int = 50
    idle_timeout: int = 300
    ssh_port: int | None = 2222
    ssh_host_key: str = 'ssh_host_key'
