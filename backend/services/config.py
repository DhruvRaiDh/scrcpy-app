import os
import json
import platform

# Use APPDATA for persistent settings (same as android_service.py)
IS_WINDOWS = platform.system() == "Windows"
def _get_data_dir():
    if IS_WINDOWS:
        appdata = os.getenv('APPDATA', os.path.expanduser('~'))
        return os.path.join(appdata, 'scrcpy-app')
    return os.path.join(os.path.expanduser('~'), '.local', 'share', 'scrcpy-app')

DATA_DIR = _get_data_dir()
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')

def load_settings():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_settings(settings):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)

def get_default_tools_dir():
    return os.path.join(DATA_DIR, 'tools')

def get_tools_dir():
    settings = load_settings()
    custom = settings.get("tools_dir", "")
    if custom:
        return custom
    return get_default_tools_dir()

def set_tools_dir(path: str):
    settings = load_settings()
    settings["tools_dir"] = path
    save_settings(settings)

def are_tools_installed():
    from services.android_service import get_adb_exe, get_scrcpy_exe
    return bool(get_adb_exe() and get_scrcpy_exe())
