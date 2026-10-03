"""A stand-in on this machine for both formats ZeroCaptcha answers besides REST, so the tests need no
key and make no real task:

- createTask, getTaskResult and getBalance: POST, JSON, every reply HTTP 200, a failure is
  errorId 1 with errorCode and errorDescription;
- in.php and res.php with json=1: a success is status 1, a failure status 0 with the code in
  request and its meaning in error_text.

A task is processing (CAPCHA_NOT_READY) on its first poll and ready on the next. The scenario
"failed" makes every task fail with ERROR_CAPTCHA_UNSOLVABLE, and "slow-down" answers the first
create with the format's "slow down" and a Retry-After of 0.
"""

from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlsplit

KEY = "zc_live_test_key"
TOKEN = "0.stand-in-turnstile-token"
BALANCE = "12.3456"


class StandIn:
    def __init__(self, scenario: str = "success") -> None:
        self.scenario = scenario
        self.requests: List[Dict[str, Any]] = []
        self.tasks: Dict[str, int] = {}
        self.creates = 0
        stand_in = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802 - the name http.server calls
                stand_in.answer(self, None)

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                stand_in.answer(self, json.loads(self.rfile.read(length) or b"null"))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def answer(self, handler: BaseHTTPRequestHandler, body: Any) -> None:
        parts = urlsplit(handler.path)
        query = {name: values[0] for name, values in parse_qs(parts.query).items()}
        self.requests.append(
            {"path": parts.path, "query": query, "body": body, "idempotency_key": handler.headers.get("Idempotency-Key")}
        )
        reply, retry_after = self.reply(parts.path, query, body if isinstance(body, dict) else {})
        data = json.dumps(reply).encode()
        handler.send_response(200)  # every reply in these formats is HTTP 200
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        if retry_after:
            handler.send_header("Retry-After", "0")
        handler.end_headers()
        handler.wfile.write(data)

    def create(self) -> Any:
        """A new task's ID, or None when this create is answered "slow down"."""
        self.creates += 1
        if self.scenario == "slow-down" and self.creates == 1:
            return None
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = 0
        return task_id

    def poll(self, task_id: str) -> str:
        """"unknown", "processing", "failed" or "ready"."""
        if task_id not in self.tasks:
            return "unknown"
        self.tasks[task_id] += 1
        if self.scenario == "failed":
            return "failed"
        return "processing" if self.tasks[task_id] == 1 else "ready"

    def reply(self, path: str, query: Dict[str, str], body: Dict[str, Any]) -> Any:
        if path in ("/createTask", "/getTaskResult", "/getBalance"):
            if body.get("clientKey") != KEY:
                return {"errorId": 1, "errorCode": "ERROR_KEY_DOES_NOT_EXIST", "errorDescription": "No such key."}, False
            if path == "/getBalance":
                return {"errorId": 0, "balance": float(BALANCE)}, False
            if path == "/createTask":
                task = body.get("task") or {}
                if not task.get("websiteURL") or not task.get("websiteKey"):
                    return {"errorId": 1, "errorCode": "ERROR_TASK_ABSENT", "errorDescription": "No task."}, False
                task_id = self.create()
                if task_id is None:
                    return {"errorId": 1, "errorCode": "ERROR_RATE_LIMIT", "errorDescription": "Slow down."}, True
                return {"errorId": 0, "taskId": task_id}, False
            state = self.poll(str(body.get("taskId")))
            if state == "unknown":
                return {"errorId": 1, "errorCode": "ERROR_NO_SUCH_CAPCHA_ID", "errorDescription": "No such task."}, False
            if state == "failed":
                return {"errorId": 1, "errorCode": "ERROR_CAPTCHA_UNSOLVABLE", "errorDescription": "Not solved.", "status": "failed"}, False
            if state == "processing":
                return {"errorId": 0, "status": "processing"}, False
            return {"errorId": 0, "status": "ready", "solution": {"token": TOKEN, "type": "turnstile"}, "cost": "0.001000"}, False

        if path in ("/in.php", "/res.php"):
            if query.get("key") != KEY:
                return {"status": 0, "request": "ERROR_KEY_DOES_NOT_EXIST", "error_text": "No such key."}, False
            if path == "/in.php":
                if query.get("method") != "turnstile":
                    return {"status": 0, "request": "ERROR_BAD_PARAMETERS", "error_text": "method=turnstile only."}, False
                if not query.get("sitekey") or not query.get("pageurl"):
                    return {"status": 0, "request": "ERROR_PAGEURL", "error_text": "pageurl and sitekey."}, False
                task_id = self.create()
                if task_id is None:
                    return {"status": 0, "request": "MAX_USER_TURN", "error_text": "Slow down."}, True
                return {"status": 1, "request": task_id}, False
            if query.get("action") == "getbalance":
                return {"status": 1, "request": BALANCE}, False
            state = self.poll(query.get("id", ""))
            if state == "unknown":
                return {"status": 0, "request": "ERROR_WRONG_CAPTCHA_ID", "error_text": "No such task."}, False
            if state == "failed":
                return {"status": 0, "request": "ERROR_CAPTCHA_UNSOLVABLE", "error_text": "Not solved."}, False
            if state == "processing":
                return {"status": 0, "request": "CAPCHA_NOT_READY"}, False
            return {"status": 1, "request": TOKEN}, False
        return {"errorId": 1, "errorCode": "NOT_FOUND"}, False
