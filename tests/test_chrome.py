from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any

import pytest

import playwright_byob._chrome as chrome_module
from playwright_byob import (
    CHROME_PATH_ENV,
    DEFAULT_IGNORE_DEFAULT_ARGS,
    PROFILE_DIRECTORY_ENV,
    USER_DATA_DIR_ENV,
    ChromeNotFoundError,
    ChromeProfileNotFoundError,
    ConfigurationError,
    async_launch_chrome,
    build_chrome_launch_config,
    chrome_executable_candidates,
    chrome_user_data_dir_candidates,
    detect_chrome_executable,
    detect_chrome_user_data_dir,
    launch_chrome,
)


class FakeSyncChromium:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, dict[str, Any]]] = []

    def launch_persistent_context(self, user_data_dir: Path, **kwargs: Any) -> str:
        self.calls.append((user_data_dir, kwargs))
        return "sync-context"


class FakeSyncPlaywright:
    def __init__(self) -> None:
        self.chromium = FakeSyncChromium()


class FakeAsyncChromium:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, dict[str, Any]]] = []

    async def launch_persistent_context(
        self, user_data_dir: Path, **kwargs: Any
    ) -> str:
        self.calls.append((user_data_dir, kwargs))
        return "async-context"


class FakeAsyncPlaywright:
    def __init__(self) -> None:
        self.chromium = FakeAsyncChromium()


def _shared_launch_option_defaults(function: object) -> tuple[tuple[str, object], ...]:
    """Return public launch option names and defaults shared by all entry points."""
    signature = inspect.signature(function)
    return tuple(
        (name, parameter.default)
        for name, parameter in signature.parameters.items()
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and name not in {"sys_platform", "env"}
    )


def test_public_launch_option_signatures_stay_in_sync() -> None:
    """Guard against silent drift in duplicated public launch option signatures."""
    shared_build_options = _shared_launch_option_defaults(build_chrome_launch_config)

    assert _shared_launch_option_defaults(launch_chrome) == shared_build_options
    assert _shared_launch_option_defaults(async_launch_chrome) == shared_build_options


def test_chrome_executable_candidates_prefer_env_path(tmp_path: Path) -> None:
    chrome = tmp_path / "chrome"
    env = {CHROME_PATH_ENV: str(chrome), "HOME": str(tmp_path)}

    candidates = chrome_executable_candidates(sys_platform="darwin", env=env)

    assert candidates[0] == chrome
    assert (
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        in candidates
    )


def test_chrome_user_data_dir_candidates_are_platform_specific(tmp_path: Path) -> None:
    mac_candidates = chrome_user_data_dir_candidates(
        sys_platform="darwin",
        env={"HOME": str(tmp_path)},
    )
    linux_candidates = chrome_user_data_dir_candidates(
        sys_platform="linux",
        env={"HOME": str(tmp_path)},
    )
    windows_candidates = chrome_user_data_dir_candidates(
        sys_platform="win32",
        env={"LOCALAPPDATA": str(tmp_path)},
    )

    assert mac_candidates == (
        tmp_path / "Library" / "Application Support" / "Google" / "Chrome",
    )
    assert linux_candidates == (tmp_path / ".config" / "google-chrome",)
    assert windows_candidates == (tmp_path / "Google" / "Chrome" / "User Data",)


def test_empty_env_does_not_fall_back_to_process_home_or_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    which_paths: list[str | None] = []

    def fake_which(command: str, path: str | None = None) -> str | None:
        del command
        which_paths.append(path)
        return "/real-path/chrome" if path is None else None

    monkeypatch.setattr(chrome_module.shutil, "which", fake_which)

    executable_candidates = chrome_executable_candidates(sys_platform="linux", env={})
    user_data_candidates = chrome_user_data_dir_candidates(sys_platform="linux", env={})

    assert which_paths == ["", "", ""]
    assert Path("/real-path/chrome") not in executable_candidates
    assert user_data_candidates == ()


def test_build_config_empty_env_does_not_use_real_user_profile() -> None:
    with pytest.raises(ChromeProfileNotFoundError):
        build_chrome_launch_config(browser_path=None, sys_platform="linux", env={})


def test_detect_chrome_executable_checks_explicit_existing_path(tmp_path: Path) -> None:
    chrome = tmp_path / "chrome"
    chrome.write_text("fake chrome", encoding="utf-8")

    assert detect_chrome_executable(chrome) == chrome
    assert detect_chrome_executable(tmp_path / "missing") is None


def test_detect_user_data_dir_checks_existing_path_only(tmp_path: Path) -> None:
    user_data_dir = tmp_path / "Chrome User Data"
    user_data_dir.mkdir()

    assert detect_chrome_user_data_dir(user_data_dir) == user_data_dir
    assert detect_chrome_user_data_dir(tmp_path / "missing") is None


def test_build_config_uses_explicit_browser_profile_and_sensible_defaults(
    tmp_path: Path,
) -> None:
    chrome = tmp_path / "chrome"
    chrome.write_text("fake chrome", encoding="utf-8")
    user_data_dir = tmp_path / "User Data"
    user_data_dir.mkdir()

    config = build_chrome_launch_config(
        browser_path=chrome,
        user_data_dir=user_data_dir,
        profile_directory="Profile 1",
        args=["--window-size=1440,1000"],
        timeout=12_000,
    )

    options = config.to_playwright_kwargs()
    assert config.user_data_dir == user_data_dir
    assert options["executable_path"] == chrome
    assert "channel" not in options
    assert options["headless"] is False
    assert options["no_viewport"] is True
    assert options["ignore_default_args"] == DEFAULT_IGNORE_DEFAULT_ARGS
    assert options["timeout"] == 12_000
    assert options["args"] == [
        "--disable-blink-features=AutomationControlled",
        "--start-maximized",
        "--profile-directory=Profile 1",
        "--window-size=1440,1000",
    ]


def test_build_config_can_use_playwright_chrome_channel_without_detection(
    tmp_path: Path,
) -> None:
    user_data_dir = tmp_path / "User Data"

    config = build_chrome_launch_config(
        browser_path=None,
        user_data_dir=user_data_dir,
        profile_directory=None,
        default_args=False,
        ignore_default_args=None,
        no_viewport=False,
    )

    options = config.to_playwright_kwargs()
    assert config.user_data_dir == user_data_dir
    assert options == {"channel": "chrome", "headless": False, "no_viewport": False}


def test_build_config_honors_environment_overrides(tmp_path: Path) -> None:
    chrome = tmp_path / "chrome"
    chrome.write_text("fake chrome", encoding="utf-8")
    user_data_dir = tmp_path / "Chrome User Data"
    user_data_dir.mkdir()
    env = {
        CHROME_PATH_ENV: str(chrome),
        USER_DATA_DIR_ENV: str(user_data_dir),
        PROFILE_DIRECTORY_ENV: "Profile 2",
    }

    config = build_chrome_launch_config(env=env)
    options = config.to_playwright_kwargs()

    assert config.user_data_dir == user_data_dir
    assert options["executable_path"] == chrome
    assert "--profile-directory=Profile 2" in options["args"]


def test_build_config_rejects_missing_environment_paths(tmp_path: Path) -> None:
    with pytest.raises(ChromeNotFoundError):
        build_chrome_launch_config(
            user_data_dir=tmp_path,
            env={CHROME_PATH_ENV: str(tmp_path / "missing-chrome")},
        )

    with pytest.raises(ChromeProfileNotFoundError):
        build_chrome_launch_config(
            browser_path=None,
            env={USER_DATA_DIR_ENV: str(tmp_path / "missing-profile")},
        )


def test_build_config_does_not_create_or_use_real_profile_in_auto_mode(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()

    with pytest.raises(ChromeProfileNotFoundError):
        build_chrome_launch_config(
            browser_path=None,
            sys_platform="linux",
            env={"HOME": str(home), "PATH": ""},
        )

    assert not (home / ".config" / "google-chrome").exists()


def test_build_config_rejects_missing_explicit_browser(tmp_path: Path) -> None:
    with pytest.raises(ChromeNotFoundError):
        build_chrome_launch_config(
            browser_path=tmp_path / "missing-chrome",
            user_data_dir=tmp_path,
        )


def test_build_config_rejects_profile_paths(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        build_chrome_launch_config(
            browser_path=None,
            user_data_dir=tmp_path,
            profile_directory="Default/Nested",
        )


def test_launch_chrome_passes_resolved_config_to_sync_playwright(
    tmp_path: Path,
) -> None:
    fake = FakeSyncPlaywright()

    context = launch_chrome(
        fake,  # type: ignore[arg-type]
        browser_path=None,
        user_data_dir=tmp_path,
        profile_directory=None,
        args=["--foo"],
        base_url="https://example.com",
    )

    assert context == "sync-context"
    assert fake.chromium.calls == [
        (
            tmp_path,
            {
                "channel": "chrome",
                "headless": False,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                    "--foo",
                ],
                "ignore_default_args": DEFAULT_IGNORE_DEFAULT_ARGS,
                "no_viewport": True,
                "base_url": "https://example.com",
            },
        ),
    ]


def test_async_launch_chrome_passes_resolved_config_to_async_playwright(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        fake = FakeAsyncPlaywright()
        context = await async_launch_chrome(
            fake,  # type: ignore[arg-type]
            browser_path=None,
            user_data_dir=tmp_path,
            profile_directory="Default",
            headless=True,
        )

        assert context == "async-context"
        assert fake.chromium.calls == [
            (
                tmp_path,
                {
                    "channel": "chrome",
                    "headless": True,
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--profile-directory=Default",
                    ],
                    "ignore_default_args": DEFAULT_IGNORE_DEFAULT_ARGS,
                    "no_viewport": True,
                },
            ),
        ]

    asyncio.run(run())
