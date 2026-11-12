"""Capture the dashboard for the README: starts Streamlit offline on a fresh database and screenshots each page.

Usage: uv run python scripts/screenshots.py
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img"


def free_port() -> int:
    """An unused local port."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(page: Page) -> None:
    """Wait until Streamlit has finished running the script."""
    page.wait_for_selector("[data-testid='stApp']", timeout=60_000)
    page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=120_000)
    time.sleep(1.0)


def main() -> None:
    """Start the app, drive each page, save PNGs."""
    OUT.mkdir(parents=True, exist_ok=True)
    port = free_port()
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "INVOICE_DB": f"{tmp}/ui.db", "RUNS_DIR": f"{tmp}/runs", "INVOICE_MODEL": "offline"}
        server = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", str(ROOT / "app" / "streamlit_app.py"),
             "--server.headless", "true", "--server.port", str(port), "--browser.gatherUsageStats", "false"],
            env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )  # fmt: skip
        try:
            with sync_playwright() as pw:
                # Use an installed Chrome when Playwright has not downloaded its own browser.
                chrome = os.environ.get("CHROME_PATH") or (
                    "/usr/bin/google-chrome" if Path("/usr/bin/google-chrome").exists() else None
                )
                browser = pw.chromium.launch(executable_path=chrome)
                page = browser.new_page(viewport={"width": 1400, "height": 1000}, device_scale_factor=2)
                base = f"http://127.0.0.1:{port}"
                for _ in range(60):
                    try:
                        page.goto(base)
                        break
                    except Exception:
                        time.sleep(1)
                wait_ready(page)
                page.get_by_role("button", name="Process").click()
                page.wait_for_selector("text=Read the file", timeout=60_000)  # the stage list renders last
                wait_ready(page)
                time.sleep(3)  # data grids paint on a canvas after the script finishes
                page.screenshot(path=OUT / "process.png", full_page=True)
                for path, name in [("inbox", "inbox"), ("history", "history"), ("roi", "roi")]:
                    page.goto(f"{base}/{path}")
                    wait_ready(page)
                    time.sleep(3)
                    page.screenshot(path=OUT / f"{name}.png", full_page=True)
                page.goto(f"{base}/batch")
                wait_ready(page)
                page.get_by_role("button", name="Run the scorecard").click()
                page.wait_for_selector("text=Pass", timeout=120_000)
                wait_ready(page)
                page.screenshot(path=OUT / "batch.png", full_page=True)
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)
    print("\n".join(str(p.relative_to(ROOT)) for p in sorted(OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
