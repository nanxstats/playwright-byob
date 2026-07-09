"""Utilities for launching Playwright with installed Google Chrome."""

from __future__ import annotations

import ntpath
import os
import posixpath
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
_AUTOMATION_USER_DATA_DIR_PARTS = ("playwright-byob", "chrome-user-data")
_REMOTE_DEBUGGING_RESTRICTION_URL = (
    "https://developer.chrome.com/blog/remote-debugging-port"
)
_RESTRICTED_CHROME_CHANNELS = {
    "chrome",
    "chrome-beta",
    "chrome-dev",
    "chrome-canary",
}
_RESTRICTED_CHROME_EXECUTABLE_NAMES = {
    "chrome",
    "chrome.exe",
    "google chrome",
    "google chrome beta",
    "google chrome canary",
    "google chrome dev",
    "google-chrome",
    "google-chrome-beta",
    "google-chrome-stable",
    "google-chrome-unstable",
}


class PlaywrightByobError(RuntimeError):
    """Base exception for playwright-byob failures."""


class ChromeNotFoundError(PlaywrightByobError):
    """Raised when a requested Chrome executable cannot be found."""


class ChromeProfileNotFoundError(PlaywrightByobError):
    """Raised when a requested Chrome user data directory cannot be found."""


class ChromeProfileInUseError(PlaywrightByobError):
    """Raised when the Chrome user data directory appears to be locked."""


class ConfigurationError(PlaywrightByobError, ValueError):
    """Raised when launch configuration is invalid."""


class ChromeRemoteDebuggingBlockedError(ConfigurationError):
    """Raised when Chrome blocks remote debugging for the selected profile root."""


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
    """Return configured and platform default Google Chrome user data directories.

    ``PLAYWRIGHT_BYOB_USER_DATA_DIR`` is returned first when set. Platform
    defaults follow, such as ``.../Google/Chrome`` on macOS or
    ``.../Google/Chrome/User Data`` on Windows. They may contain profile folders
    named ``Default``, ``Profile 1``, and so on. This function is exposed for
    detection and migration code; launch defaults use a separate automation
    directory.
    """
    environ = os.environ if env is None else env
    candidates: list[Path] = []

    env_path = environ.get(USER_DATA_DIR_ENV)
    if env_path:
        candidates.append(Path(env_path).expanduser())

    candidates.extend(
        _platform_chrome_user_data_dir_candidates(
            sys_platform=sys_platform,
            env=environ,
        )
    )

    return _dedupe_paths(candidates)


def _platform_chrome_user_data_dir_candidates(
    *,
    sys_platform: str | None,
    env: Mapping[str, str],
) -> tuple[Path, ...]:
    platform = sys_platform or sys.platform
    candidates: list[Path] = []

    if platform == "darwin":
        home = _home_path(env)
        if home is not None:
            candidates.append(
                home / "Library" / "Application Support" / "Google" / "Chrome"
            )
    elif platform.startswith("win"):
        local_app_data = env.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Google" / "Chrome" / "User Data")
    else:
        home = _home_path(env)
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
    check_profile_lock: bool = True,
    sys_platform: str | None = None,
    env: Mapping[str, str] | None = None,
    **launch_options: Any,
) -> ChromeLaunchConfig:
    """Build resolved launch parameters for Playwright's persistent context.

    Defaults are intentionally tuned for using installed Google Chrome in headed
    mode with a persistent, non-default automation profile:

    - use the installed Chrome executable;
    - use a package-owned Chrome user data directory under the platform app data
      directory;
    - select the ``Default`` Chrome profile directory;
    - run headed with Playwright's fixed viewport disabled;
    - hide Playwright's ``--enable-automation`` default argument.

    Extra ``launch_options`` are passed directly to Playwright and can override
    most defaults. Use ``args`` for additional Chrome flags, or set
    ``default_args=False`` to opt out of this package's default Chrome flags.
    Set ``browser_path=None`` to skip Chrome executable detection and ask
    Playwright to use ``channel`` instead. Set ``check_profile_lock=False`` to
    skip the best-effort check for Chrome profile lock artifacts.

    Chrome 136 and newer ignore Playwright's remote debugging pipe when the user
    data directory is the platform default Chrome profile root. This function
    raises ``ChromeRemoteDebuggingBlockedError`` for that configuration before
    Playwright starts Chrome.
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
    _raise_if_remote_debugging_blocked(
        resolved_user_data_dir,
        options=options,
        sys_platform=sys_platform,
        env=environ,
    )
    if check_profile_lock:
        _raise_if_profile_locked(
            resolved_user_data_dir,
            sys_platform=sys_platform,
        )
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
    check_profile_lock: bool = True,
    **launch_options: Any,
) -> SyncBrowserContext:
    """Launch a sync Playwright persistent context with installed Chrome.

    By default, the context uses playwright-byob's dedicated non-default Chrome
    user data directory, not the platform default Chrome profile root.

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
        check_profile_lock=check_profile_lock,
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
    check_profile_lock: bool = True,
    **launch_options: Any,
) -> AsyncBrowserContext:
    """Launch an async persistent context with installed Chrome.

    By default, the context uses playwright-byob's dedicated non-default Chrome
    user data directory, not the platform default Chrome profile root.
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
        check_profile_lock=check_profile_lock,
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
        return Path(env_user_data_dir).expanduser()

    return _default_automation_user_data_dir(
        sys_platform=sys_platform,
        env=env,
    )


def _default_automation_user_data_dir(
    *,
    sys_platform: str | None,
    env: Mapping[str, str],
) -> Path:
    app_data_dir = _platform_app_data_dir(sys_platform=sys_platform, env=env)
    if app_data_dir is None:
        msg = (
            "Could not determine a platform app data directory for "
            "playwright-byob's default Chrome user data directory. "
            f"Set {USER_DATA_DIR_ENV} or pass user_data_dir=... explicitly."
        )
        raise ConfigurationError(msg)

    path = app_data_dir
    for part in _AUTOMATION_USER_DATA_DIR_PARTS:
        path /= part
    return path


def _platform_app_data_dir(
    *,
    sys_platform: str | None,
    env: Mapping[str, str],
) -> Path | None:
    platform = sys_platform or sys.platform
    if platform == "darwin":
        home = _home_path(env)
        return home / "Library" / "Application Support" if home is not None else None
    if platform.startswith("win"):
        local_app_data = env.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data).expanduser()
        user_profile = env.get("USERPROFILE")
        if user_profile:
            return Path(user_profile).expanduser() / "AppData" / "Local"
        return None

    xdg_data_home = env.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser()
    home = _home_path(env)
    return home / ".local" / "share" if home is not None else None


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


def _raise_if_remote_debugging_blocked(
    user_data_dir: Path,
    *,
    options: Mapping[str, Any],
    sys_platform: str | None,
    env: Mapping[str, str],
) -> None:
    if not _is_platform_default_chrome_user_data_dir(
        user_data_dir,
        sys_platform=sys_platform,
        env=env,
    ):
        return
    if not _uses_chrome_remote_debugging_restriction(options):
        return

    msg = (
        "Chrome 136 and newer ignore --remote-debugging-port and "
        "--remote-debugging-pipe when the user data directory is the platform "
        f"default Chrome profile root: {user_data_dir}. "
        "Playwright launch_persistent_context() depends on "
        "--remote-debugging-pipe, so this configuration will fail or time out. "
        "Use user_data_dir='auto' for playwright-byob's dedicated automation "
        "directory, or pass a temporary directory or another dedicated "
        "non-default user_data_dir with profile_directory=None. "
        f"See {_REMOTE_DEBUGGING_RESTRICTION_URL}."
    )
    raise ChromeRemoteDebuggingBlockedError(msg)


def _is_platform_default_chrome_user_data_dir(
    user_data_dir: Path,
    *,
    sys_platform: str | None,
    env: Mapping[str, str],
) -> bool:
    return any(
        _same_path(user_data_dir, candidate, sys_platform=sys_platform)
        for candidate in _platform_chrome_user_data_dir_candidates(
            sys_platform=sys_platform,
            env=env,
        )
    )


def _uses_chrome_remote_debugging_restriction(options: Mapping[str, Any]) -> bool:
    executable_path = options.get("executable_path")
    if isinstance(executable_path, (str, os.PathLike)):
        return _looks_like_restricted_chrome_executable(Path(executable_path))

    channel = options.get("channel")
    return isinstance(channel, str) and channel in _RESTRICTED_CHROME_CHANNELS


def _looks_like_restricted_chrome_executable(path: Path) -> bool:
    path_text = os.fspath(path).casefold()
    if "chrome for testing" in path_text or "chrome-for-testing" in path_text:
        return False
    return path.name.casefold() in _RESTRICTED_CHROME_EXECUTABLE_NAMES


def _same_path(left: Path, right: Path, *, sys_platform: str | None) -> bool:
    return _path_identity(left, sys_platform=sys_platform) == _path_identity(
        right,
        sys_platform=sys_platform,
    )


def _path_identity(path: Path, *, sys_platform: str | None) -> str:
    platform = sys_platform or sys.platform
    path_string = os.fspath(path.expanduser())
    if platform.startswith("win"):
        return ntpath.normcase(ntpath.abspath(path_string))
    return posixpath.normpath(posixpath.abspath(path_string))


def _raise_if_profile_locked(
    user_data_dir: Path,
    *,
    sys_platform: str | None,
) -> None:
    lock_path = _detect_profile_lock(user_data_dir, sys_platform=sys_platform)
    if lock_path is None:
        return

    msg = (
        "Chrome user data directory appears to be in use: "
        f"{user_data_dir}. Found Chrome profile lock artifact: {lock_path.name}. "
        "Close Chrome windows using this profile or pass a separate "
        "user_data_dir. This check is best-effort; if you know the lock is "
        "stale, pass check_profile_lock=False."
    )
    raise ChromeProfileInUseError(msg)


def _detect_profile_lock(
    user_data_dir: Path,
    *,
    sys_platform: str | None,
) -> Path | None:
    for artifact in _profile_lock_artifacts(sys_platform=sys_platform):
        lock_path = user_data_dir / artifact
        if os.path.lexists(lock_path):
            return lock_path
    return None


def _profile_lock_artifacts(*, sys_platform: str | None) -> tuple[str, ...]:
    platform = sys_platform or sys.platform
    if platform.startswith("win"):
        return ("lockfile",)
    return ("SingletonLock", "SingletonSocket")


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
