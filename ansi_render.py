#!/usr/bin/env python3
"""
ansi_render.py — Universal ANSI art video renderer

Converts video files to xterm-256 colour ANSI art streams (.ansi.gz)
for playback in a terminal (e.g., via a telnet server).

Output format: gzip-compressed binary stream
  Header (16 bytes, big-endian): magic "ANSI" + fps_num (uint32) + fps_den (uint32)
                                 + version (uint16, currently 1) + cols (uint8) + rows (uint8)
  Per frame: frame_number + flags (bit0=keyframe) + data_length + ANSI bytes

Terminal layout (default 80×25):
  Row  1        : blank letterbox
  Rows 2–23     : video (22 char rows = 44 effective pixel rows via half-block ▀)
  Row 24        : blank letterbox
  Row 25        : subtitle (centered, white on black)

Examples:
  python ansi_render.py video.mkv
  python ansi_render.py /path/to/season/
  python ansi_render.py *.mkv --sub-track 4 --cols 80 --rows 25
  python ansi_render.py video.mkv --no-subs
  python ansi_render.py video.mkv --sub-lang eng
  python ansi_render.py video.mkv --sub-file external.ass
  python ansi_render.py video.mkv --list-streams
"""

import argparse
import gzip
import json
import os
import re
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image


# ---------------------------------------------------------------------------
# Video file extensions to scan when given a directory
# ---------------------------------------------------------------------------

VIDEO_EXTENSIONS = {
    '.mkv', '.mp4', '.avi', '.mov', '.m4v', '.webm',
    '.flv', '.wmv', '.ts', '.m2ts', '.mpg', '.mpeg',
}


# ---------------------------------------------------------------------------
# xterm-256 colour palette and lookup
# ---------------------------------------------------------------------------

def _build_palette() -> list[tuple[int, int, int]]:
    standard = [
        (0,0,0),(128,0,0),(0,128,0),(128,128,0),
        (0,0,128),(128,0,128),(0,128,128),(192,192,192),
        (128,128,128),(255,0,0),(0,255,0),(255,255,0),
        (0,0,255),(255,0,255),(0,255,255),(255,255,255),
    ]
    palette = list(standard)
    cube_steps = [0, 95, 135, 175, 215, 255]
    for r in range(6):
        for g in range(6):
            for b in range(6):
                palette.append((cube_steps[r], cube_steps[g], cube_steps[b]))
    for i in range(24):
        v = 8 + i * 10
        palette.append((v, v, v))
    return palette

_PALETTE = _build_palette()
_PALETTE_RGB = _PALETTE[16:]   # indices 16-255 (240 entries)
_COLOR_CACHE: dict[tuple[int,int,int], int] = {}


def _rgb_to_xterm256(r: int, g: int, b: int) -> int:
    best_idx, best_dist = 16, 10**9
    for i, (pr, pg, pb) in enumerate(_PALETTE_RGB):
        d = (r-pr)**2 + (g-pg)**2 + (b-pb)**2
        if d < best_dist:
            best_dist = d
            best_idx = i + 16
            if d == 0:
                break
    return best_idx


def cached_xterm(r: int, g: int, b: int) -> int:
    key = (r, g, b)
    idx = _COLOR_CACHE.get(key)
    if idx is None:
        idx = _rgb_to_xterm256(r, g, b)
        _COLOR_CACHE[key] = idx
    return idx


# ---------------------------------------------------------------------------
# Layout: terminal geometry
# ---------------------------------------------------------------------------

@dataclass
class Layout:
    cols: int           # terminal columns
    total_rows: int     # total terminal rows
    letterbox_top: int  # blank rows above video area
    letterbox_bot: int  # blank rows below video area
    subtitle_rows: int  # 0 or 1 subtitle row at the very bottom

    @property
    def video_rows(self) -> int:
        return self.total_rows - self.letterbox_top - self.letterbox_bot - self.subtitle_rows

    @property
    def pixel_w(self) -> int:
        return self.cols

    @property
    def pixel_h(self) -> int:
        return self.video_rows * 2  # half-block: 2 pixels per char row

    @property
    def frame_bytes(self) -> int:
        return self.pixel_w * self.pixel_h * 3

    @property
    def video_start_row(self) -> int:
        return self.letterbox_top + 1  # 1-indexed first display row of video

    @property
    def subtitle_row(self) -> int:
        return self.total_rows  # 1-indexed


def make_layout(cols: int, rows: int, no_letterbox: bool, no_subs: bool) -> Layout:
    subtitle_rows = 0 if no_subs else 1
    if no_letterbox:
        lb_top, lb_bot = 0, 0
    else:
        lb_top, lb_bot = 1, 1
    layout = Layout(
        cols=cols,
        total_rows=rows,
        letterbox_top=lb_top,
        letterbox_bot=lb_bot,
        subtitle_rows=subtitle_rows,
    )
    if layout.video_rows <= 0:
        raise ValueError(
            f"Layout leaves no room for video: {rows} rows - "
            f"{lb_top} top - {lb_bot} bottom - {subtitle_rows} subtitle = "
            f"{layout.video_rows}"
        )
    return layout


# ---------------------------------------------------------------------------
# Subtitle parsing — ASS
# ---------------------------------------------------------------------------

_ASS_TAG = re.compile(r'\{[^}]*\}')
_ASS_NEWLINE = re.compile(r'\\[nN]')
_ASS_DIALOGUE = re.compile(
    r'^Dialogue:.*?(\d+):(\d{2}):(\d{2})\.(\d{2}),'
    r'(\d+):(\d{2}):(\d{2})\.(\d{2}),.*?,.*?,.*?,.*?,.*?,.*?,(.*)',
    re.MULTILINE,
)


def _ass_ts(h, m, s, cs) -> float:
    return int(h)*3600 + int(m)*60 + int(s) + int(cs)/100.0


def _load_ass(path: str) -> list[tuple[float, float, str]]:
    with open(path, encoding='utf-8-sig', errors='replace') as f:
        text = f.read()
    entries = []
    for m in _ASS_DIALOGUE.finditer(text):
        sh, sm, ss, scs, eh, em, es, ecs, raw = m.groups()
        start = _ass_ts(sh, sm, ss, scs)
        end   = _ass_ts(eh, em, es, ecs)
        plain = _ASS_TAG.sub('', raw)
        plain = _ASS_NEWLINE.sub(' ', plain).strip()
        if plain:
            entries.append((start, end, plain))
    entries.sort(key=lambda x: x[0])
    return entries


# ---------------------------------------------------------------------------
# Subtitle parsing — SRT
# ---------------------------------------------------------------------------

_SRT_TIMESTAMP = re.compile(
    r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*'
    r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})'
)
_HTML_TAG = re.compile(r'<[^>]+>')


def _srt_ts(h, m, s, ms) -> float:
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0


def _load_srt(path: str) -> list[tuple[float, float, str]]:
    with open(path, encoding='utf-8-sig', errors='replace') as f:
        text = f.read()
    entries = []
    blocks = re.split(r'\n{2,}', text.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        m = None
        text_lines = []
        for line in lines:
            if m is None:
                m = _SRT_TIMESTAMP.match(line)
                if m:
                    continue
            elif m is not None:
                text_lines.append(line)
        if m and text_lines:
            sh, sm, ss, sms, eh, em, es, ems = m.groups()
            start = _srt_ts(sh, sm, ss, sms)
            end   = _srt_ts(eh, em, es, ems)
            plain = ' '.join(text_lines)
            plain = _HTML_TAG.sub('', plain).strip()
            if plain:
                entries.append((start, end, plain))
    entries.sort(key=lambda x: x[0])
    return entries


def load_subtitles(path: str) -> list[tuple[float, float, str]]:
    ext = Path(path).suffix.lower()
    if ext == '.srt':
        return _load_srt(path)
    return _load_ass(path)  # .ass / .ssa / anything else


def get_subtitle(entries: list, ts: float) -> str:
    lo, hi = 0, len(entries)
    while lo < hi:
        mid = (lo + hi) // 2
        if entries[mid][1] <= ts:
            lo = mid + 1
        else:
            hi = mid
    for i in range(max(0, lo-1), min(len(entries), lo+3)):
        s, e, t = entries[i]
        if s <= ts < e:
            return t
    return ''


# ---------------------------------------------------------------------------
# Frame → cell list  (Cell = (fg_xterm, bg_xterm), char always ▀)
# ---------------------------------------------------------------------------

Cell = tuple[int, int]
BLANK_CELL: Cell = (16, 16)  # black on black


def image_to_cells(img: Image.Image, layout: Layout) -> list[Cell]:
    img = img.resize((layout.pixel_w, layout.pixel_h), Image.LANCZOS).convert('RGB')
    pixels = img.load()
    cells: list[Cell] = []
    for py in range(0, layout.pixel_h, 2):
        for px in range(layout.pixel_w):
            r1, g1, b1 = pixels[px, py]
            r2, g2, b2 = pixels[px, py+1]
            cells.append((cached_xterm(r1, g1, b1), cached_xterm(r2, g2, b2)))
    return cells  # layout.video_rows * layout.cols entries


# ---------------------------------------------------------------------------
# ANSI frame builders
# ---------------------------------------------------------------------------

_HALF_BLOCK = b'\xe2\x96\x80'  # UTF-8 for ▀ (U+2580)
_BLACK_CELL_ESC = b'\x1b[38;5;16;48;5;16m'


def full_frame_ansi(video_cells: list[Cell], subtitle: str, layout: Layout, clear: bool = True) -> bytes:
    buf = BytesIO()

    if clear:
        buf.write(b'\x1b[2J')
    buf.write(b'\x1b[?7l')  # disable line wrap

    prev_fg = prev_bg = -1

    def _move(row: int, col: int = 1):
        buf.write(f'\x1b[{row};{col}H'.encode())

    # Letterbox rows above video
    for lb_row in range(1, layout.letterbox_top + 1):
        _move(lb_row)
        buf.write(_BLACK_CELL_ESC)
        prev_fg = prev_bg = 16
        buf.write(_HALF_BLOCK * layout.cols)

    # Video rows
    for row in range(layout.video_rows):
        display_row = layout.video_start_row + row
        _move(display_row)
        base = row * layout.cols
        for col in range(layout.cols):
            fg, bg = video_cells[base + col]
            if fg != prev_fg or bg != prev_bg:
                buf.write(f'\x1b[38;5;{fg};48;5;{bg}m'.encode())
                prev_fg, prev_bg = fg, bg
            buf.write(_HALF_BLOCK)

    # Letterbox rows below video
    lb_start = layout.video_start_row + layout.video_rows
    for lb_row in range(lb_start, lb_start + layout.letterbox_bot):
        _move(lb_row)
        if prev_fg != 16 or prev_bg != 16:
            buf.write(_BLACK_CELL_ESC)
            prev_fg = prev_bg = 16
        buf.write(_HALF_BLOCK * layout.cols)

    # Subtitle row
    if layout.subtitle_rows:
        _move(layout.subtitle_row)
        buf.write(b'\x1b[K')
        if subtitle:
            line = subtitle[:layout.cols].center(layout.cols)
            buf.write(b'\x1b[38;5;231;48;5;16m')
            buf.write(line.encode('utf-8', errors='replace'))

    buf.write(b'\x1b[0m')
    return buf.getvalue()


def delta_frame_ansi(
    prev_cells: list[Cell],
    curr_cells: list[Cell],
    subtitle: str,
    prev_subtitle: str,
    layout: Layout,
) -> bytes:
    buf = BytesIO()
    prev_fg = prev_bg = -1

    for row in range(layout.video_rows):
        base = row * layout.cols
        display_row = layout.video_start_row + row
        col = 0
        while col < layout.cols:
            if curr_cells[base+col] == prev_cells[base+col]:
                col += 1
                continue
            run_start = col
            run_buf = BytesIO()
            lfg = prev_fg
            lbg = prev_bg
            while col < layout.cols and curr_cells[base+col] != prev_cells[base+col]:
                fg, bg = curr_cells[base+col]
                if fg != lfg or bg != lbg:
                    run_buf.write(f'\x1b[38;5;{fg};48;5;{bg}m'.encode())
                    lfg, lbg = fg, bg
                run_buf.write(_HALF_BLOCK)
                col += 1
            buf.write(f'\x1b[{display_row};{run_start+1}H'.encode())
            buf.write(run_buf.getvalue())
            prev_fg, prev_bg = lfg, lbg

    if layout.subtitle_rows and subtitle != prev_subtitle:
        buf.write(f'\x1b[{layout.subtitle_row};1H\x1b[K'.encode())
        if subtitle:
            line = subtitle[:layout.cols].center(layout.cols)
            buf.write(b'\x1b[38;5;231;48;5;16m')
            buf.write(line.encode('utf-8', errors='replace'))
        buf.write(b'\x1b[0m')

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Output file format helpers
# ---------------------------------------------------------------------------

FLAG_KEYFRAME = 0x01


CURRENT_VERSION = 1


def write_header(fh, fps_num: int, fps_den: int, cols: int, rows: int):
    fh.write(struct.pack('>4sIIHBB', b'ANSI', fps_num, fps_den, CURRENT_VERSION, cols, rows))


def write_frame(fh, frame_no: int, flags: int, data: bytes):
    fh.write(struct.pack('>III', frame_no, flags, len(data)))
    fh.write(data)


# ---------------------------------------------------------------------------
# FFmpeg / ffprobe helpers
# ---------------------------------------------------------------------------

_FFMPEG_INSTALL = (
    "  Linux:   sudo apt install ffmpeg\n"
    "  macOS:   brew install ffmpeg\n"
    "  Windows: https://www.gyan.dev/ffmpeg/builds/"
)


def _find_tool(name: str, hint: Optional[str]) -> str:
    """Resolve ffmpeg/ffprobe: explicit hint > script dir > PATH."""
    if hint:
        return hint
    # Script-adjacent binary (Windows: .exe)
    for ext in ('', '.exe'):
        candidate = Path(__file__).parent / (name + ext)
        if candidate.exists():
            return str(candidate)
    # Fall back to PATH
    return name


def probe_streams(video_path: str, ffprobe: str) -> list[dict]:
    cmd = [
        ffprobe, '-v', 'quiet',
        '-print_format', 'json',
        '-show_streams',
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return json.loads(result.stdout).get('streams', [])
    except FileNotFoundError:
        sys.exit(
            f"ERROR: ffprobe not found.\n"
            f"       Make sure ffmpeg is installed and on your PATH:\n"
            f"{_FFMPEG_INSTALL}"
        )
    except Exception as e:
        print(f"  WARNING: ffprobe failed ({e}); stream info unavailable", file=sys.stderr)
        return []


def probe_fps(streams: list[dict]) -> tuple[int, int]:
    """Extract FPS from the first video stream; fall back to 24000/1001."""
    for s in streams:
        if s.get('codec_type') != 'video':
            continue
        for key in ('r_frame_rate', 'avg_frame_rate'):
            fps_str = s.get(key, '')
            if fps_str and fps_str != '0/0':
                try:
                    if '/' in fps_str:
                        num, den = fps_str.split('/')
                        return int(num), int(den)
                    val = float(fps_str)
                    return int(val * 1000), 1000
                except ValueError:
                    pass
    return 24000, 1001  # safe default


def find_subtitle_stream(
    streams: list[dict],
    track_index: Optional[int],
    lang: Optional[str],
    title_substr: Optional[str],
) -> Optional[int]:
    """
    Return the global stream index to use for subtitle extraction, or None.

    Priority: explicit index > language match > title substring match > first subtitle stream.
    """
    sub_streams = [(i, s) for i, s in enumerate(streams) if s.get('codec_type') == 'subtitle']
    if not sub_streams:
        return None

    if track_index is not None:
        for i, s in sub_streams:
            if i == track_index:
                return i
        print(f"  WARNING: no subtitle stream at index {track_index}", file=sys.stderr)
        return None

    if lang:
        for i, s in sub_streams:
            if s.get('tags', {}).get('language', '').lower() == lang.lower():
                return i
        print(f"  WARNING: no subtitle stream with language '{lang}'", file=sys.stderr)

    if title_substr:
        for i, s in sub_streams:
            t = s.get('tags', {}).get('title', '')
            if title_substr.lower() in t.lower():
                return i
        print(f"  WARNING: no subtitle stream with title containing '{title_substr}'", file=sys.stderr)

    # Default: first subtitle stream
    return sub_streams[0][0]


def extract_subtitle(
    video_path: str,
    stream_index: int,
    out_path: str,
    ffmpeg: str,
) -> bool:
    """Extract subtitle stream to an ASS file (ffmpeg converts any format to ASS)."""
    cmd = [
        ffmpeg, '-y',
        '-i', video_path,
        '-map', f'0:{stream_index}',
        '-c:s', 'ass',
        out_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        sys.exit(
            f"ERROR: ffmpeg not found.\n"
            f"       Make sure ffmpeg is installed and on your PATH:\n"
            f"{_FFMPEG_INSTALL}"
        )
    if result.returncode != 0:
        print(f"  ERROR extracting subtitle: {result.stderr[-400:]}", file=sys.stderr)
        return False
    return True


def open_frame_pipe(video_path: str, layout: Layout, ffmpeg: str, preserve_aspect: bool) -> subprocess.Popen:
    """Open an ffmpeg pipe delivering raw RGB24 frames at layout.pixel_w × layout.pixel_h."""
    w, h = layout.pixel_w, layout.pixel_h
    if preserve_aspect:
        scale = (
            f'scale={w}:{h}:force_original_aspect_ratio=decrease:eval=init,'
            f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2'
        )
    else:
        scale = f'scale={w}:{h}'
    cmd = [
        ffmpeg,
        '-i', video_path,
        '-an', '-sn',
        '-vf', scale,
        '-pix_fmt', 'rgb24',
        '-f', 'rawvideo',
        '-',
    ]
    try:
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=layout.frame_bytes * 30,
        )
    except FileNotFoundError:
        sys.exit(
            f"ERROR: ffmpeg not found.\n"
            f"       Make sure ffmpeg is installed and on your PATH:\n"
            f"{_FFMPEG_INSTALL}"
        )


# ---------------------------------------------------------------------------
# Core render loop
# ---------------------------------------------------------------------------

def render_video(
    video_path: str,
    sub_path: Optional[str],
    out_path: str,
    layout: Layout,
    fps_num: int,
    fps_den: int,
    ffmpeg: str,
    keyframe_interval_s: float = 5.0,
    duration_s: Optional[float] = None,
    preserve_aspect: bool = False,
):
    subtitles: list = []
    if sub_path and layout.subtitle_rows:
        print(f"  Loading subtitles: {sub_path}")
        subtitles = load_subtitles(sub_path)
        print(f"  {len(subtitles)} subtitle entries loaded")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    keyframe_interval_frames = max(1, int(keyframe_interval_s * fps_num / fps_den))

    print(f"  Opening ffmpeg pipe: {Path(video_path).name}")
    proc = open_frame_pipe(video_path, layout, ffmpeg, preserve_aspect)

    with gzip.open(out_path, 'wb', compresslevel=6) as gz:
        write_header(gz, fps_num, fps_den, layout.cols, layout.total_rows)

        prev_cells: list[Cell] = [BLANK_CELL] * (layout.video_rows * layout.cols)
        prev_subtitle = ''
        frame_no = 0
        t_start = time.time()
        last_report = 0.0

        try:
            while True:
                raw = proc.stdout.read(layout.frame_bytes)
                if len(raw) < layout.frame_bytes:
                    break

                timestamp_s = frame_no * fps_den / fps_num
                if duration_s is not None and timestamp_s > duration_s:
                    break

                img = Image.frombytes('RGB', (layout.pixel_w, layout.pixel_h), raw)
                curr_cells = image_to_cells(img, layout)
                subtitle = get_subtitle(subtitles, timestamp_s) if subtitles else ''

                is_keyframe = (frame_no % keyframe_interval_frames == 0)
                if is_keyframe:
                    data = full_frame_ansi(curr_cells, subtitle, layout, clear=True)
                    flags = FLAG_KEYFRAME
                else:
                    data = delta_frame_ansi(prev_cells, curr_cells, subtitle, prev_subtitle, layout)
                    flags = 0

                write_frame(gz, frame_no, flags, data)
                prev_cells = curr_cells
                prev_subtitle = subtitle
                frame_no += 1

                now = time.time()
                if now - last_report >= 5:
                    elapsed = now - t_start
                    fps_actual = frame_no / elapsed if elapsed > 0 else 0
                    print(f"    frame {frame_no:6d}  video {timestamp_s:7.1f}s  "
                          f"{fps_actual:.1f} fps rendered  "
                          f"out: {gz.tell() // 1024} KB", flush=True)
                    last_report = now

        finally:
            proc.stdout.close()
            proc.wait()

    size_mb = os.path.getsize(out_path) / (1024**2)
    print(f"  Done: {frame_no} frames → {out_path} ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# Input file collection
# ---------------------------------------------------------------------------

def collect_inputs(paths: list[str], recursive: bool) -> list[Path]:
    results = []
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            if p.suffix.lower() in VIDEO_EXTENSIONS:
                results.append(p)
            else:
                print(f"WARNING: skipping non-video file: {p}", file=sys.stderr)
        elif p.is_dir():
            if recursive:
                found = sorted(q for q in p.rglob('*') if q.suffix.lower() in VIDEO_EXTENSIONS)
            else:
                found = sorted(q for q in p.iterdir() if q.suffix.lower() in VIDEO_EXTENSIONS)
            if not found:
                print(f"WARNING: no video files found in {p}", file=sys.stderr)
            results.extend(found)
        else:
            # Glob already expanded by shell on Unix; on Windows we handle it
            import glob as _glob
            matched = [Path(m) for m in _glob.glob(str(p))
                       if Path(m).suffix.lower() in VIDEO_EXTENSIONS]
            if matched:
                results.extend(sorted(matched))
            else:
                print(f"WARNING: no match for: {raw}", file=sys.stderr)
    return results


# ---------------------------------------------------------------------------
# --list-streams helper
# ---------------------------------------------------------------------------

def list_streams(video_path: str, ffprobe: str):
    streams = probe_streams(video_path, ffprobe)
    print(f"\n{video_path}")
    print(f"  {'IDX':>4}  {'TYPE':10}  {'CODEC':12}  {'LANG':6}  TITLE")
    print(f"  {'-'*4}  {'-'*10}  {'-'*12}  {'-'*6}  -----")
    for i, s in enumerate(streams):
        codec_type = s.get('codec_type', '?')
        codec_name = s.get('codec_name', '?')
        lang = s.get('tags', {}).get('language', '')
        title = s.get('tags', {}).get('title', '')
        marker = '  <-- subtitle' if codec_type == 'subtitle' else ''
        print(f"  {i:>4}  {codec_type:10}  {codec_name:12}  {lang:6}  {title}{marker}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='Convert video files to xterm-256 ANSI art streams (.ansi.gz)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    p.add_argument('inputs', nargs='+', metavar='INPUT',
                   help='Video files or directories')

    # Output
    p.add_argument('--output-dir', default='output', metavar='DIR',
                   help='Directory for .ansi.gz output files (default: ./output)')
    p.add_argument('--sub-dir', default='subs', metavar='DIR',
                   help='Directory to cache extracted .ass files (default: ./subs)')
    p.add_argument('--force', action='store_true',
                   help='Re-render even if output already exists')

    # Layout
    layout = p.add_argument_group('layout')
    layout.add_argument('--cols', type=int, default=80, metavar='N',
                        help='Terminal columns (default: 80)')
    layout.add_argument('--rows', type=int, default=25, metavar='N',
                        help='Terminal rows (default: 25)')
    layout.add_argument('--no-letterbox', action='store_true',
                        help='Remove blank letterbox rows above/below video')
    layout.add_argument('--no-subs', action='store_true',
                        help='Disable subtitle rendering (use all rows for video)')
    layout.add_argument('--preserve-aspect', action='store_true',
                        help='Letterbox/pillarbox video to preserve source aspect ratio')

    # Subtitles
    subs = p.add_argument_group('subtitles')
    subs.add_argument('--sub-track', type=int, default=None, metavar='INDEX',
                      help='Global stream index of subtitle track (see --list-streams)')
    subs.add_argument('--sub-lang', default=None, metavar='LANG',
                      help='Select subtitle track by language code (e.g. eng, jpn)')
    subs.add_argument('--sub-title', default=None, metavar='TEXT',
                      help='Select subtitle track whose title contains TEXT')
    subs.add_argument('--sub-file', default=None, metavar='FILE',
                      help='External subtitle file (.ass/.srt) — skips extraction')

    # FPS
    fps = p.add_argument_group('fps')
    fps.add_argument('--fps-num', type=int, default=None, metavar='N',
                     help='Override FPS numerator (default: auto-detect)')
    fps.add_argument('--fps-den', type=int, default=None, metavar='N',
                     help='Override FPS denominator (default: auto-detect)')

    # Render options
    render = p.add_argument_group('render')
    render.add_argument('--duration', type=float, default=None, metavar='SECONDS',
                        help='Only render the first N seconds (for testing)')
    render.add_argument('--keyframe-interval', type=float, default=5.0, metavar='SECONDS',
                        help='Full-redraw interval in seconds (default: 5)')
    render.add_argument('--recursive', '-r', action='store_true',
                        help='Recurse into sub-directories when given a directory')

    # Tools
    tools = p.add_argument_group('tools')
    tools.add_argument('--ffmpeg', default=None, metavar='PATH',
                       help='Path to ffmpeg binary (default: auto-detect)')
    tools.add_argument('--ffprobe', default=None, metavar='PATH',
                       help='Path to ffprobe binary (default: auto-detect)')

    # Info modes
    p.add_argument('--list-streams', action='store_true',
                   help='Print stream info for each input file and exit')

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    ffmpeg  = _find_tool('ffmpeg',  args.ffmpeg)
    ffprobe = _find_tool('ffprobe', args.ffprobe)

    video_files = collect_inputs(args.inputs, args.recursive)
    if not video_files:
        print("No video files found.", file=sys.stderr)
        sys.exit(1)

    # --list-streams mode: print stream info and exit
    if args.list_streams:
        for vf in video_files:
            list_streams(str(vf), ffprobe)
        return

    # Build layout
    try:
        layout = make_layout(
            cols=args.cols,
            rows=args.rows,
            no_letterbox=args.no_letterbox,
            no_subs=args.no_subs,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Layout: {layout.cols}×{layout.total_rows} terminal, "
          f"{layout.video_rows} video rows, "
          f"pixel grid {layout.pixel_w}×{layout.pixel_h}"
          + (" [no letterbox]" if args.no_letterbox else "")
          + (" [no subs]" if args.no_subs else ""))

    out_dir  = Path(args.output_dir)
    subs_dir = Path(args.sub_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    total_files = len(video_files)
    skipped = rendered = failed = 0
    t_all = time.time()

    for idx, vf in enumerate(video_files, 1):
        out_path = out_dir / (vf.stem + '.ansi.gz')
        print(f"\n[{idx}/{total_files}] {vf.name}")

        if out_path.exists() and args.duration is None and not args.force:
            print(f"  SKIP: output exists → {out_path}  [use --force to overwrite]")
            skipped += 1
            continue

        # Probe streams for FPS and subtitle auto-detection
        streams = probe_streams(str(vf), ffprobe)

        fps_num, fps_den = probe_fps(streams)
        if args.fps_num:
            fps_num = args.fps_num
        if args.fps_den:
            fps_den = args.fps_den

        # Subtitle handling
        sub_path: Optional[str] = None

        if not args.no_subs and layout.subtitle_rows:
            if args.sub_file:
                sub_path = args.sub_file
            else:
                stream_idx = find_subtitle_stream(
                    streams,
                    track_index=args.sub_track,
                    lang=args.sub_lang,
                    title_substr=args.sub_title,
                )
                if stream_idx is not None:
                    subs_dir.mkdir(parents=True, exist_ok=True)
                    sub_path = str(subs_dir / (vf.stem + '.ass'))
                    if os.path.exists(sub_path):
                        print(f"  Subtitle cache hit: {Path(sub_path).name}")
                    else:
                        print(f"  Extracting subtitle stream {stream_idx} → {Path(sub_path).name}")
                        ok = extract_subtitle(str(vf), stream_idx, sub_path, ffmpeg)
                        if not ok:
                            print("  WARNING: subtitle extraction failed; rendering without subs")
                            sub_path = None
                else:
                    print("  No subtitle stream found; rendering without subs")

        try:
            render_video(
                video_path=str(vf),
                sub_path=sub_path,
                out_path=str(out_path),
                layout=layout,
                fps_num=fps_num,
                fps_den=fps_den,
                ffmpeg=ffmpeg,
                keyframe_interval_s=args.keyframe_interval,
                duration_s=args.duration,
                preserve_aspect=args.preserve_aspect,
            )
            rendered += 1
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr)
            failed += 1

    # Summary
    elapsed_total = time.time() - t_all
    print(f"\n{'='*60}")
    print(f"  Done in {elapsed_total:.0f}s - "
          f"{rendered} rendered, {skipped} skipped, {failed} failed")
    if out_dir.is_dir():
        files = sorted(out_dir.glob('*.ansi.gz'))
        if files:
            total_bytes = sum(f.stat().st_size for f in files)
            print(f"  Output ({out_dir}):")
            for f in files:
                sz = f.stat().st_size
                print(f"    {f.name:50s}  {sz/1048576:6.1f} MB")
            print(f"    {'TOTAL':50s}  {total_bytes/1048576:6.1f} MB")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
