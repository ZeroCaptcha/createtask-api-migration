"""Both clients against a stand-in for both formats: no key, no real task, nothing spent."""

from __future__ import annotations

import unittest

from createtask_client import CaptchaApiError as CreateTaskError
from createtask_client import CreateTaskClient
from in_php_client import CaptchaApiError as InPhpError
from in_php_client import InPhpClient
from stand_in import BALANCE, KEY, TOKEN, StandIn

PAGE = "https://shop.example.com/login"
SITEKEY = "0x4AAAAAAAB1cD2eF3gH4iJ5"


class CreateTaskFormatTest(unittest.TestCase):
    def test_solves_with_the_same_calls(self) -> None:
        api = StandIn()
        try:
            client = CreateTaskClient(api.url, KEY, interval=0.01)
            self.assertEqual(client.solve_turnstile(PAGE, SITEKEY, action="login", cdata="session-7f3a9c2e"), TOKEN)
            create = api.requests[0]
            self.assertEqual(create["path"], "/createTask")
            self.assertEqual(
                create["body"],
                {
                    "clientKey": KEY,
                    "task": {
                        "type": "TurnstileTaskProxyless",
                        "websiteURL": PAGE,
                        "websiteKey": SITEKEY,
                        # The widget's action and cData reach the API.
                        "metadata": {"action": "login", "cdata": "session-7f3a9c2e"},
                    },
                },
            )
            self.assertTrue(create["idempotency_key"])
            self.assertEqual([r["path"] for r in api.requests], ["/createTask", "/getTaskResult", "/getTaskResult"])
        finally:
            api.close()

    def test_other_services_task_type_names_work(self) -> None:
        api = StandIn()
        try:
            client = CreateTaskClient(api.url, KEY, interval=0.01)
            token = client.solve_turnstile(PAGE, SITEKEY, task_type="AntiTurnstileTaskProxyLess")
            self.assertEqual(token, TOKEN)
            self.assertEqual(api.requests[0]["body"]["task"]["type"], "AntiTurnstileTaskProxyLess")
        finally:
            api.close()

    def test_reads_the_balance(self) -> None:
        api = StandIn()
        try:
            self.assertEqual(CreateTaskClient(api.url, KEY).get_balance(), float(BALANCE))
        finally:
            api.close()

    def test_a_failed_task_is_its_error_code(self) -> None:
        api = StandIn("failed")
        try:
            with self.assertRaises(CreateTaskError) as raised:
                CreateTaskClient(api.url, KEY, interval=0.01).solve_turnstile(PAGE, SITEKEY)
            self.assertEqual(raised.exception.code, "ERROR_CAPTCHA_UNSOLVABLE")
        finally:
            api.close()

    def test_slow_down_is_retried_with_the_same_idempotency_key(self) -> None:
        api = StandIn("slow-down")
        try:
            self.assertEqual(CreateTaskClient(api.url, KEY, interval=0.01).solve_turnstile(PAGE, SITEKEY), TOKEN)
            first, second = api.requests[0], api.requests[1]
            self.assertEqual((first["path"], second["path"]), ("/createTask", "/createTask"))
            self.assertEqual(first["idempotency_key"], second["idempotency_key"])
        finally:
            api.close()

    def test_a_wrong_key_is_refused(self) -> None:
        api = StandIn()
        try:
            with self.assertRaises(CreateTaskError) as raised:
                CreateTaskClient(api.url, "zc_live_wrong").get_balance()
            self.assertEqual(raised.exception.code, "ERROR_KEY_DOES_NOT_EXIST")
        finally:
            api.close()


class InPhpFormatTest(unittest.TestCase):
    def test_solves_with_the_same_calls(self) -> None:
        api = StandIn()
        try:
            client = InPhpClient(api.url, KEY, interval=0.01)
            self.assertEqual(client.solve_turnstile(SITEKEY, PAGE, action="login", data="session-7f3a9c2e"), TOKEN)
            submit = api.requests[0]
            self.assertEqual(submit["path"], "/in.php")
            self.assertEqual(
                submit["query"],
                {
                    "key": KEY,
                    "method": "turnstile",
                    "sitekey": SITEKEY,
                    "pageurl": PAGE,
                    "json": "1",
                    # The widget's action, and its cData as 2Captcha names it, reach the API.
                    "action": "login",
                    "data": "session-7f3a9c2e",
                },
            )
            polls = api.requests[1:]
            self.assertEqual([r["path"] for r in polls], ["/res.php", "/res.php"])
            self.assertEqual(polls[0]["query"]["action"], "get")
        finally:
            api.close()

    def test_reads_the_balance(self) -> None:
        api = StandIn()
        try:
            self.assertEqual(InPhpClient(api.url, KEY).get_balance(), float(BALANCE))
        finally:
            api.close()

    def test_a_failed_task_is_its_error_code(self) -> None:
        api = StandIn("failed")
        try:
            with self.assertRaises(InPhpError) as raised:
                InPhpClient(api.url, KEY, interval=0.01).solve_turnstile(SITEKEY, PAGE)
            self.assertEqual(raised.exception.code, "ERROR_CAPTCHA_UNSOLVABLE")
        finally:
            api.close()

    def test_slow_down_is_retried_with_the_same_idempotency_key(self) -> None:
        api = StandIn("slow-down")
        try:
            self.assertEqual(InPhpClient(api.url, KEY, interval=0.01).solve_turnstile(SITEKEY, PAGE), TOKEN)
            first, second = api.requests[0], api.requests[1]
            self.assertEqual((first["path"], second["path"]), ("/in.php", "/in.php"))
            self.assertEqual(first["idempotency_key"], second["idempotency_key"])
        finally:
            api.close()


if __name__ == "__main__":
    unittest.main()
