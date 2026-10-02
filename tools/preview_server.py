"""Development-only browser preview. Never reads/writes actual user schedules.

python -X utf8 tools/preview_server.py
Open http://127.0.0.1:8765/index.html?preview=1
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import mimetypes
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from schedule_domain import MAX_BYTES, validate_snapshot
from document_engine import document_model
from document_layout import build_plan

ALLOWED = {'index.html', 'app.js', 'style.css', 'document.css', 'schedule-core.js',
           '처음사용_5분안내.html',
           'assets/boeun-symbol.png', 'assets/boeun-slogan.png', 'assets/app_icon.ico'}
ORIGIN = 'http://127.0.0.1:8765'


class Handler(BaseHTTPRequestHandler):
    def send(self, status, content, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        name = unquote(urlsplit(self.path).path).lstrip('/') or 'index.html'
        if name not in ALLOWED:
            self.send(404, b'Not found', 'text/plain')
            return
        content = (ROOT / name).read_bytes()
        self.send(200, content, mimetypes.guess_type(name)[0] or 'application/octet-stream')

    def do_POST(self):
        if self.path != '/preview-document' or self.headers.get('Origin') != ORIGIN:
            self.send(403, b'Forbidden', 'text/plain')
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_BYTES or self.headers.get_content_type() != 'application/json':
                raise ValueError('미리보기 요청 크기 또는 형식이 올바르지 않습니다.')
            request = json.loads(self.rfile.read(size))
            snapshot = validate_snapshot(request['snapshot'])
            result = {'success': True, 'plan': build_plan(document_model(snapshot, request['request']))}
        except (ValueError, KeyError, TypeError) as error:
            result = {'success': False, 'message': str(error)}
        self.send(200, json.dumps(result, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')


if __name__ == '__main__':
    print(ORIGIN + '/index.html?preview=1', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
