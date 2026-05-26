#!/usr/bin/env python3
"""
convert.py — Render video files to .ansi.gz format for the telnet server.

Reads settings from config.toml and converts all video files found in the
configured input directory. Already-rendered files are skipped unless
--force is passed (or force = true is set in config.toml).

Usage:
  python convert.py                    render all new videos in videos/
  python convert.py --force            re-render everything
  python convert.py "My Video.mp4"     render one specific file
  python convert.py --list-streams v   show stream info for a video
"""

import argparse
import sys
import time
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # pip install tomli  (Python < 3.11)
    except ImportError:
        sys.exit("ERROR: Python 3.11+ is required, or install tomli: pip install tomli")

import ansi_render as _r

CONFIG_FILE = Path(__file__).parent / 'config.toml'


def _load_config(path: Path) -> dict:
    if not path.exists():
        sys.exit(
            f"ERROR: config.toml not found at {path}\n"
            f"       A default config.toml should have come with this toolkit."
        )
    with open(path, 'rb') as f:
        return tomllib.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Render videos to .ansi.gz for the telnet server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        'inputs', nargs='*', metavar='FILE',
        help='Specific video file(s) to convert. Omit to convert everything in input_dir.',
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Re-render even if output already exists (overrides config.toml)',
    )
    parser.add_argument(
        '--list-streams', metavar='FILE',
        help='Print stream info for a video file and exit (useful for subtitle selection)',
    )
    parser.add_argument(
        '--config', default=str(CONFIG_FILE), metavar='PATH',
        help=f'Path to config file (default: {CONFIG_FILE})',
    )
    args = parser.parse_args()

    cfg        = _load_config(Path(args.config))
    layout_cfg = cfg.get('layout', {})
    conv_cfg   = cfg.get('convert', {})
    sub_cfg    = cfg.get('subtitles', {})

    cols       = layout_cfg.get('cols', 80)
    rows       = layout_cfg.get('rows', 25)
    force      = args.force or conv_cfg.get('force', False)
    input_dir  = Path(conv_cfg.get('input_dir', 'videos'))
    output_dir = Path(conv_cfg.get('output_dir', 'output'))
    cache_dir  = Path(sub_cfg.get('cache_dir', 'subs'))
    preserve_aspect   = conv_cfg.get('preserve_aspect', True)
    keyframe_interval = float(conv_cfg.get('keyframe_interval', 5.0))
    subs_enabled = sub_cfg.get('enabled', True)
    sub_lang     = sub_cfg.get('language', '') or None

    ffmpeg  = _r._find_tool('ffmpeg',  None)
    ffprobe = _r._find_tool('ffprobe', None)

    # ── --list-streams mode ──────────────────────────────────────────────────
    if args.list_streams:
        _r.list_streams(args.list_streams, ffprobe)
        return

    # ── Collect input files ──────────────────────────────────────────────────
    if args.inputs:
        video_files = _r.collect_inputs(args.inputs, recursive=False)
    else:
        if not input_dir.is_dir():
            sys.exit(
                f"ERROR: input directory not found: {input_dir.resolve()}\n"
                f"       Create the '{input_dir}' folder and drop your videos into it,\n"
                f"       or set a different path with input_dir in config.toml."
            )
        video_files = _r.collect_inputs([str(input_dir)], recursive=True)

    if not video_files:
        print(
            f"No video files found in '{input_dir}'.\n"
            f"Supported formats: .mkv .mp4 .avi .mov .m4v .webm .flv .wmv .ts .m2ts .mpg .mpeg",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Build layout ─────────────────────────────────────────────────────────
    try:
        layout = _r.make_layout(
            cols=cols, rows=rows,
            no_letterbox=False,
            no_subs=not subs_enabled,
        )
    except ValueError as e:
        sys.exit(f"ERROR: {e}")

    print(f"Layout   : {cols}×{rows} terminal, {layout.video_rows} video rows, "
          f"pixel grid {layout.pixel_w}×{layout.pixel_h}")
    print(f"Input    : {input_dir.resolve()}")
    print(f"Output   : {output_dir.resolve()}")
    print()

    output_dir.mkdir(parents=True, exist_ok=True)

    total    = len(video_files)
    rendered = skipped = failed = 0
    t_all    = time.time()

    for idx, vf in enumerate(video_files, 1):
        out_path = output_dir / (vf.stem + '.ansi.gz')
        print(f"[{idx}/{total}] {vf.name}")

        if out_path.exists() and not force:
            print(f"  SKIP  already rendered (pass --force to re-render)")
            skipped += 1
            continue

        streams = _r.probe_streams(str(vf), ffprobe)
        fps_num, fps_den = _r.probe_fps(streams)

        sub_path = None
        if subs_enabled and layout.subtitle_rows:
            stream_idx = _r.find_subtitle_stream(
                streams, track_index=None, lang=sub_lang, title_substr=None,
            )
            if stream_idx is not None:
                cache_dir.mkdir(parents=True, exist_ok=True)
                sub_path = str(cache_dir / (vf.stem + '.ass'))
                if not Path(sub_path).exists():
                    print(f"  Extracting subtitle stream {stream_idx}")
                    if not _r.extract_subtitle(str(vf), stream_idx, sub_path, ffmpeg):
                        print("  WARNING: subtitle extraction failed; rendering without subs")
                        sub_path = None
                else:
                    print(f"  Subtitle cache: {Path(sub_path).name}")

        try:
            _r.render_video(
                video_path=str(vf),
                sub_path=sub_path,
                out_path=str(out_path),
                layout=layout,
                fps_num=fps_num,
                fps_den=fps_den,
                ffmpeg=ffmpeg,
                keyframe_interval_s=keyframe_interval,
                preserve_aspect=preserve_aspect,
            )
            rendered += 1
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr)
            failed += 1

    elapsed = time.time() - t_all
    print(f"\n{'='*60}")
    print(f"Done in {elapsed:.0f}s - "
          f"{rendered} rendered, {skipped} skipped, {failed} failed")

    files = sorted(output_dir.glob('*.ansi.gz'))
    if files:
        total_bytes = sum(f.stat().st_size for f in files)
        print(f"\nOutput ({output_dir}):")
        for f in files:
            print(f"  {f.name:50s}  {f.stat().st_size / 1_048_576:6.1f} MB")
        print(f"  {'TOTAL':50s}  {total_bytes / 1_048_576:6.1f} MB")

    print('='*60)
    if rendered > 0:
        print(f"\nRun 'python serve.py' to start the server.")


if __name__ == '__main__':
    main()
