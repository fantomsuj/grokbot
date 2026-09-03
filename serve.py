#!/usr/bin/env python3
"""Live-reload static server.

Serves the current directory and auto-refreshes the browser when any
served file changes. No dependencies beyond the Python standard library.

Usage:
    python3 serve.py [port]        # default port 8000
"""
import os
import sys
import time
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
ROOT = os.getcwd()

RELOAD_SNIPPET = b"""
<script>
(async function () {
  try {
    const res = await fetch('/__reload/ping');
    if (!res.ok) return;
    const es = new EventSource('/__reload/stream');
    es.onmessage = () => location.reload();
  } catch (e) {}
})();
</script>
"""


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/__reload/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            reload_event.wait()
            self.wfile.write(b"data: reload\n\n")
            return
        super().do_GET()


def watch():
    """Poll mtimes of all files below ROOT; bump the version on change."""
    last = snapshot()
    while True:
        time.sleep(1)
        now = snapshot()
        if now != last:
            last = now
            trigger_reload()


def snapshot():
    state = {}
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        if any(p in dirpath for p in (".git", "__pycache__", "node_modules")):
            continue
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
                state[path] = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
    return state


reload_event = threading.Event()


def trigger_reload():
    # Wake all SSE clients connected to the stream endpoint.
    with reload_lock:
        reload_event.set()


if __name__ == "__main__":
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    print(f"Serving http://localhost:{PORT}  (live reload enabled)")
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
