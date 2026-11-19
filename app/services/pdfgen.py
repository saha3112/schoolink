"""One headless Chrome kept open to print many HTML documents to PDF (DevTools protocol)."""
import base64
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.request

import websocket


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class ChromePdf:
    def __init__(self, chrome_bin):
        if not os.path.exists(chrome_bin):
            raise RuntimeError("Google Chrome was not found (set CHROME_BIN).")
        self.dir = tempfile.mkdtemp(prefix="sl_chrome_")
        self.port = _free_port()
        self.proc = subprocess.Popen([chrome_bin, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                                      f"--remote-debugging-port={self.port}", f"--user-data-dir={self.dir}", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tabs = None
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json", timeout=2)); break
            except Exception:
                time.sleep(0.2)
        if not tabs:
            self.close(); raise RuntimeError("Chrome did not start.")
        page = [t for t in tabs if t["type"] == "page"][0]
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=120, max_size=None)
        self.n = 0
        self.call("Page.enable")

    def call(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == self.n:
                if "error" in r:
                    raise RuntimeError(r["error"].get("message", "Chrome error"))
                return r.get("result", {})

    def _wait_event(self, name, timeout):
        end = time.time() + timeout
        self.ws.settimeout(max(1, timeout))
        while time.time() < end:
            try:
                r = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                break
            if r.get("method") == name:
                return True
        return False

    def to_pdf(self, html):
        """html (str) -> pdf bytes. The page's own @page rule decides the paper size."""
        path = os.path.join(self.dir, "doc.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        self.call("Page.navigate", url="file://" + path)
        self._wait_event("Page.loadEventFired", 60)
        try:   # let web fonts finish
            self.call("Runtime.evaluate", expression="document.fonts && document.fonts.ready.then(()=>true)", awaitPromise=True, returnByValue=True)
        except Exception:
            pass
        self.ws.settimeout(120)
        r = self.call("Page.printToPDF", printBackground=True, preferCSSPageSize=True, displayHeaderFooter=False)
        return base64.b64decode(r["data"])

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        try:
            self.proc.terminate(); self.proc.wait(timeout=5)
        except Exception:
            try: self.proc.kill()
            except Exception: pass
