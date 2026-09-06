import base64
import os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

USER = os.environ.get('TEST_USER', 'bursa')
PASSWORD = os.environ.get('TEST_PASS', '')
PORT = int(os.environ.get('PORT', '10000'))
WEB_ROOT = Path(__file__).parent / 'web'

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def do_GET(self):
        if not PASSWORD:
            self.send_error(500, 'TEST_PASS is not configured')
            return
        expected = 'Basic ' + base64.b64encode(f'{USER}:{PASSWORD}'.encode()).decode()
        if self.headers.get('Authorization') != expected:
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="Turkey Pulse Bursa Test"')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return
        if self.path == '/':
            self.path = '/bursa-test.html'
        super().do_GET()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Robots-Tag', 'noindex, nofollow, noarchive')
        super().end_headers()

if __name__ == '__main__':
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print(f'Serving protected Bursa TEST_ONLY preview on port {PORT}')
    server.serve_forever()
