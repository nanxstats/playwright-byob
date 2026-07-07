from __future__ import annotations

import os
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import BrowserContext, Playwright, sync_playwright

from playwright_byob import detect_chrome_executable, launch_chrome

_SESSION_VALUE = "research-session"
_EXPECTED_STATE = f"storage={_SESSION_VALUE}; cookie={_SESSION_VALUE}"

_TEST_APP_HTML = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>playwright-byob integration app</title>
</head>
<body data-state="loading">
  <main>
    <p id="state">loading</p>
    <form id="state-form">
      <label for="session">Session value</label>
      <input id="session" name="session" value="{_SESSION_VALUE}">
      <button type="submit">Save state</button>
    </form>
  </main>
  <script>
    function byobCookie() {{
      const prefix = "byob_session=";
      const cookies = document.cookie ? document.cookie.split("; ") : [];
      for (const cookie of cookies) {{
        if (cookie.startsWith(prefix)) {{
          return decodeURIComponent(cookie.slice(prefix.length));
        }}
      }}
      return "";
    }}

    function render() {{
      const storage = localStorage.getItem("byob_session") || "";
      const cookie = byobCookie();
      document.body.dataset.state = storage && cookie ? "restored" : "empty";
      document.getElementById("state").textContent =
        "storage=" + (storage || "missing") + "; cookie=" + (cookie || "missing");
    }}

    document.getElementById("state-form").addEventListener("submit", (event) => {{
      event.preventDefault();
      const value = new FormData(event.currentTarget).get("session");
      localStorage.setItem("byob_session", value);
      document.cookie =
        "byob_session=" + encodeURIComponent(value) +
        "; Max-Age=3600; Path=/; SameSite=Lax";
      render();
    }});

    render();
  </script>
</body>
</html>
""".encode()


class _IntegrationAppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in {"/", "/index.html"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(_TEST_APP_HTML)))
        self.end_headers()
        self.wfile.write(_TEST_APP_HTML)

    def log_message(self, format: str, *args: Any) -> None:
        return


@contextmanager
def _serve_test_app() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _IntegrationAppHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port

    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _running_in_ci() -> bool:
    for name in ("CI", "GITHUB_ACTIONS"):
        value = os.environ.get(name, "").lower()
        if value not in {"", "0", "false", "no"}:
            return True
    return False


def _local_macos_chrome_path() -> Path:
    if sys.platform != "darwin":
        pytest.skip("installed Chrome integration test only runs on local macOS")
    if _running_in_ci():
        pytest.skip("installed Chrome integration test is skipped in CI")

    chrome_path = detect_chrome_executable(sys_platform="darwin")
    if chrome_path is None:
        pytest.skip("installed Google Chrome was not found")
    return chrome_path


def _launch_test_context(
    playwright: Playwright,
    *,
    chrome_path: Path,
    user_data_dir: Path,
) -> BrowserContext:
    # Keep the integration test isolated from named profiles in real Chrome roots.
    return launch_chrome(
        playwright,
        browser_path=chrome_path,
        user_data_dir=user_data_dir,
        profile_directory=None,
        headless=True,
        no_viewport=False,
        timeout=30_000,
    )


def _write_browser_state(
    playwright: Playwright,
    *,
    chrome_path: Path,
    user_data_dir: Path,
    app_url: str,
) -> None:
    context = _launch_test_context(
        playwright,
        chrome_path=chrome_path,
        user_data_dir=user_data_dir,
    )
    try:
        page = context.new_page()
        page.goto(app_url, wait_until="domcontentloaded")
        page.get_by_label("Session value").fill(_SESSION_VALUE)
        page.get_by_role("button", name="Save state").click()
        page.wait_for_selector("body[data-state='restored']")
        assert page.locator("#state").text_content() == _EXPECTED_STATE
    finally:
        context.close()


def _read_browser_state(
    playwright: Playwright,
    *,
    chrome_path: Path,
    user_data_dir: Path,
    app_url: str,
) -> str:
    context = _launch_test_context(
        playwright,
        chrome_path=chrome_path,
        user_data_dir=user_data_dir,
    )
    try:
        page = context.new_page()
        page.goto(app_url, wait_until="domcontentloaded")
        page.wait_for_selector("body[data-state='restored']")
        state = page.locator("#state").text_content()
        assert state is not None
        return state
    finally:
        context.close()


@pytest.mark.integration
def test_launch_chrome_persists_cookie_and_local_storage_in_temp_user_data_dir(
    tmp_path: Path,
) -> None:
    chrome_path = _local_macos_chrome_path()
    user_data_dir = tmp_path / "chrome-user-data"
    user_data_dir.mkdir()

    with _serve_test_app() as app_url, sync_playwright() as playwright:
        _write_browser_state(
            playwright,
            chrome_path=chrome_path,
            user_data_dir=user_data_dir,
            app_url=app_url,
        )
        restored_state = _read_browser_state(
            playwright,
            chrome_path=chrome_path,
            user_data_dir=user_data_dir,
            app_url=app_url,
        )

    assert restored_state == _EXPECTED_STATE
