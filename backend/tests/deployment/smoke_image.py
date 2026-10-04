"""Run in the release container to check its user, browser and packaged UI.

Usage: docker run --rm --network none --mount <this file> IMAGE python /tmp/smoke_image.py
No provider keys, model requests, search calls or external pages are used.
"""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    assert os.getuid() != 0, "The release image must run as a non-root user"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto("data:text/html,<title>DeepResearch smoke</title><h1>ready</h1>")
            assert page.title() == "DeepResearch smoke"
            assert page.locator("h1").inner_text() == "ready"
        finally:
            browser.close()

    from deeptrace.api import _resolve_dashboard_dir

    dashboard = _resolve_dashboard_dir()
    assert dashboard is not None, "The image must contain the built dashboard"
    assert (dashboard / "index.html").is_file()
    assert list((dashboard / "assets").glob("*.js"))
    Path("/app/runs/.smoke-write").write_text("writable", encoding="utf-8")
    Path("/app/runs/.smoke-write").unlink()
    print("PASS: non-root browser launch, packaged dashboard and writable runtime")


if __name__ == "__main__":
    main()
