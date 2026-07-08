"""Utilities for launching Playwright with an installed Google Chrome profile."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeAlias

from playwright.async_api import BrowserContext as AsyncBrowserContext
from playwright.async_api import Playwright as AsyncPlaywright
from playwright.sync_api import BrowserContext as SyncBrowserContext
from playwright.sync_api import Playwright as SyncPlaywright

Auto: TypeAlias = Literal["auto"]
PathLike: TypeAlias = str | os.PathLike[str]
PathSetting: TypeAlias = PathLike | Auto | None
ProfileSetting: TypeAlias = str | Auto | None
IgnoreDefaultArgs: TypeAlias = bool | Sequence[str] | None

CHROME_PATH_ENV = "PLAYWRIGHT_BYOB_CHROME_PATH"
USER_DATA_DIR_ENV = "PLAYWRIGHT_BYOB_USER_DATA_DIR"
PROFILE_DIRECTORY_ENV = "PLAYWRIGHT_BYOB_PROFILE_DIRECTORY"
DEFAULT_CHANNEL = "chrome"
DEFAULT_PROFILE_DIRECTORY = "Default"
DEFAULT_IGNORE_DEFAULT_ARGS: tuple[str, ...] = ("--enable-automation",)
DEFAULT_CHROME_ARGS: tuple[str, ...] = (
    "--disable-blink-features=AutomationControlled",
)


class PlaywrightByobError(RuntimeError):
    """Base exception for playwright-byob failures."""


class ChromeNotFoundError(PlaywrightByobError):
    """Raised when a requested Chrome executable cannot be found."""


class ChromeProfileNotFoundError(PlaywrightByobError):
    """Raised when the default Chrome user data directory cannot be found."""


class ConfigurationError(PlaywrightByobError, ValueError):
    """Raised when launch configuration is invalid."""


@dataclass(frozen=True)
class ChromeLaunchConfig:
    """Resolved arguments for ``chromium.launch_persistent_context``.

    ``user_data_dir`` is passed as the first positional argument. ``options`` is
    expanded as keyword arguments.
    """

    user_data_dir: Path
    options: Mapping[str, Any]

    def to_playwright_kwargs(self) -> dict[str, Any]:
        """Return a mutable copy of the keyword arguments for Playwright."""
        return dict(self.options)


def chrome_executable_candidates(
    *,
    sys_platform: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Return plausible Google Chrome executable paths for the current platform.

    The function only builds candidates; it does not read profile data or launch
    Chrome. The ``PLAYWRIGHT_BYOB_CHROME_PATH`` environment variable, when set,
    is returned first.
    """
    platform = sys_platform or sys.platform
    environ = os.environ if env is None else env
    candidates: list[Path] = []

    env_path = environ.get(CHROME_PATH_ENV)
    if env_path:
        candidates.append(Path(env_path).expanduser())

    if platform == "darwin":
        candidates.append(
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        )
        home = _home_path(environ)
        if home is not None:
            candidates.append(
                home
                / "Applications"
                / "Google Chrome.app"
                / "Contents"
                / "MacOS"
                / "Google Chrome"
            )
    elif platform.startswith("win"):
        for key in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            root = environ.get(key)
            if root:
                candidates.append(
                    Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
                )
    else:
        for command in (
            "google-chrome",
            "google-chrome-stable",
            "chrome",
        ):
            found = shutil.which(
                command,
                path=environ.get("PATH") if env is None else environ.get("PATH", ""),
            )
            if found:
                candidates.append(Path(found))
        candidates.extend(
            [
                Path("/usr/bin/google-chrome"),
                Path("/usr/bin/google-chrome-stable"),
                Path("/opt/google/chrome/chrome"),
            ]
        )

    return _dedupe_paths(candidates)


def detect_chrome_executable(
    browser_path: PathSetting = "auto",
    *,
    sys_platform: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    """Return an existing Google Chrome executable, or ``None`` if not found.

    Pass ``browser_path`` to check one explicit path. With the default
    ``"auto"``, common platform locations and ``PLAYWRIGHT_BYOB_CHROME_PATH``
    are checked.
    """
    explicit = _coerce_optional_path(browser_path)
    if explicit is not None:
        return explicit if explicit.exists() else None

    for candidate in chrome_executable_candidates(
        sys_platform=sys_platform,
        env=env,
    ):
        if candidate.exists():
            return candidate
    return None


def chrome_user_data_dir_candidates(
    *,
    sys_platform: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Return plausible Google Chrome user data directories.

    These are profile roots such as ``.../Google/Chrome`` on macOS or
    ``.../Google/Chrome/User Data`` on Windows. They may contain profile folders
    named ``Default``, ``Profile 1``, and so on.
    """
    platform = sys_platform or sys.platform
    environ = os.environ if env is None else env
    candidates: list[Path] = []

    env_path = environ.get(USER_DATA_DIR_ENV)
    if env_path:
        candidates.append(Path(env_path).expanduser())

    if platform == "darwin":
        home = _home_path(environ)
        if home is not None:
            candidates.append(
                home / "Library" / "Application Support" / "Google" / "Chrome"
            )
    elif platform.startswith("win"):
        local_app_data = environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Google" / "Chrome" / "User Data")
    else:
        home = _home_path(environ)
        if home is not None:
            candidates.append(home / ".config" / "google-chrome")

    return _dedupe_paths(candidates)


def detect_chrome_user_data_dir(
    user_data_dir: PathSetting = "auto",
    *,
    sys_platform: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    """Return an existing Google Chrome user data directory, or ``None``."""
    explicit = _coerce_optional_path(user_data_dir)
    if explicit is not None:
        return explicit if explicit.exists() else None

    for candidate in chrome_user_data_dir_candidates(
        sys_platform=sys_platform,
        env=env,
    ):
        if candidate.exists():
            return candidate
    return None


def build_chrome_launch_config(
    *,
    browser_path: PathSetting = "auto",
    user_data_dir: PathSetting = "auto",
    profile_directory: ProfileSetting = "auto",
    channel: str | None = DEFAULT_CHANNEL,
    headless: bool | None = False,
    args: Sequence[str] | None = None,
    default_args: bool = True,
    ignore_default_args: IgnoreDefaultArgs = DEFAULT_IGNORE_DEFAULT_ARGS,
    no_viewport: bool | None = True,
    sys_platform: str | None = None,
    env: Mapping[str, str] | None = None,
    **launch_options: Any,
) -> ChromeLaunchConfig:
    """Build resolved launch parameters for Playwright's persistent context.

    Defaults are intentionally tuned for using installed Google Chrome in headed
    mode with a persistent profile:

    - use the installed Chrome executable;
    - use the existing platform Chrome user data directory;
    - select the ``Default`` Chrome profile directory;
    - run headed with Playwright's fixed viewport disabled;
    - hide Playwright's ``--enable-automation`` default argument.

    Extra ``launch_options`` are passed directly to Playwright and can override
    most defaults. Use ``args`` for additional Chrome flags, or set
    ``default_args=False`` to opt out of this package's default Chrome flags.
    Set ``browser_path=None`` to skip Chrome executable detection and ask
    Playwright to use ``channel`` instead.
    """
    environ = os.environ if env is None else env
    resolved_user_data_dir = _resolve_user_data_dir(
        user_data_dir,
        sys_platform=sys_platform,
        env=environ,
    )
    resolved_profile_directory = _resolve_profile_directory(
        profile_directory,
        env=environ,
    )
    resolved_browser_path = _resolve_browser_path(
        browser_path,
        sys_platform=sys_platform,
        env=environ,
    )

    options: dict[str, Any] = {}
    if resolved_browser_path is not None:
        options["executable_path"] = resolved_browser_path
    elif channel is not None:
        options["channel"] = channel

    if headless is not None:
        options["headless"] = headless

    launch_args = _build_chrome_args(
        profile_directory=resolved_profile_directory,
        headless=headless,
        args=args,
        default_args=default_args,
    )
    if launch_args:
        options["args"] = launch_args

    if ignore_default_args is not None:
        options["ignore_default_args"] = ignore_default_args

    if no_viewport is not None and "viewport" not in launch_options:
        options["no_viewport"] = no_viewport

    options.update(launch_options)
    return ChromeLaunchConfig(
        user_data_dir=resolved_user_data_dir,
        options=options,
    )


def launch_chrome(
    playwright: SyncPlaywright,
    *,
    browser_path: PathSetting = "auto",
    user_data_dir: PathSetting = "auto",
    profile_directory: ProfileSetting = "auto",
    channel: str | None = DEFAULT_CHANNEL,
    headless: bool | None = False,
    args: Sequence[str] | None = None,
    default_args: bool = True,
    ignore_default_args: IgnoreDefaultArgs = DEFAULT_IGNORE_DEFAULT_ARGS,
    no_viewport: bool | None = True,
    **launch_options: Any,
) -> SyncBrowserContext:
    """Launch a sync Playwright persistent context with installed Chrome.

    Example:
        ```python
        from playwright.sync_api import sync_playwright
        from playwright_byob import launch_chrome

        with sync_playwright() as p:
            context = launch_chrome(p)
            page = context.new_page()
            page.goto("https://example.com")
            context.close()
        ```
    """
    config = build_chrome_launch_config(
        browser_path=browser_path,
        user_data_dir=user_data_dir,
        profile_directory=profile_directory,
        channel=channel,
        headless=headless,
        args=args,
        default_args=default_args,
        ignore_default_args=ignore_default_args,
        no_viewport=no_viewport,
        **launch_options,
    )
    return playwright.chromium.launch_persistent_context(
        config.user_data_dir,
        **config.to_playwright_kwargs(),
    )


async def async_launch_chrome(
    playwright: AsyncPlaywright,
    *,
    browser_path: PathSetting = "auto",
    user_data_dir: PathSetting = "auto",
    profile_directory: ProfileSetting = "auto",
    channel: str | None = DEFAULT_CHANNEL,
    headless: bool | None = False,
    args: Sequence[str] | None = None,
    default_args: bool = True,
    ignore_default_args: IgnoreDefaultArgs = DEFAULT_IGNORE_DEFAULT_ARGS,
    no_viewport: bool | None = True,
    **launch_options: Any,
) -> AsyncBrowserContext:
    """Launch an async Playwright persistent context with installed Chrome."""
    config = build_chrome_launch_config(
        browser_path=browser_path,
        user_data_dir=user_data_dir,
        profile_directory=profile_directory,
        channel=channel,
        headless=headless,
        args=args,
        default_args=default_args,
        ignore_default_args=ignore_default_args,
        no_viewport=no_viewport,
        **launch_options,
    )
    return await playwright.chromium.launch_persistent_context(
        config.user_data_dir,
        **config.to_playwright_kwargs(),
    )


def _resolve_user_data_dir(
    user_data_dir: PathSetting,
    *,
    sys_platform: str | None,
    env: Mapping[str, str],
) -> Path:
    explicit = _coerce_optional_path(user_data_dir)
    if explicit is not None:
        return explicit

    env_user_data_dir = env.get(USER_DATA_DIR_ENV)
    if env_user_data_dir:
        env_user_data_path = Path(env_user_data_dir).expanduser()
        if env_user_data_path.exists():
            return env_user_data_path
        msg = (
            f"Chrome user data directory from {USER_DATA_DIR_ENV} "
            f"does not exist: {env_user_data_path}"
        )
        raise ChromeProfileNotFoundError(msg)

    detected = detect_chrome_user_data_dir(
        "auto",
        sys_platform=sys_platform,
        env=env,
    )
    if detected is not None:
        return detected

    candidates = ", ".join(
        str(path)
        for path in chrome_user_data_dir_candidates(sys_platform=sys_platform, env=env)
    )
    msg = (
        "Could not find an existing Google Chrome user data directory. "
        f"Set {USER_DATA_DIR_ENV} or pass user_data_dir=... explicitly. "
        f"Checked: {candidates}."
    )
    raise ChromeProfileNotFoundError(msg)


def _resolve_browser_path(
    browser_path: PathSetting,
    *,
    sys_platform: str | None,
    env: Mapping[str, str],
) -> Path | None:
    if browser_path is None:
        return None

    explicit = _coerce_optional_path(browser_path)
    if explicit is not None:
        if explicit.exists():
            return explicit
        msg = f"Chrome executable does not exist: {explicit}"
        raise ChromeNotFoundError(msg)

    env_browser_path = env.get(CHROME_PATH_ENV)
    if env_browser_path:
        env_browser = Path(env_browser_path).expanduser()
        if env_browser.exists():
            return env_browser
        msg = f"Chrome executable from {CHROME_PATH_ENV} does not exist: {env_browser}"
        raise ChromeNotFoundError(msg)

    candidates = chrome_executable_candidates(
        sys_platform=sys_platform,
        env=env,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate

    msg = (
        "Could not find an installed Google Chrome executable. "
        f"Set {CHROME_PATH_ENV} or pass browser_path=... explicitly. "
        f"Checked {CHROME_PATH_ENV} and candidate paths: "
        f"{_format_checked_paths(candidates)}."
    )
    raise ChromeNotFoundError(msg)


def _resolve_profile_directory(
    profile_directory: ProfileSetting,
    *,
    env: Mapping[str, str],
) -> str | None:
    resolved: str | None
    if profile_directory == "auto":
        resolved = env.get(PROFILE_DIRECTORY_ENV, DEFAULT_PROFILE_DIRECTORY)
    else:
        resolved = profile_directory
    if resolved is None:
        return None
    if not resolved:
        msg = "profile_directory must be a non-empty folder name or None"
        raise ConfigurationError(msg)
    if "/" in resolved or "\\" in resolved or resolved in {".", ".."}:
        msg = "profile_directory must be a Chrome profile folder name, not a path"
        raise ConfigurationError(msg)
    return resolved


def _build_chrome_args(
    *,
    profile_directory: str | None,
    headless: bool | None,
    args: Sequence[str] | None,
    default_args: bool,
) -> list[str]:
    launch_args: list[str] = []
    if default_args:
        launch_args.extend(DEFAULT_CHROME_ARGS)
        if headless is False:
            launch_args.append("--start-maximized")
    if profile_directory is not None:
        launch_args.append(f"--profile-directory={profile_directory}")
    if args:
        launch_args.extend(args)
    return launch_args


def _coerce_optional_path(value: PathSetting) -> Path | None:
    if value is None or value == "auto":
        return None
    return Path(value).expanduser()


def _home_path(env: Mapping[str, str]) -> Path | None:
    home = env.get("HOME") or env.get("USERPROFILE")
    if home:
        return Path(home).expanduser()
    return None


def _dedupe_paths(paths: Sequence[Path]) -> tuple[Path, ...]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = os.fspath(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return tuple(result)


def _format_checked_paths(paths: Sequence[Path]) -> str:
    return ", ".join(str(path) for path in paths) or "(none)"
