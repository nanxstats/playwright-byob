# playwright-byob

[![PyPI version](https://img.shields.io/pypi/v/playwright-byob)](https://pypi.org/project/playwright-byob/)
![Python versions](https://img.shields.io/pypi/pyversions/playwright-byob)
[![CI tests](https://github.com/nanxstats/playwright-byob/actions/workflows/ci-tests.yml/badge.svg)](https://github.com/nanxstats/playwright-byob/actions/workflows/ci-tests.yml)
[![Mypy check](https://github.com/nanxstats/playwright-byob/actions/workflows/mypy.yml/badge.svg)](https://github.com/nanxstats/playwright-byob/actions/workflows/mypy.yml)
[![Ruff check](https://github.com/nanxstats/playwright-byob/actions/workflows/ruff-check.yml/badge.svg)](https://github.com/nanxstats/playwright-byob/actions/workflows/ruff-check.yml)
[![Documentation](https://github.com/nanxstats/playwright-byob/actions/workflows/docs.yml/badge.svg)](https://nanx.me/playwright-byob/)
![License](https://img.shields.io/pypi/l/playwright-byob)

Bring your own browser to Playwright.

playwright-byob is a tiny Python helper for launching Playwright against the
real Google Chrome installation already present on a machine.
It keeps the API close to Playwright, but chooses practical defaults for headed,
persistent Chrome automation.

## Installation

```bash
pip install playwright-byob
```

With `uv`:

```bash
uv add playwright-byob
```

## Quick start

```python
from playwright.sync_api import sync_playwright
from playwright_byob import launch_chrome

with sync_playwright() as p:
    context = launch_chrome(p)
    page = context.new_page()
    page.goto("https://example.com")
    print(page.title())
    context.close()
```

The default launch uses installed Chrome, opens headed, uses the platform Chrome
user data directory, selects the `Default` profile, disables Playwright's fixed
viewport, and removes the `--enable-automation` default argument.
If Chrome is not detected, it raises `ChromeNotFoundError`; set
`PLAYWRIGHT_BYOB_CHROME_PATH` or pass `browser_path=...` explicitly.

## Customize the browser or profile

```python
from playwright.sync_api import sync_playwright
from playwright_byob import launch_chrome

with sync_playwright() as p:
    context = launch_chrome(
        p,
        browser_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        user_data_dir="~/Library/Application Support/Google/Chrome",
        profile_directory="Profile 1",
        args=["--window-size=1440,1000"],
        timeout=30_000,
    )
```

You can also use environment variables:

- `PLAYWRIGHT_BYOB_CHROME_PATH`
- `PLAYWRIGHT_BYOB_USER_DATA_DIR`
- `PLAYWRIGHT_BYOB_PROFILE_DIRECTORY`

Pass `browser_path=None` to skip installed Chrome detection and use
Playwright's `channel="chrome"` path instead.

## Recommended profile patterns

Using the installed Chrome binary and using your daily Chrome profile are
separate choices. In practice, the most reliable paths are:

1. **Installed Chrome with a temporary profile**.
   Use `tempfile.TemporaryDirectory()` as `user_data_dir` and
   `profile_directory=None`, then log in during the run.
   This avoids downloading Playwright Chromium without touching
   a personal Chrome profile.
2. **Installed Chrome with a dedicated automation profile**.
   Create a separate Chrome profile for automation and point `user_data_dir`
   and `profile_directory` at it. Keep it out of day-to-day browsing.
3. **Installed Chrome with a real user profile**.
   This is convenient for local one-off scripts, but it can expose sensitive
   state, conflict with a profile already open in Chrome, or trigger account
   verification prompts.

Playwright's authentication guide also describes saving authenticated browser
state to JSON files with `context.storage_state(path=...)` and keeping those
files out of source control. Because playwright-byob launches persistent
contexts, it cannot pass `storage_state` directly at launch time, but exporting
state after login is still useful when a workflow later uses standard
Playwright contexts.

## Privacy note

A real Chrome profile or exported storage-state JSON file can contain cookies,
local storage, saved sessions, and other sensitive state,
**so use these intentionally**.
Tests in this project never read or launch a real user profile.
They use temporary directories and fake Playwright objects.

The local integration test is macOS-only and skipped in CI. It launches the
installed Chrome executable with an isolated temporary user data directory,
then verifies cookie and local storage persistence across two browser sessions.
