"""Local OpenAI-compatible chat-completions server backed by Claude Code.

    python gateway/server.py [--port 8787] [--bin gateway/chat_turn_bin]

POST /v1/chat/completions {model, messages, tools?} -> one model turn produced by
the authenticated Claude Code CLI through BAML's claude_code.ClaudeCodeClient
(see baml_src/main.baml). Tool calls are returned, never executed. Each request
spawns the packed BAML binary, which spawns `claude -p`; the server itself is a
thin, dependency-free thread-per-request host.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BIN = HERE / "chat_turn_bin"


def run_turn(binary: Path, req: dict, timeout_ms: int) -> dict:
    args = {"req_json": json.dumps(req), "model": req.get("model", "claude-opus-5-5"), "timeout_ms": timeout_ms}
    proc = subprocess.run([str(binary), "--json-args", "-"], input=json.dumps(args), capture_output=True, text=True, timeout=timeout_ms / 1000 + 30)
    if proc.returncode != 0:
        raise RuntimeError(f"baml exited {proc.returncode}: {proc.stderr.strip()[-2000:]}")
    # stdout is the function's JSON return value: a JSON *string* holding the response JSON
    last = [l for l in proc.stdout.splitlines() if l.strip()][-1]
    out = json.loads(last)
    if isinstance(out, str):
        out = json.loads(out)
    out["id"] = f"chatcmpl-cc-{uuid.uuid4().hex[:12]}"
    out["created"] = int(time.time())
    return out


class Handler(BaseHTTPRequestHandler):
    binary: Path = DEFAULT_BIN
    timeout_ms: int = 240_000

    def log_message(self, fmt, *args):  # quieter, one line per request
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/") == "/v1/models":
            return self._send(200, {"object": "list", "data": [{"id": "claude-opus-5-5", "object": "model"}]})
        if self.path.rstrip("/") == "/health":
            return self._send(200, {"ok": True})
        self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if self.path.rstrip("/") != "/v1/chat/completions":
            return self._send(404, {"error": {"message": "not found"}})
        n = int(self.headers.get("Content-Length", "0"))
        req = json.loads(self.rfile.read(n) or b"{}")
        if req.get("stream"):
            return self._send(400, {"error": {"message": "streaming not supported"}})
        t0 = time.perf_counter()
        try:
            resp = run_turn(self.binary, req, self.timeout_ms)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"turn failed: {e}\n")
            return self._send(500, {"error": {"message": str(e)[-2000:], "type": "server_error"}})
        fr = resp["choices"][0]["finish_reason"]
        sys.stderr.write(f"turn ok model={req.get('model')} finish={fr} msgs={len(req.get('messages', []))} {time.perf_counter() - t0:.1f}s\n")
        self._send(200, resp)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--bin", default=str(DEFAULT_BIN))
    p.add_argument("--timeout-ms", type=int, default=240_000)
    a = p.parse_args()
    Handler.binary = Path(a.bin)
    Handler.timeout_ms = a.timeout_ms
    if not Handler.binary.exists():
        sys.exit(f"missing {Handler.binary}; build it with: cd gateway && baml pack chat_turn -o chat_turn_bin")
    print(f"claude-code gateway on http://127.0.0.1:{a.port}/v1 using {Handler.binary}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
