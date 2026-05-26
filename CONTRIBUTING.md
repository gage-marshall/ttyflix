# Contributing to TTYFlix

Thanks for your interest! Contributions of all kinds are welcome — bug reports,
fixes, new features, documentation improvements, and alternative implementations
of the file format.

---

## Reporting bugs

Open an issue and include:

- Your OS and Python version (`python --version`)
- The command you ran and the full error output
- Your `config.toml` (redact any hostnames/IPs if you prefer)
- For render issues: the output of `python convert.py --list-streams yourfile.mkv`

---

## Development setup

```
git clone https://github.com/gage-marshall/TTYFlix
cd TTYFlix
pip install -r requirements.txt
```

ffmpeg is required. On Linux/macOS:
```
sudo apt install ffmpeg      # Debian/Ubuntu
brew install ffmpeg          # macOS
```

On Windows, `ffmpeg.exe` and `ffprobe.exe` are included in the repo.

---

## Areas where help is wanted

### Features
- **Seeking** — the `FLAG_KEYFRAME` bit is stored in every frame record but
  the server streams linearly from the start. Proper seeking requires a
  format change (v2 with per-keyframe gzip members and a seek table); see
  the architecture discussion in the README.
- **Playlist / shuffle mode** — automatically advance to the next catalog entry
  after playback ends, or play entries in random order.
- **Password-protected entries** — simple per-entry PIN in `config.toml`.
- **Live streaming** — instead of a pre-rendered file, pipe ffmpeg output
  directly through the renderer in real time.

### Alternative implementations
The `.ansi.gz` format is simple enough to implement in an afternoon. If you
build a player, renderer, or any compatible tool in another language, open an
issue or PR to get it linked here. See [FILEFORMAT.md](FILEFORMAT.md) for the
full spec.

---

## Pull request guidelines

- Keep PRs focused — one logical change per PR.
- If you're adding a feature, add a brief description to `README.md`.
- The `server/` package must remain importable without third-party dependencies
  (paramiko and Pillow belong at the root or CLI layer, not inside `server/`).
- Test with at least one real video file before submitting.

---

## Code style

- Standard Python — no formatter is enforced, but match the style of the file
  you're editing.
- No `type: ignore` comments — fix the type error instead.
- No comments explaining *what* the code does — only *why* when the reason is
  non-obvious.
