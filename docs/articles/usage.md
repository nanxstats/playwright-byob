# Usage

playwright-byob keeps the normal Playwright lifecycle.
You still create a Playwright object and receive a `BrowserContext`.
The package only resolves the Chrome executable, profile directory,
and launch options.

## Sync API

```python
from playwright.sync_api import sync_playwright
from playwright_byob import launch_chrome

with sync_playwright() as p:
    context = launch_chrome(p)
    page = context.new_page()
    page.goto("https://example.com")
    context.close()
```

## Async API

```python
from playwright.async_api import async_playwright
from playwright_byob import async_launch_chrome

async with async_playwright() as p:
    context = await async_launch_chrome(p)
    page = await context.new_page()
    await page.goto("https://example.com")
    await context.close()
```

## Defaults

`launch_chrome()` and `async_launch_chrome()` default to:

- Detecting Google Chrome from common platform locations.
- Using a dedicated `playwright-byob` Chrome user data directory under the
  platform app data directory.
- Selecting the `Default` Chrome profile folder inside that directory.
- Launching headed (`headless=False`).
- Disabling Playwright's fixed viewport (`no_viewport=True`).
- Adding `--disable-blink-features=AutomationControlled`.
- Adding `--start-maximized` for headed sessions.
- Ignoring Playwright's `--enable-automation` default argument.

The automatic user data directory is:

- macOS: `~/Library/Application Support/playwright-byob/chrome-user-data`
- Windows: `%LOCALAPPDATA%\playwright-byob\chrome-user-data`
- Linux: `$XDG_DATA_HOME/playwright-byob/chrome-user-data`, or
  `~/.local/share/playwright-byob/chrome-user-data`

`build_chrome_launch_config()` resolves this path but does not create it.
Chrome creates it when Playwright launches the persistent context.

If Chrome is not detected, the launch helper raises `ChromeNotFoundError` with
the checked paths. Set `PLAYWRIGHT_BYOB_CHROME_PATH` or pass `browser_path=...`
explicitly.

If the platform app data directory cannot be determined, it raises
`ConfigurationError`. Set `PLAYWRIGHT_BYOB_USER_DATA_DIR` or pass
`user_data_dir=...` explicitly.

Chrome 136 and newer ignore `--remote-debugging-port` and
`--remote-debugging-pipe` when the user data directory is Chrome stable's
platform default profile root. Playwright's `launch_persistent_context()`
depends on `--remote-debugging-pipe`, so that configuration fails or times out.
If you explicitly select that root with Chrome stable, playwright-byob
raises `ChromeRemoteDebuggingBlockedError` before launch. The Chrome team
documents the restriction at
<https://developer.chrome.com/blog/remote-debugging-port>.

Before launching, the helpers look for Chrome's profile lock artifacts in the
resolved user data directory: `SingletonLock` and `SingletonSocket` on Linux
and macOS, or `lockfile` on Windows. If one is present, they raise
`ChromeProfileInUseError` with a message to close Chrome or use a separate
`user_data_dir`. `build_chrome_launch_config()` performs the same check.
This lock check is advisory because stale lock files can remain after Chrome
crashes. Pass `check_profile_lock=False` only when you know the lock is stale.

## Choose a browser or profile

```python
from playwright.sync_api import sync_playwright
from playwright_byob import launch_chrome

with sync_playwright() as p:
    context = launch_chrome(
        p,
        browser_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        user_data_dir="~/Library/Application Support/playwright-byob/work-profile",
        profile_directory=None,
        timeout=30_000,
    )
```

Set `profile_directory=None` if the `user_data_dir` already points at an isolated
profile root and you do not want to pass Chrome's `--profile-directory` flag.

Pass `browser_path=None` only when you want to skip installed Chrome detection
and use Playwright's branded `channel="chrome"` path.

Do not use Chrome stable's platform default profile root, such as
`~/Library/Application Support/Google/Chrome`,
`%LOCALAPPDATA%\Google\Chrome\User Data`, or `~/.config/google-chrome`, as
`user_data_dir` for Chrome stable. Chrome 136+ ignores the remote debugging pipe
there even when the path is passed explicitly.

## Recommended profile patterns

There are two separate decisions:

- which Chrome binary to launch;
- which browser profile state to use.

playwright-byob helps with the first decision. It can use the installed Chrome
binary without requiring a Playwright Chromium download. For the second decision,
prefer non-default automation state and the least-sensitive data that works for
the task.

### Installed Chrome with the default automation profile

This is the package default. It uses installed Chrome and stores persistent
state in playwright-byob's own non-default user data directory.

```python
from playwright.sync_api import sync_playwright
from playwright_byob import launch_chrome

with sync_playwright() as p:
    context = launch_chrome(p)
    page = context.new_page()
    page.goto("https://example.com")
    context.close()
```

### Installed Chrome with a temporary profile

This is often the best default for scripts that can log in during the run. It
uses the installed Chrome binary, but stores browser state in a temporary
directory that is removed after the context closes.

```python
import tempfile
from playwright.sync_api import sync_playwright
from playwright_byob import launch_chrome

with sync_playwright() as p:
    with tempfile.TemporaryDirectory() as user_data_dir:
        context = launch_chrome(
            p,
            user_data_dir=user_data_dir,
            profile_directory=None,
        )
        page = context.new_page()
        page.goto("https://example.com/login")
        # Fill the login form here.
        context.close()
```

### Installed Chrome with a custom automation profile

Use this when repeated login is expensive and you want a named automation
directory. Keep it outside Chrome stable's platform default profile root and
avoid using it for daily browsing.

```python
context = launch_chrome(
    p,
    user_data_dir="~/Library/Application Support/playwright-byob/work-profile",
    profile_directory=None,
)
```

### Installed Chrome with a real user profile

This is not a reliable pattern for Chrome stable. Its platform default profile
root contains personal profile state, and Chrome 136+ blocks the remote
debugging pipe there. Chrome can also lock a profile that is already open in a
normal browser window, leaving automation unable to control the launched
profile. Use the default automation profile, a temporary directory, or a custom
non-default automation directory instead.

### Export authenticated state

Playwright's authentication guide recommends saving authenticated browser state
under a gitignored directory such as `playwright/.auth` and treating those files
as secrets. You can export state from a playwright-byob context after logging in:

```python
from pathlib import Path

auth_file = Path("playwright/.auth/user.json")
auth_file.parent.mkdir(parents=True, exist_ok=True)

context.storage_state(path=auth_file)
```

Persistent contexts created by `launch_persistent_context()` do not accept
Playwright's `storage_state` option at launch time. That means
`launch_chrome()` cannot directly start from a storage-state JSON file.
The JSON state is still useful when a later workflow uses standard Playwright
contexts, or when you need an explicit, reviewable artifact for cookies and
local storage.

## Environment variables

These variables are useful for local scripts and CI matrices:

| Variable | Purpose |
| --- | --- |
| `PLAYWRIGHT_BYOB_CHROME_PATH` | Explicit Google Chrome executable path. |
| `PLAYWRIGHT_BYOB_USER_DATA_DIR` | Explicit Chrome user data directory. |
| `PLAYWRIGHT_BYOB_PROFILE_DIRECTORY` | Chrome profile folder, such as `Default` or `Profile 1`. |

Explicit function arguments take precedence over environment variables.
`PLAYWRIGHT_BYOB_USER_DATA_DIR` behaves like an explicit path and does not need
to exist before launch, but it must not be Chrome stable's platform default
profile root.

## Customize flags

Use `args` for additional Chrome flags:

```python
context = launch_chrome(
    p,
    args=["--window-size=1440,1000"],
    locale="en-US",
    timezone_id="America/Los_Angeles",
)
```

Set `default_args=False` to remove this package's default Chrome flags, or pass
`ignore_default_args=None` to keep all Playwright default arguments.

## Build options without launching

For tests and dry runs, resolve launch options without starting Chrome:

```python
from playwright_byob import build_chrome_launch_config

config = build_chrome_launch_config(
    browser_path=None,
    user_data_dir="/tmp/byob-profile",
    profile_directory=None,
)
print(config.user_data_dir)
print(config.to_playwright_kwargs())
```

This explicitly opts into Playwright's `channel="chrome"` path and is the
recommended pattern for CI tests that do not have Google Chrome installed.
