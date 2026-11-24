"""In-page WorldWard host for Pyodide.

Runs the unchanged App request handler and Engine in-process. The App's
network server is replaced by an in-memory stand-in, and each interface
request is dispatched straight to the real handler. Saves live in /saves and
assistance records in /private; the page mirrors both to claude.ai storage.
"""
import email.message
import hashlib
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path('/worldward')
SAVES = Path('/saves')
PRIVATE = Path('/private')
PORT = 8765
sys.path.insert(0, str(ROOT / 'IRGS_Web'))

import server as host  # noqa: E402  (path set above)


class _InPageServer:
    """Stands in for ThreadingHTTPServer: no socket, no thread."""
    def __init__(self, address, handler):
        self.server_address = ('127.0.0.1', PORT)
        self.server_port = PORT
        self.RequestHandlerClass = handler

    def server_close(self):
        pass


host.ThreadingHTTPServer = _InPageServer
_server = None


def start(solo_configuration=None):
    global _server
    SAVES.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    _server = host.make_server(PORT, SAVES, reference_config=Path('/tmp/no-reference-config.json'),
                               reference_cache=Path('/tmp/reference-cache'),
                               solo_configuration=solo_configuration)
    return True


def _bytes(value):
    """Accept None, JavaScript null/undefined, a Uint8Array proxy or bytes."""
    if value is None or type(value).__name__ in ('JsNull', 'JsUndefined'):
        return b''
    if hasattr(value, 'to_bytes'):
        return value.to_bytes()
    return bytes(value)


def dispatch(method, path, headers_json, body):
    """Run one request through the real handler; return (status, type, bytes)."""
    if method not in ('GET', 'POST'):
        return 405, 'application/json', b'{"error": "Unsupported request"}'
    handler_class = _server.RequestHandlerClass
    handler = handler_class.__new__(handler_class)
    handler.server = _server
    handler.client_address = ('127.0.0.1', 0)
    handler.command = method
    handler.path = path
    handler.request_version = 'HTTP/1.1'
    handler.requestline = f'{method} {path} HTTP/1.1'
    handler.close_connection = True
    headers = email.message.Message()
    for name, value in json.loads(headers_json or '{}').items():
        if name.lower() not in ('host', 'origin', 'content-length'):
            headers[name] = value
    headers['Host'] = f'127.0.0.1:{PORT}'
    data = _bytes(body)
    if data:
        headers['Content-Length'] = str(len(data))
    handler.headers = headers
    handler.rfile = io.BytesIO(data)
    handler.wfile = io.BytesIO()
    handler.log_message = lambda *args: None
    getattr(handler, 'do_' + method)()
    raw = handler.wfile.getvalue()
    head, _, payload = raw.partition(b'\r\n\r\n')
    lines = head.decode('latin-1').split('\r\n')
    status = int(lines[0].split()[1])
    content_type = next((line.split(':', 1)[1].strip() for line in lines[1:]
                         if line.lower().startswith('content-type:')), 'application/octet-stream')
    return status, content_type, payload


def snapshot():
    """Current saved files as {path: sha256}, for mirroring changes."""
    result = {}
    for base in (SAVES, PRIVATE):
        for path in sorted(base.rglob('*')):
            if path.is_file() and path.suffix not in ('.tmp',) and not path.name.endswith('-journal'):
                result[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.dumps(result)


def restore(path, data):
    """Write one mirrored file back before the host starts."""
    target = Path(path)
    if not (target.is_relative_to(SAVES) or target.is_relative_to(PRIVATE)) or '..' in target.parts:
        raise ValueError('Refusing a file outside the save folders')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_bytes(data))


def verify_bundle():
    """Check every bundled source file against the build's manifest."""
    manifest = json.loads((ROOT / 'BUNDLE_MANIFEST.json').read_text())
    for relative, expected in manifest.items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError('Bundled file changed: ' + relative)
    return len(manifest)
