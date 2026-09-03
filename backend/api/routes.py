"""
Android Control Center — FastAPI REST Endpoints
"""
from fastapi import APIRouter
from pydantic import BaseModel
from services.android_service import (
    get_devices, tools_status, forget_device,
    enable_wireless_legacy, pair_wireless_android11, connect_ip,
    launch_scrcpy, send_keyevent, send_text_as_keyevents, send_swipe, send_unlock
)
from services.downloader import get_progress, start_download_if_needed

router = APIRouter(prefix="/api")


# ── Tools & Status ────────────────────────────────────────────────────────────

@router.get("/status")
def api_status():
    tools = tools_status()
    devices = get_devices() if tools["adb_found"] else []
    return {"tools": tools, "devices": devices}

@router.get("/tools/status")
def api_tools_status():
    from services.config import get_tools_dir, are_tools_installed
    # get real status
    st = tools_status()
    st["tools_dir"] = get_tools_dir()
    st["installed"] = are_tools_installed()
    return st

@router.get("/tools/progress")
def api_download_progress():
    return get_progress()

@router.post("/tools/select-folder")
def api_tools_select_folder():
    from services.config import set_tools_dir, get_default_tools_dir
    import os
    import subprocess
    import logging
    logger = logging.getLogger(__name__)

    path = None
    try:
        import webview
        if webview.windows:
            result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
            if result and len(result) > 0:
                path = result[0]
    except Exception as e:
        logger.warning(f"webview folder dialog failed: {e}")

    # Fallback 1: Zenity (Ubuntu / GNOME default)
    if not path:
        try:
            res = subprocess.run(
                ["zenity", "--file-selection", "--directory", "--title=Select Installation Folder"],
                capture_output=True, text=True, timeout=30
            )
            if res.returncode == 0 and res.stdout.strip():
                path = res.stdout.strip()
        except Exception:
            pass

    # Fallback 2: Kdialog (KDE)
    if not path:
        try:
            res = subprocess.run(
                ["kdialog", "--getexistingdirectory", "."],
                capture_output=True, text=True, timeout=30
            )
            if res.returncode == 0 and res.stdout.strip():
                path = res.stdout.strip()
        except Exception:
            pass

    # Fallback 3: Tkinter dialog
    if not path:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            selected = filedialog.askdirectory(title="Select Installation Folder")
            root.destroy()
            if selected:
                path = selected
        except Exception:
            pass

    # Fallback 4: Automatically fall back to default user directory
    if not path:
        dpath = get_default_tools_dir()
        set_tools_dir(dpath)
        return {"path": dpath, "fallback": True}

    final_path = os.path.join(path, "scrcpy-app", "tools")
    set_tools_dir(final_path)
    return {"path": final_path, "fallback": False}

@router.post("/tools/use-default-folder")
def api_tools_use_default():
    from services.config import get_default_tools_dir, set_tools_dir
    dpath = get_default_tools_dir()
    set_tools_dir(dpath)
    return {"path": dpath}

@router.post("/tools/download")
def api_trigger_download():
    started = start_download_if_needed()
    return {"started": started, "message": "Download already complete." if not started else "Download started."}


# ── Device Connection ─────────────────────────────────────────────────────────

class EnableWirelessReq(BaseModel):
    serial: str

@router.post("/connect/wireless-legacy")
def api_enable_wireless(body: EnableWirelessReq):
    return enable_wireless_legacy(body.serial)


class PairCodeReq(BaseModel):
    ip_port: str   # e.g. "192.168.1.5:37123"
    code: str      # 6-digit code shown on phone

@router.post("/connect/pair-code")
def api_pair_code(body: PairCodeReq):
    return pair_wireless_android11(body.ip_port, body.code)


class ConnectIpReq(BaseModel):
    ip: str
    port: int = 5555

@router.post("/connect/ip")
def api_connect_ip(body: ConnectIpReq):
    return connect_ip(body.ip, body.port)


class ForgetReq(BaseModel):
    ip: str

@router.post("/connect/forget")
def api_forget(body: ForgetReq):
    return forget_device(body.ip)


# ── Mirror Launch ─────────────────────────────────────────────────────────────

class LaunchReq(BaseModel):
    serial: str
    title: str = "Android Mirror"
    turn_screen_off: bool = True
    stay_awake: bool = True
    api_level: int = 0

@router.post("/mirror/launch")
def api_launch(body: LaunchReq):
    return launch_scrcpy(
        serial=body.serial,
        title=body.title,
        turn_screen_off=body.turn_screen_off,
        stay_awake=body.stay_awake,
        api_level=body.api_level,
    )


# ── Remote Control ────────────────────────────────────────────────────────────

class KeyReq(BaseModel):
    serial: str
    keycode: int | str

@router.post("/input/key")
def api_key(body: KeyReq):
    return send_keyevent(body.serial, body.keycode)


class TextReq(BaseModel):
    serial: str
    text: str

@router.post("/input/text")
def api_text(body: TextReq):
    return send_text_as_keyevents(body.serial, body.text)


class SwipeReq(BaseModel):
    serial: str
    x1: int = 540; y1: int = 1900
    x2: int = 540; y2: int = 500
    ms: int = 300

@router.post("/input/swipe")
def api_swipe(body: SwipeReq):
    return send_swipe(body.serial, body.x1, body.y1, body.x2, body.y2, body.ms)

class UnlockReq(BaseModel):
    serial: str

@router.post("/input/unlock")
def api_unlock(body: UnlockReq):
    return send_unlock(body.serial)
