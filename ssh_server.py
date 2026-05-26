"""
ssh_server.py — SSH transport for TTYFlix.

Runs alongside the Telnet server, accepting SSH connections and routing them
through the same session/playback pipeline via SSHConnection.

Clients connect with any SSH client (no password required):
  ssh anything@your-server-hostname -p 2222
"""

import logging
import socket
import threading
from pathlib import Path

import paramiko

from server.catalog import Entry
from server.config import ServerConfig
from server.session import handle_client
from server.ssh_conn import SSHConnection

log = logging.getLogger('ssh')


class _SessionInterface(paramiko.ServerInterface):
    """Accepts any connection; no authentication required."""

    def __init__(self) -> None:
        self.shell_ready = threading.Event()
        self.terminal_size: tuple[int, int] | None = None

    def check_channel_request(self, kind: str, chanid: int) -> int:
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def get_allowed_auths(self, username: str) -> str:
        return 'none,password,publickey'

    def check_auth_none(self, username: str) -> int:
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_password(self, username: str, password: str) -> int:
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_publickey(self, username: str, key: paramiko.PKey) -> int:
        return paramiko.AUTH_SUCCESSFUL

    def check_channel_pty_request(
        self, channel, term: bytes, width: int, height: int,
        pixelwidth: int, pixelheight: int, modes: bytes,
    ) -> bool:
        self.terminal_size = (width, height)
        return True

    def check_channel_shell_request(self, channel) -> bool:
        self.shell_ready.set()
        return True

    def check_channel_window_change_request(
        self, channel, width: int, height: int,
        pixelwidth: int, pixelheight: int,
    ) -> bool:
        return True


def load_or_generate_host_key(path: Path) -> paramiko.RSAKey:
    if path.exists() and path.stat().st_size > 0:
        try:
            return paramiko.RSAKey(filename=str(path))
        except (paramiko.SSHException, OSError):
            log.warning('could not read host key at %s; regenerating', path)
    log.info('generating SSH host key at %s', path)
    key = paramiko.RSAKey.generate(2048)
    key.write_private_key_file(str(path))
    return key


def _handle_connection(
    sock: socket.socket,
    addr: tuple[str, int],
    host_key: paramiko.PKey,
    menu_bytes: bytes,
    key_map: dict[str, Entry],
    config: ServerConfig,
    sem: threading.Semaphore,
) -> None:
    transport: paramiko.Transport | None = None
    try:
        transport = paramiko.Transport(sock)
        transport.add_server_key(host_key)
        transport.set_keepalive(60)

        iface = _SessionInterface()
        try:
            transport.start_server(server=iface)
        except paramiko.SSHException as e:
            log.debug('SSH negotiation failed from %s: %s', addr[0], e)
            return

        channel = transport.accept(timeout=30)
        if channel is None:
            log.debug('no channel opened from %s', addr[0])
            return

        if not iface.shell_ready.wait(timeout=10):
            log.debug('shell request timed out from %s', addr[0])
            channel.close()
            return

        conn = SSHConnection(channel, addr, iface.terminal_size)
        handle_client(conn, menu_bytes, key_map, config)

    except Exception as e:
        log.debug('connection error from %s: %s', addr[0], e)
    finally:
        if transport is not None:
            transport.close()
        sock.close()
        sem.release()


def run_ssh_server(
    config: ServerConfig,
    menu_bytes: bytes,
    key_map: dict[str, Entry],
    host_key: paramiko.PKey,
    sem: threading.Semaphore,
) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((config.host, config.ssh_port))
    except OSError as e:
        log.error('cannot bind SSH port %d: %s', config.ssh_port, e)
        return

    srv.listen(10)
    log.info('listening on %s:%d', config.host, config.ssh_port)

    while True:
        try:
            sock, addr = srv.accept()
        except OSError:
            break

        if not sem.acquire(blocking=False):
            log.warning('connection cap reached; rejecting SSH from %s', addr[0])
            try:
                sock.close()
            except OSError:
                pass
            continue

        t = threading.Thread(
            target=_handle_connection,
            args=(sock, addr, host_key, menu_bytes, key_map, config, sem),
            daemon=True,
        )
        t.start()
