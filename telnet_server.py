"""
telnet_server.py — ANSI art Telnet + SSH server

Streams pre-rendered .ansi.gz files from an output directory to Telnet and
SSH clients, with an auto-generated menu and terminal capability checks.

Usage:
  python telnet_server.py
  python telnet_server.py --title "MY SERVER" --output-dir /path/to/output
  python telnet_server.py --hd
  python telnet_server.py --cols 120 --rows 40
  python telnet_server.py --port 2323 --no-web
"""

import argparse
import logging
import socket
import sys
import threading
from pathlib import Path

from server.catalog import build_key_map, discover
from server.config import ServerConfig
from server.screens import build_menu
from server.session import handle_client
from server.telnet_conn import TelnetConnection


def run_server(config: ServerConfig) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(name)s  %(message)s',
        datefmt='%H:%M:%S',
    )
    log = logging.getLogger('server')

    # Build catalog and menu once at startup; all sessions share the same bytes
    entries    = discover(config.output_dir)
    key_map    = build_key_map(entries)
    menu_bytes = build_menu(entries, config)

    log.info(
        f'Catalog: {len(entries)} entries from {config.output_dir}  '
        f'layout: {config.cols}x{config.rows}'
    )
    if not entries:
        log.warning(
            'No .ansi.gz files found in %s — '
            'did you forget to run: python convert.py',
            config.output_dir,
        )

    if config.web_port is not None:
        try:
            import web_server
            telnet_host = config.host if config.host not in ('0.0.0.0', '') else 'your-server-hostname'
            port_suffix = f' {config.port}' if config.port != 23 else ''
            subs = {
                '{{TITLE}}':      config.title,
                '{{TELNET_CMD}}': f'telnet {telnet_host}{port_suffix}',
                '{{COLS}}':       str(config.cols),
                '{{ROWS}}':       str(config.rows),
            }
            web_server.start(config.host, config.web_port, subs)
            log.info(f'HTTP server on port {config.web_port}')
        except ImportError:
            log.warning('web_server.py not found; HTTP server disabled')

    sem = threading.Semaphore(config.max_connections)

    # Start SSH server as a daemon thread if configured
    if config.ssh_port:
        import ssh_server as _ssh
        host_key = _ssh.load_or_generate_host_key(Path(config.ssh_host_key))
        t = threading.Thread(
            target=_ssh.run_ssh_server,
            args=(config, menu_bytes, key_map, host_key, sem),
            daemon=True,
        )
        t.start()
        log.info(f'SSH server on port {config.ssh_port}')

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((config.host, config.port))
    except PermissionError:
        sys.exit(
            f"ERROR: Cannot bind to port {config.port} — permission denied.\n"
            f"       Ports below 1024 require root on Linux/macOS.\n"
            f"       Try:  python serve.py --port 2323"
        )
    except OSError as e:
        sys.exit(f"ERROR: Cannot bind to {config.host}:{config.port} — {e}")
    srv.listen(10)

    ready = sum(1 for e in entries if e.path.exists())
    log.info(f'Listening on {config.host}:{config.port}  ({ready}/{len(entries)} entries ready)')
    log.info(f'Connection cap: {config.max_connections}  idle timeout: {config.idle_timeout}s')

    def _run(sock: socket.socket, addr: tuple) -> None:
        try:
            conn = TelnetConnection(sock, addr)
            handle_client(conn, menu_bytes, key_map, config)
        except OSError:
            pass  # TelnetConnection.__init__ already closed sock on failure
        finally:
            sem.release()

    try:
        while True:
            sock, addr = srv.accept()
            if not sem.acquire(blocking=False):
                log.warning('Connection cap reached; rejecting %s:%s', addr[0], addr[1])
                try:
                    sock.sendall(b'\r\nServer is full. Please try again later.\r\n')
                except OSError:
                    pass
                sock.close()
                continue
            t = threading.Thread(target=_run, args=(sock, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        log.info('shutting down')
    finally:
        srv.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description='ANSI art Telnet + SSH server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument('--host', default='0.0.0.0',
                        help='Bind address (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=23,
                        help='Telnet port (default: 23)')
    parser.add_argument('--output-dir', default='output', metavar='DIR',
                        help='Directory containing .ansi.gz files (default: ./output)')
    parser.add_argument('--title', default='ANSI TELNET',
                        help='Server title shown in the menu banner')

    res = parser.add_mutually_exclusive_group()
    res.add_argument('--hd', action='store_true',
                     help='HD mode: expect a 160x50 terminal')
    res.add_argument('--cols', type=int, default=None, metavar='N',
                     help='Expected terminal columns (default: 80)')
    parser.add_argument('--rows', type=int, default=None, metavar='N',
                        help='Expected terminal rows (default: 25, or 50 with --hd)')

    web = parser.add_mutually_exclusive_group()
    web.add_argument('--web-port', type=int, default=8080, metavar='PORT',
                     help='HTTP landing page port (default: 8080)')
    web.add_argument('--no-web', action='store_true',
                     help='Disable the HTTP landing page entirely')

    parser.add_argument('--ssh-port', type=int, default=2222, metavar='PORT',
                        help='SSH port (default: 2222; 0 = disable)')
    parser.add_argument('--no-ssh', action='store_true',
                        help='Disable the SSH server')

    args = parser.parse_args()

    if args.hd:
        cols = args.cols or 160
        rows = args.rows or 50
    else:
        cols = args.cols or 80
        rows = args.rows or 25

    web_port = None if args.no_web else args.web_port
    ssh_port = None if args.no_ssh else (args.ssh_port or None)

    config = ServerConfig(
        output_dir=Path(args.output_dir),
        cols=cols,
        rows=rows,
        title=args.title,
        host=args.host,
        port=args.port,
        web_port=web_port,
        ssh_port=ssh_port,
    )

    run_server(config)


if __name__ == '__main__':
    main()
