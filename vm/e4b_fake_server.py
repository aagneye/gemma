#!/usr/bin/env python3
"""Stand-in for an E4B vLLM server, for testing the E4B side track's plumbing without a GPU (vm/e4b_arms.sh).

  python3 e4b_fake_server.py <port> [<log file>]

GET  /v1/models            -> the E4B's model id
POST /v1/chat/completions  -> one short assistant text that names the port (no tool call), plain or streamed
Every request is appended to the log file as one JSON line: path, model, the thinking fields the harness sent
(chat_template_kwargs, thinking_token_budget), tool names and message count. An agent run against it ends without a
patch, which is enough to check that each arm reaches only its own port, that the internet is cut off, and what the
harness sends for a bundle's thinking budget.
"""
import json, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]); LOG = sys.argv[2] if len(sys.argv) > 2 else f"/tmp/e4b_fake_{PORT}.log"
MODEL = "gemma-4-e4b-it-qat-w4a16-ct"


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a): pass

    def send_json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            self.send_json({"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "fake"}]})
        else:
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); raw = self.rfile.read(n)
        try: req = json.loads(raw or b"{}")
        except ValueError: req = {}
        rec = {"t": round(time.time(), 1), "port": PORT, "path": self.path, "model": req.get("model"),
               "chat_template_kwargs": req.get("chat_template_kwargs"), "thinking_token_budget": req.get("thinking_token_budget"),
               "tools": [t.get("function", {}).get("name") for t in req.get("tools") or []], "messages": len(req.get("messages") or []),
               "stream": bool(req.get("stream"))}
        with open(LOG, "a") as f: f.write(json.dumps(rec) + "\n")
        text = f"Stand-in server on port {PORT}: no tool call."
        base = {"id": "chatcmpl-fake", "created": int(time.time()), "model": MODEL}
        if req.get("stream"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Connection", "close"); self.end_headers()
            chunks = [{**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}]},
                      {**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                       "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18}}]
            for c in chunks: self.wfile.write(b"data: " + json.dumps(c).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush(); self.close_connection = True
        else:
            self.send_json({**base, "object": "chat.completion",
                            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                            "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18}})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
