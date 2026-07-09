# Privacy

playwright-byob is designed to launch real Google Chrome with persistent browser
state. That is useful for local automation, but it also means profile handling
needs clear boundaries.

## Privacy and safety

A real Chrome profile can include cookies, local storage, extensions, saved
sessions, and other sensitive state. Use real profiles intentionally, and do not
use a personal profile in automated tests.

Prefer temporary directories, purpose-built Chrome profiles, or mock Playwright
objects when verifying integration code. The safest automation pattern is often
installed Chrome with playwright-byob's default automation profile or a
temporary `user_data_dir`, followed by explicit login during the run.

Tests in this project must not read cookies, local storage, history, or other
data from a real user Chrome profile.

Chrome may also lock a profile that is already open in a normal browser window.
For reliable automation, use a dedicated Chrome profile or close the matching
Chrome profile before launching Playwright.

Chrome 136 and newer also ignore remote debugging switches for the platform
default Chrome profile root. Playwright persistent contexts use
`--remote-debugging-pipe`, so playwright-byob rejects that configuration before
launching real Chrome. This is both a reliability issue and a useful boundary:
automation should use a non-default directory instead of a daily Chrome profile.

Some providers treat automation against a normal user profile as suspicious and
may show "verify it is you" prompts or force a fresh login. That is a service
policy decision outside this package. If that happens, switch to a temporary
profile with explicit login, or use a dedicated automation profile.

Playwright's authentication guide recommends storing authenticated browser state
under a gitignored directory such as `playwright/.auth`. Those JSON files can
contain cookies and headers that authenticate as the user, so treat them like
passwords and never commit them. Persistent Chrome contexts can export state via
`context.storage_state(path=...)`, but they cannot consume Playwright's
`storage_state` option directly at launch time.

## Local integration testing

The project includes a macOS-only integration test for installed Chrome:

```bash
uv run pytest -m integration
```

The test is skipped in CI, outside macOS, and when Google Chrome is not found.
It serves a local HTML page, launches installed Chrome through
`launch_chrome()`, writes a cookie and local storage item, closes the browser,
then launches Chrome again to verify that state persisted.

The test uses an isolated temporary user data directory and passes
`profile_directory=None`, so it does not launch or inspect a real user Chrome
profile. The temporary directory is managed by pytest and cleaned up after the
test run.
