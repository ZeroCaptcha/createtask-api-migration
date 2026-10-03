"""A Cloudflare Turnstile client in the in.php and res.php format (method=turnstile, json=1), the
format 2Captcha documents. Point it at ZeroCaptcha by changing the host and the key; nothing else
changes. Standard library only; Python 3.9 or later.

    client = InPhpClient(os.environ["ZEROCAPTCHA_API"], os.environ["ZEROCAPTCHA_KEY"])
    token = client.solve_turnstile("0x4AAAAAAAB1cD2eF3gH4iJ5", "https://shop.example.com/login")
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, Optional

NOT_READY = "CAPCHA_NOT_READY"
# The format's "slow down": in.php's and res.php's, and a queue that is full for a moment.
RETRYABLE = {"MAX_USER_TURN", "ERROR: 1005", "ERROR_NO_SLOT_AVAILABLE"}
ATTEMPTS = 3


class CaptchaApiError(Exception):
    """A reply with status 0 other than CAPCHA_NOT_READY, or a wait that ran out."""

    def __init__(self, code: str, description: str = "") -> None:
        super().__init__(f"{code}: {description}" if description else code)
        self.code = code


class InPhpClient:
    def __init__(self, api: str, key: str, interval: float = 5, timeout: float = 180) -> None:
        self.api = api.rstrip("/")  # before: https://2captcha.com; after: ZeroCaptcha's API
        self.key = key
        self.interval = interval
        self.timeout = timeout

    def solve_turnstile(
        self, sitekey: str, pageurl: str, action: Optional[str] = None, data: Optional[str] = None
    ) -> str:
        """in.php, then res.php?action=get every few seconds until the token is ready."""
        deadline = time.monotonic() + self.timeout
        params = {"key": self.key, "method": "turnstile", "sitekey": sitekey, "pageurl": pageurl, "json": "1"}
        if action:
            params["action"] = action
        if data:
            params["data"] = data  # the widget's cData
        # An Idempotency-Key makes a retried in.php return the first task, never a second.
        task_id = self._call("in.php", params, deadline, str(uuid.uuid4()))
        while True:
            if time.monotonic() + self.interval >= deadline:
                raise CaptchaApiError("timeout", f"Task {task_id} was not ready by the deadline.")
            time.sleep(self.interval)
            try:
                return self._call("res.php", {"key": self.key, "action": "get", "id": task_id, "json": "1"}, deadline)
            except CaptchaApiError as error:
                if error.code != NOT_READY:
                    raise

    def get_balance(self) -> float:
        """The available balance, in US dollars."""
        return float(self._call("res.php", {"key": self.key, "action": "getbalance", "json": "1"}, time.monotonic() + 30))

    def _call(self, script: str, params: Dict[str, str], deadline: float, idempotency_key: Optional[str] = None) -> str:
        headers = {} if idempotency_key is None else {"Idempotency-Key": idempotency_key}
        url = f"{self.api}/{script}?{urllib.parse.urlencode(params)}"
        for attempt in range(1, ATTEMPTS + 1):
            left = max(0.1, deadline - time.monotonic())
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=min(30, left)) as response:
                reply: Dict[str, Any] = json.loads(response.read())
                asked = response.headers.get("Retry-After") or ""
            if reply.get("status") == 1:
                return str(reply["request"])
            code = str(reply.get("request"))
            if code not in RETRYABLE or attempt == ATTEMPTS:
                raise CaptchaApiError(code, str(reply.get("error_text") or ""))
            wait = float(asked) if asked.strip().isdigit() else float(attempt)
            if time.monotonic() + wait >= deadline:
                raise CaptchaApiError(code, "Still refused at the deadline.")
            time.sleep(wait)
        raise AssertionError("unreachable")
