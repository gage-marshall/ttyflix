"""
Frame reading and real-time streaming for .ansi.gz files.

The play() function streams frames at the source FPS, sleeping between
frames and checking the connection for a quit keypress.
"""

import gzip
import logging
import struct
import time
from pathlib import Path

from .connection import Connection

log = logging.getLogger(__name__)

MAGIC           = b'ANSI'
FLAG_KEYFRAME   = 0x01
CURRENT_VERSION = 1


def read_header(fh) -> tuple[int, int, int, int]:
    """Read and validate the 16-byte file header. Returns (fps_num, fps_den, cols, rows)."""
    raw = fh.read(16)
    if len(raw) < 16:
        raise ValueError('Truncated header')
    magic, fps_num, fps_den, version, cols, rows = struct.unpack('>4sIIHBB', raw)
    if magic != MAGIC:
        raise ValueError(f'Bad magic: {magic!r}')
    if version != CURRENT_VERSION:
        raise ValueError(f'Unsupported format version: {version}')
    return fps_num, fps_den, cols, rows


def read_frame(fh) -> tuple[int, int, bytes] | None:
    """Read one frame record. Returns (frame_no, flags, data) or None at EOF."""
    hdr = fh.read(12)
    if len(hdr) < 12:
        return None
    frame_no, flags, dlen = struct.unpack('>III', hdr)
    data = fh.read(dlen)
    if len(data) < dlen:
        return None
    return frame_no, flags, data


def play(conn: Connection, path: Path) -> str:
    """
    Stream an .ansi.gz file at the encoded FPS.

    Checks the connection for input after each frame; returns immediately if
    the client sends 'q' or disconnects.

    Returns one of: 'ended' | 'quit' | 'disconnected'
    """
    if not path.exists():
        try:
            conn.send(f'\r\n  [Error: {path.name} not found]\r\n'.encode())
            time.sleep(2)
        except OSError:
            return 'disconnected'
        return 'ended'

    try:
        conn.send(b'\x1b[2J\x1b[H\x1b[?25l\x1b[?7l')
    except OSError:
        return 'disconnected'

    try:
        with gzip.open(path, 'rb') as gz:
            fps_num, fps_den, _cols, _rows = read_header(gz)
            frame_duration = fps_den / fps_num
            t_origin: float | None = None

            while True:
                frame = read_frame(gz)
                if frame is None:
                    break
                frame_no, _flags, data = frame

                if t_origin is None:
                    t_origin = time.monotonic() - frame_no * frame_duration

                try:
                    conn.send(data)
                except OSError:
                    return 'disconnected'

                deadline = t_origin + (frame_no + 1) * frame_duration

                if conn.recv_ready():
                    try:
                        raw = conn.recv(256)
                    except OSError:
                        return 'disconnected'
                    if not raw:
                        return 'disconnected'
                    if b'q' in conn.input_filter(raw).lower():
                        return 'quit'

                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)

    except (ValueError, struct.error, ZeroDivisionError, gzip.BadGzipFile) as e:
        log.error('corrupt file %s: %s', path.name, e)
        try:
            conn.send(
                f'\r\n  [Error: {path.name} could not be played'
                f' — try re-rendering: python convert.py --force]\r\n'.encode()
            )
            time.sleep(2)
        except OSError:
            return 'disconnected'

    return 'ended'
