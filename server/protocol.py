"""Telnet protocol constants and IAC/NAWS helpers."""

IAC  = 255
WILL = 251
WONT = 252
DO   = 253
DONT = 254
SB   = 250
SE   = 240

OPT_ECHO = 1
OPT_SGA  = 3   # Suppress Go-Ahead
OPT_NAWS = 31  # Negotiate About Window Size

# Sent immediately on connect: we suppress go-ahead, echo, and request window size
NEGOTIATE = bytes([
    IAC, WILL, OPT_SGA,
    IAC, WILL, OPT_ECHO,
    IAC, DO,   OPT_NAWS,
])


def strip_iac(data: bytes) -> bytes:
    """Remove telnet IAC command sequences from raw received bytes."""
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b != IAC:
            out.append(b)
            i += 1
            continue
        i += 1
        if i >= len(data):
            break
        cmd = data[i]
        i += 1
        if cmd == IAC:
            out.append(0xFF)          # escaped 0xFF literal
        elif cmd in (WILL, WONT, DO, DONT):
            i += 1                    # skip one-byte option
        elif cmd == SB:
            while i < len(data) - 1:  # skip subnegotiation until IAC SE
                if data[i] == IAC and data[i + 1] == SE:
                    i += 2
                    break
                i += 1
    return bytes(out)


def parse_naws(data: bytes) -> tuple[int, int] | None:
    """Extract (width, height) from a NAWS subnegotiation block, or None."""
    i = 0
    while i < len(data) - 8:
        if data[i] == IAC and data[i + 1] == SB and data[i + 2] == OPT_NAWS:
            w = (data[i + 3] << 8) | data[i + 4]
            h = (data[i + 5] << 8) | data[i + 6]
            return w, h
        i += 1
    return None
