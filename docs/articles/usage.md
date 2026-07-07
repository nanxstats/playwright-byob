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
- Falling back to Playwright's branded `channel="chrome"` when no path is found.
- Using the platform Chrome user data directory.
- Selecting the `Default` Chrome profile folder.
- Launching headed (`headless=False`).
- Disabling Playwright's fixed viewport (`no_viewport=True`).
- Adding `--disable-blink-features=AutomationControlled`.
- Adding `--start-maximized` for headed sessions.
- Ignoring Playwright's `--enable-automation` default argument.

If the default Chrome user data directory is not present, the launch helper
raises `ChromeProfileNotFoundError` instead of silently creating a fake profile.

## Choose a browser or profile

```python
from playwright.sync_api import sync_playwright
from playwright_byob import launch_chrome

with sync_playwright() as p:
    context = launch_chrome(
        p,
        browser_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        user_data_dir="~/Library/Application Support/Google/Chrome",
        profile_directory="Profile 1",
        timeout=30_000,
    )
```

Set `profile_directory=None` if the `user_data_dir` already points at an isolated
profile root and you do not want to pass Chrome's `--profile-directory` flag.

## Environment variables

These variables are useful for local scripts and CI matrices:

| Variable | Purpose |
| --- | --- |
| `PLAYWRIGHT_BYOB_CHROME_PATH` | Explicit Google Chrome executable path. |
| `PLAYWRIGHT_BYOB_USER_DATA_DIR` | Explicit Chrome user data directory. |
| `PLAYWRIGHT_BYOB_PROFILE_DIRECTORY` | Chrome profile folder, such as `Default` or `Profile 1`. |

Explicit function arguments take precedence over detection, while the environment
variables participate in automatic detection.

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

This is the recommended pattern for CI tests that do not have Google Chrome
installed.
