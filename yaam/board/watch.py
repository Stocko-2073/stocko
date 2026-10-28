"""Rebuild and preview the board on source changes: uv run watch.py."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
import time
from urllib.parse import urlsplit
import webbrowser


BOARD = Path(__file__).resolve().with_name("bench_board.py")
PDF = BOARD.with_suffix(".pdf")

VIEWER = b"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Bench board preview</title>
<style>
  html, body { height: 100%; margin: 0; background: #303030; color: white; }
  body { display: flex; flex-direction: column; font: 14px system-ui; }
  header { padding: 10px 16px; }
  iframe { flex: 1; width: 100%; border: 0; background: white; }
</style>
<header id="status" role="status">Waiting for a successful build...</header>
<iframe id="pdf" title="Bench board PDF" hidden></iframe>
<script>
  let version = 0;
  async function refresh() {
    const status = document.getElementById('status');
    try {
      const response = await fetch('/status', {cache: 'no-store'});
      if (!response.ok) throw new Error('Preview unavailable');
      const next = (await response.json()).version;
      if (next !== version) {
        const pdf = document.getElementById('pdf');
        pdf.src = '/bench_board.pdf?v=' + next + '#view=Fit';
        pdf.hidden = false;
        version = next;
      }
      status.textContent = version
        ? 'Bench board | Watching for saves | Last successful build shown'
        : 'Waiting for a successful build...';
    } catch {
      status.textContent = 'Watcher disconnected. Run uv run watch.py to restart.';
    } finally {
      setTimeout(refresh, 500);
    }
  }
  refresh();
</script>
</html>
"""


class PreviewServer(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), PreviewHandler)
        self.snapshot = (0, None)

    def publish(self, pdf):
        # Keep the last successful PDF available while the next build runs.
        self.snapshot = (self.snapshot[0] + 1, pdf)


class PreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        version, pdf = self.server.snapshot
        path = urlsplit(self.path).path
        if path == "/":
            content_type, body = "text/html; charset=utf-8", VIEWER
        elif path == "/status":
            content_type, body = "application/json", json.dumps({"version": version}).encode()
        elif path == "/bench_board.pdf" and pdf is not None:
            content_type, body = "application/pdf", pdf
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def source():
    try:
        return BOARD.read_bytes()
    except FileNotFoundError:
        # Editors may briefly remove the file while saving it.
        return None


def rebuild():
    print(f"Building {BOARD.name}...", flush=True)
    result = subprocess.run([sys.executable, str(BOARD), "--preview"], cwd=BOARD.parent)
    if result.returncode:
        print("Build failed; waiting for the next edit.", flush=True)
    else:
        print("Updated bench_board.pdf", flush=True)
        return PDF.read_bytes()


def main():
    with PreviewServer() as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            print(f"Watching {BOARD.name}. Press Ctrl+C to stop.", flush=True)
            previous = source()
            pdf = rebuild()
            if pdf is not None:
                server.publish(pdf)
            url = f"http://127.0.0.1:{server.server_port}/"
            print(f"PDF preview: {url}", flush=True)
            webbrowser.open(url)
            while True:
                time.sleep(0.5)
                current = source()
                if current is not None and current != previous:
                    previous = current
                    pdf = rebuild()
                    if pdf is not None:
                        server.publish(pdf)
        finally:
            server.shutdown()
            thread.join()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nWatcher stopped.")
