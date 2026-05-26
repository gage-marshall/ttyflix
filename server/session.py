"""
Client session handler.

handle_client() is the per-thread entry point for each connection (Telnet or
SSH). It receives pre-built menu bytes and a key map so no screen is rebuilt
per session — just per server startup.
"""

import logging
import socket
import time

from .catalog import Entry
from .config import ServerConfig
from .connection import Connection
from .playback import play
from .screens import build_check_screen


def handle_client(
    conn: Connection,
    menu_bytes: bytes,
    key_map: dict[str, Entry],
    config: ServerConfig,
) -> None:
    log = logging.getLogger(f'client:{conn.addr[0]}:{conn.addr[1]}')
    log.info('connected')

    try:
        client_w, client_h = conn.terminal_size or (0, 0)
        size_known = conn.terminal_size is not None
        if size_known:
            log.info(f'terminal size: {client_w}x{client_h}')
        else:
            log.info('terminal size: unknown')

        check_screen = build_check_screen(client_w, client_h, size_known, config)
        try:
            conn.send(check_screen)
        except OSError:
            return

        if not _wait_for_enter(conn, config.idle_timeout):
            return

        while True:
            conn.send(menu_bytes)

            key = _read_key(conn, config.idle_timeout)
            if key is None:
                break

            if key.lower() == 'q':
                conn.send(b'\r\n\x1b[0m  Goodbye.\r\n')
                break

            entry = key_map.get(key.lower())
            if entry is None:
                continue

            log.info(f'playing {entry.path.name}')
            result = play(conn, entry.path)
            log.info(f'{entry.path.name} ended: {result}')

            if result == 'disconnected':
                break

            if result == 'ended':
                try:
                    conn.send(
                        b'\x1b[2J\x1b[H\x1b[38;5;201m'
                        b'\r\n\r\n  Playback complete.  Returning to menu...\r\n'
                        b'\x1b[0m'
                    )
                    time.sleep(2)
                except OSError:
                    break

    except (OSError, ConnectionResetError, BrokenPipeError) as e:
        log.info(f'disconnected: {e}')
    except Exception as e:
        log.exception(f'unexpected error: {e}')
    finally:
        try:
            conn.send(b'\x1b[?25h\x1b[?7h\x1b[0m')
        except OSError:
            pass
        conn.close()
        log.info('session closed')


def _wait_for_enter(conn: Connection, timeout: int) -> bool:
    """Block until the client sends CR/LF; return False on disconnect or timeout."""
    conn.settimeout(timeout)
    buf = b''
    while True:
        try:
            chunk = conn.recv(256)
        except (OSError, socket.timeout):
            return False
        if not chunk:
            return False
        buf += chunk
        filtered = conn.input_filter(buf)
        if b'\r' in filtered or b'\n' in filtered:
            return True
        buf = b''


def _read_key(conn: Connection, timeout: int) -> str | None:
    """Block until the client sends a printable keystroke; return None on disconnect or timeout."""
    conn.settimeout(timeout)
    buf = b''
    while True:
        try:
            chunk = conn.recv(256)
        except (OSError, socket.timeout):
            return None
        if not chunk:
            return None
        buf += chunk
        clean = conn.input_filter(buf)
        for b in clean:
            ch = chr(b)
            if ch.isprintable() or ch in ('\r', '\n'):
                return ch if ch.strip() else None
        buf = b''
