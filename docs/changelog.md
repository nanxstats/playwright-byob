# Changelog

## playwright-byob (development version)

### Improvements

- Raise `ChromeProfileInUseError` before launching when the resolved Chrome
  user data directory contains known profile lock artifacts. Pass
  `check_profile_lock=False` to skip the advisory stale lock check (#14).
- Raise `ChromeNotFoundError` when automatic Chrome executable detection finds
  nothing, with a message listing checked paths and
  `PLAYWRIGHT_BYOB_CHROME_PATH`. Pass `browser_path=None` to opt into
  Playwright's `channel="chrome"` path explicitly (#15).

### Testing

- Add a signature drift regression test to keep the shared launch options for
  `launch_chrome()`, `async_launch_chrome()`, and `build_chrome_launch_config()`
  aligned while preserving builder-only `sys_platform` and `env` overrides (#16).

## playwright-byob 0.1.2

### Dependencies

- Lower the minimum Playwright version to 1.50.0 (#10).

### Documentation

- Clarify that using installed Chrome and using a real user profile are separate
  choices, and document safer profile patterns such as temporary profiles and
  dedicated automation profiles (#9).
- Document the relationship between persistent Chrome contexts and Playwright's
  storage-state authentication files (#9).

## playwright-byob 0.1.1

### Testing

- Add a macOS-only local integration test that launches installed Google Chrome
  through `launch_chrome()`, drives a small local HTML app, and verifies cookie
  and local storage persistence across browser sessions (#6).
- Register a pytest `integration` marker for tests that launch an installed
  browser and are skipped in CI (#6).

### Documentation

- Move privacy and local integration testing guidance into a dedicated article (#8).

## playwright-byob 0.1.0

### New features

- Add sync and async helpers, `launch_chrome()` and `async_launch_chrome()`,
  for launching Playwright with a persistent Google Chrome context.
- Add automatic detection for installed Google Chrome and the platform Chrome
  user data directory on macOS, Windows, and Linux.
- Add sensible headed Chrome defaults: persistent profile,
  `Default` profile selection, no fixed Playwright viewport, maximized window,
  and removal of Playwright's `--enable-automation` default argument.
- Add explicit customization for Chrome executable path, user data directory,
  profile directory, Chrome flags, and arbitrary Playwright launch options.
- Add environment variable overrides via `PLAYWRIGHT_BYOB_CHROME_PATH`,
  `PLAYWRIGHT_BYOB_USER_DATA_DIR`, and `PLAYWRIGHT_BYOB_PROFILE_DIRECTORY`.
- Add `build_chrome_launch_config()` for tests, dry runs, and inspecting
  resolved launch options without starting a browser.
- Add typed public exceptions for missing Chrome executables,
  missing Chrome profile directories, and invalid configuration.

### Documentation

- Add README and Zensical documentation covering installation,
  sync and async usage, defaults, customization, environment variables,
  and privacy guidance.
- Add coding-agent guidance documenting privacy rules, development commands,
  and design preferences for future maintenance.

### Testing

- Add a pytest suite that verifies launch configuration and platform detection
  without reading real user browser data or requiring Chrome in CI.
