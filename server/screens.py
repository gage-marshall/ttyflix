"""
Terminal screens: capability check and episode menu.

Both screens are resolution-aware — they read required dimensions from
ServerConfig so they automatically adapt when --hd or custom --cols/--rows
are used.
"""

from .catalog import Entry
from .config import ServerConfig

# Colour palette
_C_RESET = b'\x1b[0m'
_C_TITLE = b'\x1b[38;5;201m'   # magenta
_C_KEY   = b'\x1b[38;5;226m'   # yellow
_C_ENTRY = b'\x1b[38;5;255m'   # white
_C_DIM   = b'\x1b[38;5;244m'   # grey
_C_RULE  = b'\x1b[38;5;57m'    # purple
_C_RED   = b'\x1b[38;5;196m'
_C_GREEN = b'\x1b[38;5;46m'

_ENC_BOX = '┌──┐ │  │ └──┘ ─ │ █'
_ENC_COLORS = [
    (_C_TITLE, b'MAGENTA'),
    (_C_KEY,   b'YELLOW '),
    (_C_ENTRY, b'WHITE  '),
    (_C_DIM,   b'GREY   '),
    (_C_GREEN, b'GREEN  '),
]


def _rule(cols: int) -> bytes:
    return _C_RULE + ('─' * cols).encode('utf-8') + _C_RESET


def _move(row: int, col: int = 1) -> bytes:
    return f'\x1b[{row};{col}H'.encode()


def build_check_screen(
    client_w: int,
    client_h: int,
    naws_received: bool,
    config: ServerConfig,
) -> bytes:
    """
    Capability check screen shown to every new connection before the menu.

    Warns if the client terminal is smaller than config.cols x config.rows,
    so the threshold automatically raises when running in HD mode.
    """
    req_w, req_h = config.cols, config.rows
    rule = _rule(req_w)

    buf = bytearray()
    buf.extend(b'\x1b[2J\x1b[H\x1b[?25l\x1b[?7l')

    buf.extend(_C_RULE + b'  Terminal Capability Check' + _C_RESET + b'\r\n')
    buf.extend(rule + b'\r\n')
    buf.extend(
        _C_KEY + b'  REQUIREMENTS\r\n\r\n' + _C_RESET +
        b'  This server requires:\r\n'
        b'  * ANSI / VT100 escape sequence support\r\n'
        b'  * UTF-8 character encoding\r\n' +
        f'  * Terminal size: at least {req_w} x {req_h} characters\r\n\r\n'.encode() +
        _C_DIM + b'  SSH recommended: ssh anything@hostname (pre-installed on macOS/Linux/Win10+)\r\n' +
        _C_DIM + b'  Windows Telnet is not supported (CP437) - use PuTTY, WSL, or SSH instead.\r\n' +
        _C_RESET + b'\r\n'
    )
    buf.extend(rule + b'\r\n')

    buf.extend(_C_DIM + b'  Box chars  : ' + _C_RESET)
    buf.extend(_ENC_BOX.encode('utf-8') + b'\r\n')

    buf.extend(_C_DIM + b'  Colours    : ' + _C_RESET)
    for colour, label in _ENC_COLORS:
        buf.extend(colour + b'[' + label + b'] ' + _C_RESET)
    buf.extend(b'\r\n')

    buf.extend(rule + b'\r\n')

    has_warning = False

    if not naws_received:
        has_warning = True
        buf.extend(
            _C_RED +
            b'  Warning: could not detect your terminal size.\r\n' +
            f'           This server requires at least {req_w}x{req_h} characters.\r\n'.encode() +
            b'           Display may be corrupted if your terminal is too small.' +
            _C_RESET + b'\r\n'
        )
    elif client_w < req_w or client_h < req_h:
        has_warning = True
        buf.extend(
            _C_RED +
            f'  Warning: your terminal is {client_w}x{client_h}. '
            f'Minimum required is {req_w}x{req_h}.\r\n'.encode() +
            b'           Resize your terminal before continuing or display may be corrupted.' +
            _C_RESET + b'\r\n'
        )

    if not has_warning:
        buf.extend(
            _C_GREEN + b'  Your terminal meets all requirements.' + _C_RESET + b'\r\n'
        )

    buf.extend(b'\r\n')
    buf.extend(_C_DIM + b'  Press [ENTER] to continue...' + _C_RESET)

    return bytes(buf)


def build_menu(entries: list[Entry], config: ServerConfig) -> bytes:
    """
    Dynamic menu built from the catalog.

    Layout (all row counts relative to config.rows):
      Rows 1-3   : title banner (box border + title + box border)
      Row  4     : horizontal rule
      Rows 5 .. rows-2 : entry list (config.rows - 6 entries visible)
      Row  rows-1: controls hint
      Row  rows  : disconnect hint
    """
    cols = config.cols
    rows = config.rows
    max_visible = max(0, rows - 6)  # rows available for the entry list

    buf = bytearray()
    buf.extend(b'\x1b[2J\x1b[H\x1b[?7l\x1b[?25l')

    # Banner: 3-row box with server title
    top    = ('╔' + '═' * (cols - 2) + '╗').encode('utf-8')
    middle = ('║' + config.title.upper().center(cols - 2) + '║').encode('utf-8')
    bottom = ('╚' + '═' * (cols - 2) + '╝').encode('utf-8')
    buf.extend(_move(1) + _C_TITLE + top    + _C_RESET)
    buf.extend(_move(2) + _C_TITLE + middle + _C_RESET)
    buf.extend(_move(3) + _C_TITLE + bottom + _C_RESET)

    # Rule below banner
    buf.extend(_move(4) + _rule(cols))

    # Entry list
    visible = entries[:max_visible]
    for i, entry in enumerate(visible):
        row = 5 + i
        key_display = entry.key.upper() if entry.key.isalpha() else entry.key
        # Truncate title to avoid overflowing the line
        max_title = cols - 8  # '  [X]  ' prefix is 7 chars + 1 spare
        title = entry.title[:max_title]
        buf.extend(_move(row))
        buf.extend(
            _C_KEY   + f'  [{key_display}]'.encode() +
            b'  ' +
            _C_ENTRY + title.encode('utf-8', errors='replace') +
            _C_RESET
        )

    # Overflow notice if catalog has more entries than fit
    if len(entries) > max_visible:
        overflow_row = 5 + max_visible
        if overflow_row <= rows - 2:
            remaining = len(entries) - max_visible
            buf.extend(_move(overflow_row))
            buf.extend(
                _C_DIM +
                f'  ... and {remaining} more (increase --rows to show all)'.encode() +
                _C_RESET
            )

    # Empty catalog notice
    if not entries:
        buf.extend(_move(5))
        buf.extend(_C_DIM + b'  [ No content available ]' + _C_RESET)

    # Footer controls
    buf.extend(_move(rows - 1))
    buf.extend(_C_DIM + b'  [1-9 / A-Z] Select' + _C_RESET)

    buf.extend(_move(rows))
    buf.extend(_C_DIM + b'  [Q] Disconnect' + _C_RESET)

    return bytes(buf)
