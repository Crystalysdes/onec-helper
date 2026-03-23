"""
Dev proxy: serves miniapp/dist on port 3000, proxies /api/v1 to FastAPI on port 8000.
Usage: python dev_proxy.py
"""
import http.server
import urllib.request
import urllib.error
import os
import sys
import mimetypes
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

STATIC_DIR = Path(__file__).parent / "miniapp" / "dist"
BACKEND_URL = "http://localhost:8000"
PORT = 3000


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[proxy] {self.path} -> {fmt % args}")

    def do_GET(self): self._dispatch()
    def do_POST(self): self._dispatch()
    def do_PUT(self): self._dispatch()
    def do_PATCH(self): self._dispatch()
    def do_DELETE(self): self._dispatch()
    def do_OPTIONS(self): self._dispatch()

    def _dispatch(self):
        if self.path.startswith("/api/"):
            self._proxy(self.command)
        else:
            self._serve_static()

    def _read_body(self):
        """Read body handling both Content-Length and chunked Transfer-Encoding."""
        te = self.headers.get("Transfer-Encoding", "").lower()
        if "chunked" in te:
            chunks = []
            while True:
                size_line = self.rfile.readline().strip()
                if not size_line:
                    break
                try:
                    chunk_size = int(size_line, 16)
                except ValueError:
                    break
                if chunk_size == 0:
                    break
                chunks.append(self.rfile.read(chunk_size))
                self.rfile.read(2)  # CRLF after chunk
            return b"".join(chunks) or None
        else:
            length = int(self.headers.get("Content-Length", 0) or 0)
            return self.rfile.read(length) if length > 0 else None

    def _proxy(self, method):
        url = BACKEND_URL + self.path
        body = self._read_body()

        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length", "transfer-encoding")}
        if body:
            headers["Content-Length"] = str(len(body))

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding",):
                        self.send_header(k, v)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for k, v in e.headers.items():
                if k.lower() not in ("transfer-encoding",):
                    self.send_header(k, v)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as ex:
            body = f'{{"detail": "Backend unavailable: {ex}"}}'.encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _serve_static(self):
        path = self.path.split("?")[0].lstrip("/") or "index.html"
        file_path = STATIC_DIR / path
        if not file_path.exists() or file_path.is_dir():
            file_path = STATIC_DIR / "index.html"
        try:
            content = file_path.read_bytes()
            mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as ex:
            self.send_response(500)
            self.end_headers()


if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    server = http.server.ThreadingHTTPServer(("", PORT), ProxyHandler)
    print(f"Dev proxy running on http://localhost:{PORT}")
    print(f"  Static: {str(STATIC_DIR).encode('ascii', errors='replace').decode()}")
    print(f"  API proxy -> {BACKEND_URL}")
    server.serve_forever()
