"""Local server for the Mike's Way site:  python serve.py   ->  http://localhost:8765

Serves this folder, plus the game videos from C:/Users/billi/Videos under /videos/ (mp4 only),
with byte-range support so the Film Room can jump around inside a video.
"""
import os, re, sys, urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
VIDEOS = os.environ.get("MW_VIDEOS") or os.path.join(os.path.expanduser("~"), "Videos")
# On the new PC the finished videos sit flat in E:\MikesWay\Full Game Videos (next to this site folder).
FLAT = os.path.join(os.path.dirname(ROOT), "Full Game Videos")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def translate_path(self, path):
        p = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        if p.startswith("/videos/"):
            full = os.path.realpath(os.path.join(VIDEOS, p[len("/videos/"):]))
            if full.startswith(os.path.realpath(VIDEOS)) and full.lower().endswith((".mp4", ".mov")):
                if os.path.isfile(full):
                    return full
                flat = os.path.join(FLAT, os.path.basename(full))
                if os.path.isfile(flat):
                    return flat
                return full
            return os.path.join(ROOT, "__nope__")
        return super().translate_path(path)

    def guess_type(self, path):
        # iPhone .MOV clips are H.264; Chrome plays them when labeled as mp4
        return "video/mp4" if str(path).lower().endswith((".mov", ".mp4")) else super().guess_type(path)

    def send_head(self):
        path = self.translate_path(self.path)
        rng = self.headers.get("Range")
        if not rng or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if not m:
            return super().send_head()
        a = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2)))
        b = int(m.group(2)) if m.group(1) and m.group(2) else size - 1
        b = min(b, size - 1)
        if a > b:
            self.send_error(416); return None
        f = open(path, "rb"); f.seek(a)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.send_header("Content-Length", str(b - a + 1))
        self.end_headers()
        self._left = b - a + 1
        return f

    def copyfile(self, src, dst):
        left = getattr(self, "_left", None)
        if left is None:
            return super().copyfile(src, dst)
        try:
            while left > 0:
                chunk = src.read(min(1 << 20, left))
                if not chunk:
                    break
                dst.write(chunk); left -= len(chunk)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    def end_headers(self):
        if not self.headers.get("Range"):
            self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"Mike's Way site: http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
