"""A Cloudflare Turnstile client in the createTask format (createTask, getTaskResult, getBalance),
the JSON format many CAPTCHA services share. Point it at ZeroCaptcha by changing the host and the
key; nothing else changes. Standard library only; Python 3.9 or later.

    client = CreateTaskClient(os.environ["ZEROCAPTCHA_API"], os.environ["ZEROCAPTCHA_KEY"])
    token = client.solve_turnstile("https://shop.example.com/login", "0x4AAAAAAAB1cD2eF3gH4iJ5")
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Optional

# The format's "try again later": wait for Retry-After, then send the same request again.
RETRYABLE = {"ERROR_RATE_LIMIT", "ERROR_NO_SLOT_AVAILABLE", "ERROR_SERVICE_UNAVAILABLE", "ERROR_IDEMPOTENCY_KEY_IN_USE"}
ATTEMPTS = 3


class CaptchaApiError(Exception):
    """A reply with errorId 1, a task that failed, or a wait that ran out."""

    def __init__(self, code: str, description: str) -> None:
        super().__init__(f"{code}: {description}")
        self.code = code


class CreateTaskClient:
    def __init__(self, api: str, client_key: str, interval: float = 2, timeout: float = 180) -> None:
        self.api = api.rstrip("/")  # before: https://api.<other service>; after: ZeroCaptcha's API
        self.client_key = client_key
        self.interval = interval
        self.timeout = timeout

    def solve_turnstile(
        self,
        website_url: str,
        website_key: str,
        action: Optional[str] = None,
        cdata: Optional[str] = None,
        task_type: str = "TurnstileTaskProxyless",
    ) -> str:
        """createTask, then getTaskResult every few seconds until the token is ready."""
        deadline = time.monotonic() + self.timeout
        task: Dict[str, Any] = {"type": task_type, "websiteURL": website_url, "websiteKey": website_key}
        # The widget's action and cData, nested in metadata as createTask clients send them, and only
        # when it sets them: many sites check both when they verify the token.
        metadata = {}
        if action:
            metadata["action"] = action
        if cdata:
            metadata["cdata"] = cdata
        if metadata:
            task["metadata"] = metadata
        # An Idempotency-Key makes a retried createTask return the first task, never a second.
        created = self._call("createTask", {"task": task}, deadline, str(uuid.uuid4()))
        task_id = created["taskId"]
        while True:
            if time.monotonic() + self.interval >= deadline:
                raise CaptchaApiError("timeout", f"Task {task_id} was not ready by the deadline.")
            time.sleep(self.interval)
            result = self._call("getTaskResult", {"taskId": task_id}, deadline)
            if result.get("status") == "ready":
                return result["solution"]["token"]

    def get_balance(self) -> float:
        """The available balance, in US dollars."""
        return float(self._call("getBalance", {}, time.monotonic() + 30)["balance"])

    def _call(self, method: str, body: Dict[str, Any], deadline: float, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        data = json.dumps({"clientKey": self.client_key, **body}).encode()
        for attempt in range(1, ATTEMPTS + 1):
            request = urllib.request.Request(f"{self.api}/{method}", data=data, headers=headers, method="POST")
            left = max(0.1, deadline - time.monotonic())
            try:
                with urllib.request.urlopen(request, timeout=min(30, left)) as response:
                    reply = json.loads(response.read())
                    asked = response.headers.get("Retry-After") or ""
            except urllib.error.HTTPError as error:
                # Only a failure outside the format answers with an HTTP error.
                reply = {"errorId": 1, "errorCode": f"HTTP_{error.code}", "errorDescription": error.reason}
                asked = error.headers.get("Retry-After") or ""
                if error.code in (429, 502, 503, 504):
                    reply["errorCode"] = "ERROR_SERVICE_UNAVAILABLE"
            if reply.get("errorId") == 0:
                return reply
            code = str(reply.get("errorCode"))
            if code not in RETRYABLE or attempt == ATTEMPTS:
                raise CaptchaApiError(code, str(reply.get("errorDescription")))
            wait = float(asked) if asked.strip().isdigit() else float(attempt)
            if time.monotonic() + wait >= deadline:
                raise CaptchaApiError(code, "Still refused at the deadline.")
            time.sleep(wait)
        raise AssertionError("unreachable")
