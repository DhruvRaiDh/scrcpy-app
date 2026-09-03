"""
Android Control Center — Auto-downloader for ADB + scrcpy
Downloads the correct binaries for Windows or Linux on first launch.
Reports progress via a shared state dict so the API can stream it.
"""
import os
import platform
import shutil
import threading
import urllib.request
import zipfile
import tarfile
import stat
import logging

from services.config import get_tools_dir

logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"

# Download URLs
PLATFORM_TOOLS_WIN_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
PLATFORM_TOOLS_LIN_URL = "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"

# scrcpy latest release — these will use GitHub API to get the latest version
SCRCPY_WIN_URL = "https://github.com/Genymobile/scrcpy/releases/download/v3.3.1/scrcpy-win64-v3.3.1.zip"
SCRCPY_LIN_URL = "https://github.com/Genymobile/scrcpy/releases/download/v3.3.1/scrcpy-linux-x86_64-v3.3.1.tar.gz"

# Shared download progress state
_progress = {
    "phase": "idle",       # idle | adb | scrcpy | done | error
    "percent": 0,
    "message": "",
    "error": "",
}
_lock = threading.Lock()

def get_progress() -> dict:
    with _lock:
        return dict(_progress)

def _set_progress(phase: str, percent: int, message: str, error: str = ""):
    with _lock:
        _progress["phase"]   = phase
        _progress["percent"] = percent
        _progress["message"] = message
        _progress["error"]   = error

def _download(url: str, dest: str, phase: str, start_pct: int, end_pct: int) -> bool:
    _set_progress(phase, start_pct, f"Starting {phase} download...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 AndroidControlCenter/1.0'})
        with urllib.request.urlopen(req) as response:
            total_size = int(response.getheader('Content-Length', 0))
            downloaded = 0
            with open(dest, 'wb') as out_file:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        ratio = min(downloaded / total_size, 1.0)
                        pct = int(start_pct + ratio * (end_pct - start_pct))
                        mb = downloaded / 1024 / 1024
                        total_mb = total_size / 1024 / 1024
                        _set_progress(phase, pct, f"Downloading {phase}... {mb:.1f} / {total_mb:.1f} MB")
        
        _set_progress(phase, end_pct, f"{phase} downloaded.")
        return True
    except Exception as e:
        _set_progress("error", 0, "", str(e))
        logger.error(f"Download failed for {phase}: {e}")
        return False

def _extract_zip(zip_path: str, extract_to: str):
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_to)

def _extract_tar(tar_path: str, extract_to: str):
    with tarfile.open(tar_path, 'r:gz') as t:
        t.extractall(extract_to)

def _make_executable(path: str):
    if os.path.exists(path):
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def download_tools():
    """
    Download ADB platform-tools and scrcpy for the current platform.
    This runs in a background thread. Poll get_progress() to check status.
    """
    tools_dir = get_tools_dir()
    if not tools_dir:
        _set_progress("error", 0, "", "No installation folder selected.")
        return

    os.makedirs(tools_dir, exist_ok=True)
    tmp = os.path.join(tools_dir, '_tmp')
    os.makedirs(tmp, exist_ok=True)

    try:
        # ── Step 1: ADB platform-tools ───────────────────────────────────────
        adb_name = 'adb.exe' if IS_WINDOWS else 'adb'
        adb_path = os.path.join(tools_dir, adb_name)

        if not os.path.exists(adb_path):
            url = PLATFORM_TOOLS_WIN_URL if IS_WINDOWS else PLATFORM_TOOLS_LIN_URL
            zip_dest = os.path.join(tmp, 'platform-tools.zip')
            if not _download(url, zip_dest, "ADB", 0, 35):
                return

            _set_progress("ADB", 36, "Extracting ADB platform-tools...")
            ext_dir = os.path.join(tmp, '_adb_extract')
            _extract_zip(zip_dest, ext_dir)

            # Files live inside platform-tools/ subfolder in the zip
            pt_dir = os.path.join(ext_dir, 'platform-tools')
            files_to_copy = ['adb.exe', 'adb', 'AdbWinApi.dll', 'AdbWinUsbApi.dll', 'libusb-1.0.so']
            for fname in files_to_copy:
                src = os.path.join(pt_dir, fname)
                if os.path.exists(src):
                    shutil.copy2(src, tools_dir)

            if IS_LINUX:
                _make_executable(adb_path)

            _set_progress("ADB", 40, "ADB ready.")
        else:
            _set_progress("ADB", 40, "ADB already present.")

        # ── Step 2: scrcpy ───────────────────────────────────────────────────
        scrcpy_name = 'scrcpy.exe' if IS_WINDOWS else 'scrcpy'
        scrcpy_path = os.path.join(tools_dir, scrcpy_name)

        if not os.path.exists(scrcpy_path):
            if IS_WINDOWS:
                url = SCRCPY_WIN_URL
                arc_dest = os.path.join(tmp, 'scrcpy.zip')
                if not _download(url, arc_dest, "scrcpy", 40, 85):
                    return
                _set_progress("scrcpy", 86, "Extracting scrcpy...")
                ext_dir = os.path.join(tmp, '_sc_extract')
                _extract_zip(arc_dest, ext_dir)
            else:
                url = SCRCPY_LIN_URL
                arc_dest = os.path.join(tmp, 'scrcpy.tar.gz')
                if not _download(url, arc_dest, "scrcpy", 40, 85):
                    return
                _set_progress("scrcpy", 86, "Extracting scrcpy...")
                ext_dir = os.path.join(tmp, '_sc_extract')
                os.makedirs(ext_dir, exist_ok=True)
                _extract_tar(arc_dest, ext_dir)

            # Copy all extracted files flat into tools_dir
            for root, dirs, files in os.walk(ext_dir):
                for fname in files:
                    shutil.copy2(os.path.join(root, fname), tools_dir)

            if IS_LINUX:
                _make_executable(scrcpy_path)

            _set_progress("scrcpy", 95, "scrcpy ready.")
        else:
            _set_progress("scrcpy", 95, "scrcpy already present.")

        # ── Cleanup ──────────────────────────────────────────────────────────
        shutil.rmtree(tmp, ignore_errors=True)
        _set_progress("done", 100, "All tools ready!")

    except Exception as e:
        _set_progress("error", 0, "", str(e))
        logger.error(f"Tool download failed: {e}")


def start_download_if_needed() -> bool:
    """
    Returns True if download was started, False if it was already in progress or tools exist.
    """
    from services.config import are_tools_installed
    if are_tools_installed():
        return False

    with _lock:
        if _progress["phase"] not in ("idle", "error", "done"):
            return True  # already downloading

    t = threading.Thread(target=download_tools, daemon=True)
    t.start()
    return True
