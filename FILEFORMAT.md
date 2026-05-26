# TTYFlix File Format

`.ansi.gz` files are the pre-rendered video container used by TTYFlix.
Each file is a **gzip-compressed binary stream** whose payload consists of a
fixed-size file header followed by a sequence of frame records.

All multi-byte integers are **big-endian**.

---

## File layout

```
┌─────────────────────────────────┐
│  File header  (16 bytes)        │
├─────────────────────────────────┤
│  Frame record 0                 │
│    Frame header  (12 bytes)     │
│    ANSI payload  (variable)     │
├─────────────────────────────────┤
│  Frame record 1                 │
│  ...                            │
└─────────────────────────────────┘
```

---

## File header (16 bytes)

| Offset | Size | Type      | Field          | Description                                        |
|--------|------|-----------|----------------|----------------------------------------------------|
| 0      | 4    | bytes     | `magic`        | Always `ANSI` (0x41 0x4E 0x53 0x49)               |
| 4      | 4    | uint32 BE | `fps_num`      | Framerate numerator                                |
| 8      | 4    | uint32 BE | `fps_den`      | Framerate denominator                              |
| 12     | 2    | uint16 BE | `version`      | Format version — currently `1`                     |
| 14     | 1    | uint8     | `cols`         | Terminal columns the file was rendered for         |
| 15     | 1    | uint8     | `rows`         | Terminal rows the file was rendered for            |

The framerate is stored as a rational number so that NTSC rates can be
represented exactly:

| Rate   | `fps_num` | `fps_den` |
|--------|-----------|-----------|
| 24 fps | 24        | 1         |
| 23.976 | 24000     | 1001      |
| 29.97  | 30000     | 1001      |
| 30 fps | 30        | 1         |
| 60 fps | 60        | 1         |

`version` is `1` for all files produced by the current implementation.
Readers **must** reject files with an unrecognised version rather than
attempting to parse them, since future versions may change the frame record
layout or payload encoding. The frame count is not stored in the header;
readers should determine it by reading the stream to EOF.

`cols` and `rows` are the terminal dimensions the file was rendered for.
A player should ensure the terminal is at least this size before streaming,
or warn the viewer if it cannot verify the size.

---

## Frame record

Each frame record immediately follows the previous one with no padding.

### Frame header (12 bytes)

| Offset | Size | Type      | Field      | Description                        |
|--------|------|-----------|------------|------------------------------------|
| 0      | 4    | uint32 BE | `frame_no` | Sequential frame number (0-based)  |
| 4      | 4    | uint32 BE | `flags`    | Bit flags (see below)              |
| 8      | 4    | uint32 BE | `data_len` | Length of the ANSI payload (bytes) |

### Flags

| Bit  | Mask     | Name        | Description                                                 |
|------|----------|-------------|-------------------------------------------------------------|
| 0    | `0x01`   | `KEYFRAME`  | Full repaint — does not depend on previous frame            |
| 1–31 | `0xFFFFFFFE` | *(reserved)* | Reserved for future use; readers should ignore unknown bits |

### ANSI payload

`data_len` bytes of UTF-8 encoded ANSI/VT100 escape sequences, ready to be
written directly to a terminal or telnet socket. No further processing is
required by the server.

---

## Frame types

### Keyframe (`flags & 0x01 == 1`)

A keyframe repaints the entire screen from scratch. It is self-contained and
can be decoded without any prior frame state. Keyframes are emitted at a
configurable interval (default: every 5 seconds) and always at frame 0.

A keyframe payload typically contains:

1. `ESC[2J` — clear screen
2. `ESC[?7l` — disable line wrap
3. Black half-block characters for any letterbox rows
4. Colour-coded half-block characters for all video rows
5. `ESC[K` + subtitle text for the subtitle row (if present)
6. `ESC[0m` — reset attributes

### Delta frame (`flags & 0x01 == 0`)

A delta frame encodes only the cells that differ from the previous frame. Each
changed run is preceded by a cursor-position escape (`ESC[{row};{col}H`) and
followed by the minimum number of colour/character sequences needed to paint
that run. Unchanged cells are skipped entirely.

Delta frames may be empty (0 bytes of payload) for static content.

---

## Terminal layout

The renderer and server share a common layout model. Given a terminal of
`cols × rows` characters:

```
Row 1                     ← letterbox (blank, black half-blocks)
Row 2 … rows-2           ← video area
Row rows-1                ← letterbox (blank, black half-blocks)
Row rows                  ← subtitle (centered white text on black, or blank)
```

The **video area** occupies `rows - 3` character rows (1 top letterbox + 1
bottom letterbox + 1 subtitle row). Each character row encodes 2 pixel rows
via the half-block trick, giving an effective pixel height of `(rows - 3) × 2`.

With `--no-letterbox` the letterbox rows are removed; with `--no-subs` the
subtitle row is also removed, giving all rows to video.

---

## Colour encoding

All colours use **xterm-256** palette indices. Only the 216-colour cube
(indices 16–231) is used by the renderer — the 16 ANSI colours (0–15) and
the 24-step greyscale ramp (232–255) are not emitted but are valid in the
format.

Each cell is encoded with a combined SGR sequence:

```
ESC[38;5;{fg};48;5;{bg}m▀
```

Where `{fg}` is the foreground (top-pixel) colour index and `{bg}` is the
background (bottom-pixel) colour index. Consecutive cells sharing the same
`fg` and `bg` values omit the SGR sequence and emit only `▀`.

---

## Reading a file (pseudocode)

```python
import gzip, struct

MAGIC = b'ANSI'

with gzip.open('video.ansi.gz', 'rb') as f:
    # File header
    raw = f.read(16)
    magic, fps_num, fps_den, version, cols, rows = struct.unpack('>4sIIHBB', raw)
    assert magic == MAGIC
    assert version == 1, f'Unsupported version: {version}'
    frame_duration = fps_den / fps_num  # seconds per frame
    # cols x rows is the terminal size the file was rendered for

    # Frame records
    while True:
        hdr = f.read(12)
        if len(hdr) < 12:
            break  # EOF
        frame_no, flags, data_len = struct.unpack('>III', hdr)
        data = f.read(data_len)

        is_keyframe = bool(flags & 0x01)
        # `data` is raw ANSI bytes — write directly to terminal/socket
```

---

## Compatibility notes

- The format is intentionally minimal. Any language that can read gzip and
  parse big-endian integers can implement a player.
- The ANSI payload uses only widely-supported VT100/xterm sequences. It has
  been tested with PuTTY, xterm, iTerm2, Windows Terminal, and the Linux
  console.
- `version` must be `1`; readers should reject files with any other value.
- `cols` and `rows` are uint8 (max 255 each), sufficient for all realistic
  terminal sizes used with ANSI art.
- Future flag bits are reserved. Readers should ignore unknown flag bits
  rather than rejecting the frame.
