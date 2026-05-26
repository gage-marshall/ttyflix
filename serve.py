#!/usr/bin/env python3
"""
serve.py — Start the ANSI Telnet + SSH server.

Reads all settings from config.toml. Run convert.py first to render
your videos before starting the server.

Usage:
  python serve.py
  python serve.py --port 2323      override telnet port (useful without root)
  python serve.py --no-web         disable the HTTP landing page
  python serve.py --no-ssh         disable the SSH server
"""

import argparse
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # pip install tomli  (Python < 3.11)
    except ImportError:
        sys.exit("ERROR: Python 3.11+ is required, or install tomli: pip install tomli")

from server.config import ServerConfig
from telnet_server import run_server

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
        description='Start the ANSI Telnet + SSH server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--port', type=int, default=None, metavar='N',
        help='Telnet port (overrides config.toml)',
    )
    parser.add_argument(
        '--web-port', type=int, default=None, metavar='N',
        help='HTTP landing page port (overrides config.toml; 0 = disable)',
    )
    parser.add_argument(
        '--no-web', action='store_true',
        help='Disable the HTTP landing page entirely',
    )
    parser.add_argument(
        '--ssh-port', type=int, default=None, metavar='N',
        help='SSH port (overrides config.toml; 0 = disable)',
    )
    parser.add_argument(
        '--no-ssh', action='store_true',
        help='Disable the SSH server',
    )
    parser.add_argument(
        '--config', default=str(CONFIG_FILE), metavar='PATH',
        help=f'Path to config file (default: {CONFIG_FILE})',
    )
    args = parser.parse_args()

    cfg        = _load_config(Path(args.config))
    srv_cfg    = cfg.get('server', {})
    layout_cfg = cfg.get('layout', {})
    conv_cfg   = cfg.get('convert', {})

    cols = layout_cfg.get('cols', 80)
    rows = layout_cfg.get('rows', 25)

    port = args.port if args.port is not None else srv_cfg.get('port', 23)

    if args.no_web:
        web_port = None
    elif args.web_port is not None:
        web_port = args.web_port or None
    else:
        raw = srv_cfg.get('web_port', 8080)
        web_port = raw if raw else None

    if args.no_ssh:
        ssh_port = None
    elif args.ssh_port is not None:
        ssh_port = args.ssh_port or None
    else:
        raw = srv_cfg.get('ssh_port', 2222)
        ssh_port = raw if raw else None

    config = ServerConfig(
        output_dir      = Path(conv_cfg.get('output_dir', 'output')),
        cols            = cols,
        rows            = rows,
        title           = srv_cfg.get('title', 'ANSI TELNET'),
        host            = srv_cfg.get('host', '0.0.0.0'),
        port            = port,
        web_port        = web_port,
        max_connections = srv_cfg.get('max_connections', 50),
        idle_timeout    = srv_cfg.get('idle_timeout', 300),
        ssh_port        = ssh_port,
        ssh_host_key    = srv_cfg.get('ssh_host_key', 'ssh_host_key'),
    )

    run_server(config)


if __name__ == '__main__':
    main()
