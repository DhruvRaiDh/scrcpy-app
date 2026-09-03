"""
Android Control Center — Main Entry Point
- Starts FastAPI backend on localhost:8412
- Opens pywebview desktop window with the React UI
- Cross-platform: Windows .exe and Linux binary
"""
import os
import sys
import threading
import time
import logging
import webbrowser
import platform

logging.basicConfig(level=logging.INFO, format='[ACC] %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"

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

# Serve the React static build if it exists (production mode)
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


def run_server():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


def wait_for_server(timeout: int = 10) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/tools/progress", timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    # On first launch, ensure tools directory is set to the default location
    # This allows auto-download to begin immediately without user interaction
    from services.config import get_tools_dir, set_tools_dir, get_default_tools_dir
    if not get_tools_dir():
        set_tools_dir(get_default_tools_dir())

    # Start auto-download of tools if missing
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

    # Try to open pywebview (native window), fall back to browser
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
        # Keep server alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
