<!-- zc:header (generated from the registry; edit repos/registry.json) -->
# createTask and in.php API migration for Cloudflare Turnstile

[![CI](https://github.com/ZeroCaptcha/createtask-api-migration/actions/workflows/ci.yml/badge.svg)](https://github.com/ZeroCaptcha/createtask-api-migration/actions/workflows/ci.yml)

Move a Cloudflare Turnstile client written for the createTask/getTaskResult JSON format or the in.php/res.php format to ZeroCaptcha by changing the host and key. Tested Python clients for both formats, field-name tables and a checklist.

[Website](https://zerocaptcha.io/docs/migrate-createtask) · [Docs](https://zerocaptcha.io/docs) · [Quickstart](https://zerocaptcha.io/docs/quickstart) · [API reference](https://zerocaptcha.io/docs/reference/api) · [Pricing](https://zerocaptcha.io/pricing)
<!-- /zc:header -->

## What it does

Most CAPTCHA-solving services speak one of two formats: the JSON **createTask** format (`createTask`, `getTaskResult`, `getBalance`), used by CapSolver, Anti-Captcha and 2Captcha's newer API, and 2Captcha's **in.php and res.php** format. ZeroCaptcha answers both, for Cloudflare Turnstile, beside its own REST API. So a client you already have moves over by changing **the host and the key**.

This repository shows that with two small, tested clients, one per format, and lists what to check when you switch:

- **`createtask_client.py`**: createTask, then getTaskResult until `ready`; getBalance.
- **`in_php_client.py`**: `in.php?method=turnstile`, then `res.php?action=get` until the token; `action=getbalance`.

Both use the standard library only (Python 3.9 or later) and send an `Idempotency-Key`, so a retried create never makes a second task.

ZeroCaptcha is not affiliated with 2Captcha, CapSolver or Anti-Captcha. They are named only to show what to change.

## Quickstart

1. Create an account on the ZeroCaptcha website, create an API key on the dashboard and add funds (crypto, from $10). A task is charged only when it succeeds.
2. Change the host and the key, and nothing else:

   ```python
   import os

   from createtask_client import CreateTaskClient

   # Before: CreateTaskClient("https://api.capsolver.com", os.environ["CAPSOLVER_KEY"])
   client = CreateTaskClient(os.environ["ZEROCAPTCHA_API"], os.environ["ZEROCAPTCHA_KEY"])
   # The widget's data-action and data-cdata (or turnstile.render()'s action and cData options),
   # sent in the task's metadata: many sites check both when they verify the token.
   token = client.solve_turnstile(
       "https://shop.example.com/login", "0x4AAAAAAAB1cD2eF3gH4iJ5", action="login", cdata="session-7f3a9c2e"
   )
   ```

   ```python
   import os

   from in_php_client import InPhpClient

   # Before: InPhpClient("https://2captcha.com", os.environ["TWOCAPTCHA_KEY"])
   client = InPhpClient(os.environ["ZEROCAPTCHA_API"], os.environ["ZEROCAPTCHA_KEY"])
   # 2Captcha's action and data: the widget's data-action and data-cdata.
   token = client.solve_turnstile(
       "0x4AAAAAAAB1cD2eF3gH4iJ5", "https://shop.example.com/login", action="login", data="session-7f3a9c2e"
   )
   ```

The same goes for a client in any language: set its base URL to `https://api.zerocaptcha.io` (ZeroCaptcha's API address, from the docs) and its key to your `zc_live_…` key. A library that cannot change its host can be replaced by the few lines above.

## The createTask format

| What | Names ZeroCaptcha reads |
| --- | --- |
| Task type | `TurnstileTaskProxyless`, `TurnstileTask`, `CloudflareChallengeTask`, CapSolver's `AntiTurnstileTaskProxyLess` and `AntiCloudflareTask`, and `AntiTurnstileTask` for the proxy variant, in any case |
| The page | `websiteURL`, `websiteUrl` |
| The sitekey | `websiteKey` |
| The action | `action`, `pageAction`, `metadata.action` |
| The cData | `cdata`, `cData`, `data`, `turnstileCData`, `metadata.cdata` |
| A proxy | `proxy` as a URL, or `proxyType`, `proxyAddress`, `proxyPort`, `proxyLogin`, `proxyPassword` |
| A callback | `callbackUrl`, beside `task` |

Fields it does not use are ignored, so a field under another name is silently left out: check yours against the table.

Replies are HTTP 200 with `errorId`: `{"errorId": 0, "taskId": "…"}` for a new task; `{"errorId": 0, "taskId": "…", "status": "processing"}` while it runs; `status: "ready"` with `solution.token` and `cost` when solved; `errorId: 1` with `errorCode` (such as `ERROR_CAPTCHA_UNSOLVABLE`) when it failed, and nothing is charged. A challenge page's `ready` reply also has `solution.userAgent` and `solution.cookies.cf_clearance`. See the [createTask format docs](https://zerocaptcha.io/docs/createtask).

## The in.php and res.php format

`in.php` takes `key`, `method=turnstile`, `sitekey`, `pageurl`, and optionally `action`, `data` (the cData), `pingback`, `proxy` with `proxytype`, and `json=1`. It answers `OK|<task id>`, or `{"status": 1, "request": "<task id>"}` with `json=1`.

`res.php?action=get&id=<task id>` answers `CAPCHA_NOT_READY` while the task runs, then `OK|<token>` (or `{"status": 1, "request": "<token>"}`). `action=get2` adds the price; `action=getbalance` gives your balance in US dollars. See the [in.php and res.php docs](https://zerocaptcha.io/docs/2captcha).

## Check these when you switch

- **Task IDs.** in.php answers numbers, as 2Captcha does, such as `10000004821`, so a client that parses them as numbers works unchanged. The createTask format answers UUIDs: a client must keep those as text.
- **Only Cloudflare Turnstile and Cloudflare challenge pages.** In in.php, `method=turnstile` only; challenge pages need the createTask format or REST, whose replies can carry the user agent a clearance is bound to.
- **Proxies are `http` or `https`.** SOCKS is not supported. A challenge page always needs your proxy.
- **Slow down when asked.** `ERROR_RATE_LIMIT` (createTask) and `MAX_USER_TURN` or `ERROR: 1005` (in.php) come with a `Retry-After`; `ERROR_NO_SLOT_AVAILABLE` means your share of the queue is full for a moment. Wait, then send the same request with the same `Idempotency-Key`. Creating tasks has no rate limit; polling does.
- **Your balance does not move.** ZeroCaptcha is prepaid separately, in US dollars, and charges a task only when it is solved.
- **Roll it out one service at a time,** each with a key of its own and a daily [spend cap](https://zerocaptcha.io/docs/keys).

## FAQ

**Is there a REST API too?**
Yes, and the official SDKs use it: `POST /v1/tasks` with idempotency keys and RFC 9457 errors. See the [Cloudflare Turnstile solver](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver) and the [API reference](https://zerocaptcha.io/docs/reference/api).

**Can I use a callback instead of polling?**
Yes: `callbackUrl` in createTask, or `pingback` in in.php, with any public URL and no registration. Each call is signed; see [polling and callbacks](https://zerocaptcha.io/docs/callbacks).

**How do prices compare?**
The [pricing page](https://zerocaptcha.io/pricing) lists ZeroCaptcha's price per 1,000 solved tasks, and the [2Captcha alternative](https://zerocaptcha.io/compare/2captcha-alternative), [CapSolver alternative](https://zerocaptcha.io/compare/capsolver-alternative) and [Anti-Captcha alternative](https://zerocaptcha.io/compare/anti-captcha-alternative) pages compare them, with sources and dates.

**Where are the step-by-step guides?**
[Migrate a createTask client](https://zerocaptcha.io/docs/migrate-createtask) and [migrate a 2Captcha client](https://zerocaptcha.io/docs/migrate-2captcha), with samples in curl, Node, Python, Go and PHP.

## Run the tests

```sh
python -m unittest discover -s tests -v
```

The tests run both clients against a stand-in for both formats on your machine: no key, no real task, nothing spent.

<!-- zc:footer (generated from the registry) -->
## More from ZeroCaptcha

- The website: [ZeroCaptcha](https://zerocaptcha.io), the [docs](https://zerocaptcha.io/docs), the [guides](https://zerocaptcha.io/guides), the [blog](https://zerocaptcha.io/blog) and the [status page](https://zerocaptcha.io/status)
- Start here: [zerocaptcha](https://github.com/ZeroCaptcha/zerocaptcha), [cloudflare-turnstile-solver](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver), [cloudflare-challenge-solver](https://github.com/ZeroCaptcha/cloudflare-challenge-solver)
- Examples by language: [cloudflare-turnstile-solver-python](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-python), [cloudflare-turnstile-solver-nodejs](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-nodejs), [cloudflare-turnstile-solver-go](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-go), [cloudflare-turnstile-solver-php](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-php), [cloudflare-turnstile-solver-java](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-java), [cloudflare-turnstile-solver-csharp](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-csharp), [cloudflare-turnstile-solver-rust](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-rust)
- Browser automation: [cloudflare-turnstile-solver-playwright](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-playwright), [cloudflare-turnstile-solver-puppeteer](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-puppeteer), [cloudflare-turnstile-solver-selenium](https://github.com/ZeroCaptcha/cloudflare-turnstile-solver-selenium)
- SDKs, MCP server and migration: [zerocaptcha-js](https://github.com/ZeroCaptcha/zerocaptcha-js), [zerocaptcha-python](https://github.com/ZeroCaptcha/zerocaptcha-python), [zerocaptcha-go](https://github.com/ZeroCaptcha/zerocaptcha-go), [zerocaptcha-mcp](https://github.com/ZeroCaptcha/zerocaptcha-mcp), **createtask-api-migration**
- Lists: [awesome-cloudflare-turnstile](https://github.com/ZeroCaptcha/awesome-cloudflare-turnstile)

## Licence

MIT: see [LICENSE](LICENSE).

## Disclaimer

ZeroCaptcha is an independent service, not affiliated with or endorsed by Cloudflare. Cloudflare and Turnstile are trademarks of Cloudflare, Inc. Use ZeroCaptcha only on sites you own or are allowed to automate, as the [Acceptable Use Policy](https://zerocaptcha.io/legal/acceptable-use) says; any site owner can [opt out](https://zerocaptcha.io/opt-out).
<!-- /zc:footer -->
