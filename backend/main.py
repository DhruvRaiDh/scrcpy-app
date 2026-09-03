"""
Android Control Center — Main Entry Point
- Starts FastAPI backend on localhost:8412
- Opens pywebview desktop window (Windows) OR system browser (Linux)
- Cross-platform: Windows .exe and Linux binary
"""
import os
import sys
import threading
import time
import logging
import webbrowser
import platform
import subprocess

logging.basicConfig(level=logging.INFO, format='[ACC] %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"

# ── Resource Path Resolution ───────────────────────────────────────────────────
def resource_path(relative: str) -> str:
    """Resolve path for both dev mode and PyInstaller bundle."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), relative)

FRONTEND_DIST = resource_path('frontend_dist')
PORT = 8412

# ── FastAPI app ────────────────────────────────────────────────────────────────
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.routes import router
from services.downloader import start_download_if_needed

app = FastAPI(title="Android Control Center")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

logger.info(f"Checking frontend distribution at: {FRONTEND_DIST} (is_dir={os.path.isdir(FRONTEND_DIST)})")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
else:
    logger.error(f"Frontend dist NOT found at: {FRONTEND_DIST}")
    @app.get("/")
    def serve_fallback():
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            "<html><body style='background:#0a0d12;color:#e8edf5;font-family:sans-serif;padding:40px;'>"
            "<h2>Android Control Center — Server Running</h2>"
            f"<p style='color:#ef4444;'>Warning: Frontend static files not found at: {FRONTEND_DIST}</p>"
            "<p>API endpoints are active at <a style='color:#3b82f6;' href='/api/status'>/api/status</a></p>"
            "</body></html>"
        )


def run_server():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


def wait_for_server(timeout: int = 15) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/tools/progress", timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def open_browser(url: str):
    """Open system browser with multiple fallbacks for Linux."""
    # Try xdg-open first (works on all Linux desktops)
    if IS_LINUX:
        for cmd in ['xdg-open', 'sensible-browser', 'firefox', 'chromium-browser', 'chromium', 'google-chrome']:
            try:
                subprocess.Popen([cmd, url],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 start_new_session=True)
                logger.info(f"Opened browser using: {cmd}")
                return
            except FileNotFoundError:
                continue
    # Windows / Mac fallback
    webbrowser.open(url)


def setup_bundled_tools():
    """
    On Linux PyInstaller builds: extract the bundled ADB + scrcpy to the user
    data directory and mark them executable. This runs once and is instant.
    """
    if not IS_LINUX or not hasattr(sys, '_MEIPASS'):
        return  # Not a Linux PyInstaller build — skip

    import shutil, stat
    bundled = os.path.join(sys._MEIPASS, 'bundled_tools')
    if not os.path.isdir(bundled):
        logger.warning("bundled_tools not found in bundle — will fall back to download.")
        return

    from services.config import get_default_tools_dir, set_tools_dir
    tools_dir = get_default_tools_dir()
    os.makedirs(tools_dir, exist_ok=True)
    set_tools_dir(tools_dir)

    for fname in os.listdir(bundled):
        src = os.path.join(bundled, fname)
        dst = os.path.join(tools_dir, fname)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
        # Always ensure executables are marked +x
        if fname in ('adb', 'scrcpy'):
            st = os.stat(dst)
            os.chmod(dst, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    logger.info(f"Bundled tools ready at: {tools_dir}")


def main():
    # Step 0: On Linux, extract bundled ADB + scrcpy (instant, no download)
    setup_bundled_tools()

    # Step 1: Ensure tools directory is configured
    from services.config import get_tools_dir, set_tools_dir, get_default_tools_dir
    if not get_tools_dir():
        set_tools_dir(get_default_tools_dir())

    # Step 2: Download tools only if not already present (skipped on Linux with bundled tools)
    start_download_if_needed()

    # Start FastAPI server in background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    logger.info(f"Starting backend on port {PORT}...")
    if not wait_for_server():
        logger.error("Backend failed to start within timeout.")
        sys.exit(1)

    url = f"http://127.0.0.1:{PORT}"
    logger.info(f"App running at: {url}")

    if IS_LINUX:
        # On Linux: always open the system browser — no GTK dependency
        # pywebview requires libwebkit2gtk which may not be installed on Ubuntu
        logger.info("Linux detected — opening system browser (no GTK required).")
        open_browser(url)
        print(f"\n{'='*50}")
        print(f"  Android Control Center is running!")
        print(f"  Open your browser at: {url}")
        print(f"  Press Ctrl+C to quit.")
        print(f"{'='*50}\n")
        # Keep server alive until user presses Ctrl+C
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down.")
    else:
        # Windows: use native pywebview window
        try:
            import webview
            logger.info("Opening native desktop window via pywebview...")
            webview.create_window(
                title="Android Control Center",
                url=url,
                width=1060,
                height=720,
                min_size=(820, 580),
                resizable=True,
            )
            webview.start()
        except ImportError:
            logger.warning("pywebview not available, opening in system browser instead.")
            webbrowser.open(url)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
