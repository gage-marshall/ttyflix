# TTYFlix

**Stream any video as ANSI art over Telnet and SSH.** Pre-render your videos into a
compact binary format, then serve them at the original framerate to anyone with
a terminal — no browser, no plugins, no account required.

![TTYFlix demo](demo.gif)

**Try it now** — open a terminal and run:

```
telnet nisemonogatari.com
```

> **See it in the wild:** check out [Nisemonogatari Telnet](https://github.com/gage-marshall/Nisemonogatari-Telnet)
> for a working deployment built on this protocol — anime streamed over raw Telnet, because why not.

---

## How it works

### The short version

Videos are converted to ANSI escape sequences ahead of time and stored in a
compressed `.ansi.gz` file. The server decompresses and streams these bytes to
telnet clients frame by frame, sleeping between frames to match the original
framerate. The heavy work is front-loaded at render time, so the server itself
is lightweight enough to run on a Raspberry Pi.

### The pixel trick

Each terminal cell displays one Unicode half-block character (`▀`, U+2580) with
an independent foreground and background colour. Because `▀` fills the top half
of the cell and the background colour fills the bottom half, one character cell
encodes **two pixels** stacked vertically. At 80×25 characters you get an
effective pixel grid of 80×44 (the bottom row is reserved for subtitles). At
160×50 you get 160×94 — genuine HD detail in a terminal.

Colours are mapped to the **xterm-256 palette** (the 216-colour cube, indices
16–231), which every modern terminal supports. Each cell is encoded as:

```
ESC[38;5;{fg};48;5;{bg}m▀
```

Consecutive cells with the same colours share one escape sequence, so
monochrome or low-detail regions compress extremely well.

### The file format

Each video is stored as a gzip-compressed binary stream (`.ansi.gz`). The
format is intentionally simple — see [FILEFORMAT.md](FILEFORMAT.md) for the
full spec. The key ideas:

- A **16-byte header** stores the framerate as a rational number
  (`fps_num / fps_den`) so NTSC rates like 29.97 and 23.976 are represented
  exactly, plus the terminal dimensions (`cols` × `rows`) the file was
  rendered for.
- Each **frame record** is a 12-byte header followed by raw ANSI bytes ready
  to be written directly to the socket.
- **Keyframes** (every 5 seconds by default) contain a full repaint of the
  screen. **Delta frames** contain only the cells that changed from the
  previous frame. A typical delta frame for talking-head content is a few
  hundred bytes; a keyframe is 10–30 KB.
- The server never re-encodes or reprocesses frames — it decompresses and
  forwards raw bytes. Serving is essentially `gzip decompress → socket.sendall`.

### Telnet and terminal negotiation

On connect the server sends a standard telnet negotiation requesting the
client's terminal size via **NAWS** (Negotiate About Window Size, RFC 1073).
If the client responds, the server compares the reported dimensions against the
configured minimum and warns the viewer before playback begins. Input handling
is a minimal subset of the telnet protocol — the server strips IAC command
sequences and looks for printable ASCII keystrokes.

---

## Quick start (local / bare-metal)

### 1. Prerequisites

- **Python 3.11 or later** — [python.org/downloads](https://www.python.org/downloads/)
- **ffmpeg** — Windows users: already included (`ffmpeg.exe`).
  Linux/macOS users: install via your package manager:
  ```
  # Ubuntu / Debian
  sudo apt install ffmpeg
  
  # macOS (Homebrew)
  brew install ffmpeg
  ```
- **Pillow** (Python image library):
  ```
  pip install -r requirements.txt
  ```

### 2. Add your videos

Create a `videos/` folder and drop your video files in:

```
videos/
  Episode 01.mkv
  Episode 02.mkv
  Short Film.mp4
```

The **file name** (without the extension) becomes the title shown in the
telnet menu, so name your files descriptively.

Supported formats: `.mkv .mp4 .avi .mov .m4v .webm .flv .wmv .ts .m2ts .mpg .mpeg`

### 3. Edit `config.toml`

Open `config.toml` in any text editor. At minimum, set your server title:

```toml
[server]
title = "MY ANSI SERVER"
```

See the comments in `config.toml` for all available options.

**Important:** The `[layout]` section sets the terminal size your viewers need.
The default `80 × 25` works in every terminal. Change it to `160 × 50` for HD
quality — but your viewers will need a large terminal.

### 4. Render your videos

```
python convert.py
```

This reads your `config.toml` settings and converts everything in `videos/`.
Rendering is slow — a 24-minute episode takes approximately 24 minutes to
render. This is normal; the process will print progress as it goes.

Output files go to `output/` — do not move or rename them.

To re-render a file:
```
python convert.py --force "Episode 01.mkv"
```

### 5. Customise the landing page

The page title, telnet command, and terminal size are automatically populated
from your `config.toml` settings when the server starts — no manual HTML
editing required for those.

The one section that needs your attention: open `www/index.html` and update
the **About** paragraph (and optionally the subtitle line under the banner)
to describe what your server streams.

The page is plain HTML with CSS variables for theming — no build step needed.

### 6. Start the server

```
python serve.py
```

- **SSH server: port 2222** — pre-installed on macOS, Linux, and Windows 10/11
- Telnet server: port **23** (requires root on Linux/macOS — see note below)
- Web landing page: port **8080** — open `http://localhost:8080` to preview it

Connect from another terminal:

**SSH (recommended):**
```
ssh anything@localhost -p 2222
```

**Telnet:**
```
telnet localhost
```

#### Running without root (Linux/macOS)

Port 23 requires root. Either run with `sudo`, or change the port in
`config.toml` and tell your viewers:

```toml
[server]
port = 2323
```

```
telnet your-server-hostname 2323
```

The SSH server always uses an unprivileged port (2222 by default) so it works
without root regardless.

---

## Quick start (Docker)

Docker handles ffmpeg, Python, and all dependencies automatically. A pre-built
image is published to GHCR — replace `build: .` with
`image: ghcr.io/gage-marshall/ttyflix:latest` in `docker-compose.yml`
to skip the local build.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose on Linux)

### Steps

**1. Add videos** to `videos/` (same as above).

**2. Edit `config.toml`** (same as above).

**3. Render your videos** inside Docker:

```
docker compose run --rm ttyflix python convert.py
```

This renders your videos using the same environment the server runs in.
Output goes to your local `output/` folder.

**4. Customise `www/index.html`** (same as above).

**5. (Optional) Persist the SSH host key** to prevent "host key changed"
warnings after server updates. Skip this if you don't care about SSH continuity.

```
touch ssh_host_key
```

Then open `docker-compose.yml` and uncomment the `ssh_host_key` volume line.

**6. Start the server:**

```
docker compose up -d
```

The server runs in the background. To see logs:
```
docker compose logs -f
```

To stop:
```
docker compose down
```

**7. Connect:**

**SSH (recommended):**
```
ssh anything@localhost -p 2222
```

**Telnet:**
```
telnet localhost
```

Web page: `http://localhost:8080`

---

## Deployment platform compatibility

This server requires **persistent raw TCP connections** on an arbitrary port
(default: 23). Most general-purpose cloud platforms are built around HTTP only
and will not work. Here is a quick guide:

| Platform | Telnet server | Web landing page | Notes |
|---|---|---|---|
| Raspberry Pi / bare metal | ✅ | ✅ | Ideal — full control over ports |
| VPS (Linode, DigitalOcean, Hetzner, etc.) | ✅ | ✅ | Works great with or without Docker |
| [Fly.io](https://fly.io) | ✅ | ✅ | Supports raw TCP — use `[[services]]` with `protocol = "tcp"` in `fly.toml` |
| Render | ⚠️ | ✅ | TCP is supported on some paid plans; standard web services are HTTP only |
| Railway | ❌ | ✅ | HTTP routing only; raw TCP not exposed to the public internet |
| Vercel | ❌ | ❌ | Serverless functions only — no persistent connections of any kind |
| Heroku | ❌ | ✅ | No raw TCP on standard dynos |

**Bottom line:** a Raspberry Pi on a home connection, any VPS, or Fly.io are
the recommended options. If port 23 is blocked by your ISP or hosting provider,
set `port` to any open port above 1024 in `config.toml`.

---

## Directory structure

```
TTYFlix/
├── config.toml          ← EDIT THIS — your server settings
├── www/
│   └── index.html       ← EDIT THIS — your web landing page
├── videos/              ← DROP YOUR VIDEOS HERE
│   └── ...
├── output/              ← auto-generated — do not edit
│   └── *.ansi.gz
│
├── convert.py           — render videos → output/
├── serve.py             — start the telnet + SSH + web server
├── Dockerfile           — Docker build file
├── docker-compose.yml   — Docker Compose config
│
├── ansi_render.py       — render engine (no need to edit)
├── telnet_server.py     — server core (no need to edit)
├── web_server.py        — static HTTP server (no need to edit)
└── server/              — server modules (no need to edit)
```

---

## Configuration reference

All settings live in `config.toml`. Here is a summary:

| Section      | Key                  | Default        | Description                                  |
|--------------|----------------------|----------------|----------------------------------------------|
| `[server]`   | `title`              | `ANSI TELNET`  | Title shown in the telnet menu               |
| `[server]`   | `host`               | `0.0.0.0`      | Bind address                                 |
| `[server]`   | `port`               | `23`           | Telnet port                                  |
| `[server]`   | `web_port`           | `8080`         | HTTP port (0 = disabled)                     |
| `[server]`   | `max_connections`    | `50`           | Maximum simultaneous telnet connections      |
| `[server]`   | `idle_timeout`       | `300`          | Seconds of inactivity before disconnect      |
| `[server]`   | `ssh_port`           | `2222`         | SSH port (0 = disabled)                      |
| `[server]`   | `ssh_host_key`       | `"ssh_host_key"` | SSH host key file path (auto-generated)    |
| `[layout]`   | `cols`               | `80`           | Terminal columns viewers need                |
| `[layout]`   | `rows`               | `25`           | Terminal rows viewers need                   |
| `[convert]`  | `input_dir`          | `videos`       | Folder containing source video files         |
| `[convert]`  | `output_dir`         | `output`       | Folder for rendered `.ansi.gz` files         |
| `[convert]`  | `force`              | `false`        | Re-render even if output exists              |
| `[convert]`  | `preserve_aspect`    | `true`         | Letterbox to preserve aspect ratio           |
| `[convert]`  | `keyframe_interval`  | `5.0`          | Full-redraw interval in seconds              |
| `[subtitles]`| `enabled`            | `true`         | Render embedded subtitles                    |
| `[subtitles]`| `language`           | `""`           | Preferred subtitle language code             |
| `[subtitles]`| `cache_dir`          | `subs`         | Folder for extracted subtitle cache          |

---

## Viewer requirements

Tell your viewers they need:

- A terminal with **ANSI / VT100** escape sequence support
- **UTF-8** character encoding
- Terminal size: at least **80 × 25** (or whatever you set in `[layout]`)

**SSH is the recommended way to connect** — it is pre-installed on macOS, Linux,
and Windows 10/11, and requires no extra configuration:

```
ssh anything@your-server-hostname -p 2222
```

**Telnet** also works for viewers who prefer it:

- **macOS:** `telnet` was removed in macOS High Sierra — install with `brew install inetutils`
- **Windows:** the built-in Telnet client defaults to CP437 and is not supported — use [PuTTY](https://putty.org) or WSL instead

---

## Troubleshooting

**"No .ansi.gz files found"** — Run `python convert.py` before starting the server.

**"Permission denied" on port 23** — Either run with `sudo python serve.py`,
or change `port` to a number above 1024 in `config.toml`.

**Video looks squished** — Set `preserve_aspect = true` in `config.toml` and re-render.

**Subtitles not showing** — Check that `enabled = true` in `[subtitles]`. Run
`python convert.py --list-streams "your-video.mkv"` to see available tracks,
then set `language` to the correct code (e.g. `"eng"`).

**Web page not loading** — Check that `web_port` in `config.toml` is not 0,
and that nothing else is using that port. You can change it to any free port.

**"telnet: command not found" (macOS)** — `telnet` was removed in macOS 10.13.
Install it: `brew install inetutils`

**"WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED" (SSH)** — The server
regenerated its host key, which happens whenever the Docker container is
recreated. To prevent this, follow the SSH host key persistence step in the
Docker quick start above.

**ffmpeg not found (Linux/macOS)** — Install ffmpeg:
`sudo apt install ffmpeg` or `brew install ffmpeg`.

**Display is garbled** — The viewer's terminal is probably too small. Tell them
to resize to at least the dimensions shown in `[layout]`, or enable the zoom
feature in their terminal emulator.
