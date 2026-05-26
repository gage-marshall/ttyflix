"""
web_server.py — Static HTTP server for the telnet landing page.

Serves files from the www/ directory adjacent to this script.
Drop an index.html (and any CSS/JS/images) into www/ and they will
be served automatically.

start() is called by telnet_server.py after catalog discovery.
"""

import functools
import http.server
import logging
import threading
from pathlib import Path

log = logging.getLogger('web')

_WWW = Path(__file__).parent / 'www'


def start(
    host: str = '0.0.0.0',
    port: int = 8080,
    substitutions: dict[str, str] | None = None,
) -> threading.Thread | None:
    if not _WWW.is_dir():
        log.warning(f'www/ not found at {_WWW}; HTTP server disabled')
        return None

    subs = substitutions or {}

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path in ('/', '/index.html') and subs:
                index_path = Path(self.directory) / 'index.html'
                if index_path.exists():
                    content = index_path.read_text(encoding='utf-8')
                    for key, val in subs.items():
                        content = content.replace(key, val)
                    body = content.encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
            super().do_GET()

        def log_message(self, fmt, *args):
            log.debug('%s - %s', self.address_string(), fmt % args)

    handler = functools.partial(_Handler, directory=str(_WWW))
    server = http.server.HTTPServer((host, port), handler)
    t = threading.Thread(target=server.serve_forever, name='http', daemon=True)
    t.start()
    log.info(f'HTTP on {host}:{port}  root={_WWW}')
    return t
