"""
Android Control Center — Core Service
Cross-platform ADB + scrcpy wrapper with:
- Android 5-15 compatibility
- Automatic Android version detection
- TCP/IP wireless (Android 5-10) + adb pair code (Android 11+)
- Persistent Wi-Fi device reconnection
- Per-version performance tuning for scrcpy
"""
import os
import re
import json
import subprocess
import logging
import sys
import shutil
import platform
from services.config import get_tools_dir, DATA_DIR

logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

PAIRED_FILE = os.path.join(DATA_DIR, 'paired_devices.json')

def get_adb_exe() -> str | None:
    name = 'adb.exe' if IS_WINDOWS else 'adb'
    # 1. Check bundled tools inside PyInstaller executable first
    if hasattr(sys, '_MEIPASS'):
        bundled = os.path.join(sys._MEIPASS, 'bundled_tools', name)
        if os.path.exists(bundled):
            return bundled
    # 2. Check user tools directory
    tdir = get_tools_dir()
    if tdir:
        cand = os.path.join(tdir, name)
        if os.path.exists(cand):
            return cand
    # 3. Check system PATH
    sys_path = shutil.which('adb')
    if sys_path:
        return sys_path
    # 4. Check local development tools directory
    local_cand = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'tools')), name)
    if os.path.exists(local_cand):
        return local_cand
    return None

def get_scrcpy_exe() -> str | None:
    name = 'scrcpy.exe' if IS_WINDOWS else 'scrcpy'
    # 1. Check bundled tools inside PyInstaller executable first
    if hasattr(sys, '_MEIPASS'):
        bundled = os.path.join(sys._MEIPASS, 'bundled_tools', name)
        if os.path.exists(bundled):
            return bundled
    # 2. Check user tools directory
    tdir = get_tools_dir()
    if tdir:
        cand = os.path.join(tdir, name)
        if os.path.exists(cand):
            return cand
    # 3. Check system PATH
    sys_path = shutil.which('scrcpy')
    if sys_path:
        return sys_path
    # 4. Check local development tools directory
    local_cand = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'tools')), name)
    if os.path.exists(local_cand):
        return local_cand
    return None

os.makedirs(DATA_DIR, exist_ok=True)
if get_tools_dir():
    try:
        os.makedirs(get_tools_dir(), exist_ok=True)
    except Exception:
        pass


# ─── Paired Device Persistence ────────────────────────────────────────────────

def _load_paired() -> list[dict]:
    if os.path.exists(PAIRED_FILE):
        try:
            with open(PAIRED_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def _save_paired(ip: str, model: str = ""):
    paired = _load_paired()
    clean_ip = ip.split(':')[0].strip()
    existing = next((d for d in paired if d.get('ip') == clean_ip), None)
    if existing:
        if model:
            existing['model'] = model
    else:
        paired.append({"ip": clean_ip, "model": model or "Android Device", "port": 5555})
    try:
        with open(PAIRED_FILE, 'w', encoding='utf-8') as f:
            json.dump(paired, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save paired device: {e}")

def forget_device(ip: str) -> dict:
    clean_ip = ip.split(':')[0].strip()
    paired = [d for d in _load_paired() if d.get('ip') != clean_ip]
    try:
        with open(PAIRED_FILE, 'w', encoding='utf-8') as f:
            json.dump(paired, f, indent=2)
        _adb('disconnect', f'{clean_ip}:5555', timeout=3)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── ADB Helpers ──────────────────────────────────────────────────────────────

def _adb(*args, serial: str = None, timeout: int = 5) -> tuple[bool, str]:
    """Run an adb command, return (success, combined_output)."""
    adb_path = get_adb_exe()
    if not adb_path:
        return False, "ADB not found. Tools not downloaded yet."
    cmd = [adb_path]
    if serial:
        cmd += ['-s', serial]
    cmd += list(args)
    try:
        kwargs = dict(capture_output=True, text=True, timeout=timeout)
        if IS_WINDOWS:
            kwargs['creationflags'] = CREATE_NO_WINDOW
        r = subprocess.run(cmd, **kwargs)
        return True, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "ADB timed out."
    except Exception as e:
        return False, str(e)


# ─── Android Version Detection ────────────────────────────────────────────────

def get_android_api(serial: str) -> int:
    """Return Android API level as int (e.g. 21 = Android 5.0). Returns 0 on failure."""
    ok, out = _adb('shell', 'getprop', 'ro.build.version.sdk', serial=serial, timeout=3)
    if ok:
        m = re.search(r'(\d+)', out)
        if m:
            return int(m.group(1))
    return 0


# ─── Device Discovery ─────────────────────────────────────────────────────────

def get_devices() -> list[dict]:
    """List all connected ADB devices, auto-reconnect known Wi-Fi devices."""
    paired_list = _load_paired()

    ok, output = _adb('devices', '-l', timeout=3)
    if not ok:
        return []

    # Auto-reconnect saved Wi-Fi devices not currently in the list
    for saved in paired_list:
        target = f"{saved['ip']}:{saved.get('port', 5555)}"
        if target not in output:
            _adb('connect', target, timeout=2)

    # Re-fetch after reconnect attempts
    if paired_list:
        ok, output = _adb('devices', '-l', timeout=3)
        if not ok:
            return []

    devices = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith('List of') or line.startswith('*'):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        state  = parts[1]

        # Extract model from adb output
        model = ""
        m = re.search(r'model:(\S+)', line)
        if m:
            model = m.group(1).replace('_', ' ')
        else:
            p = re.search(r'product:(\S+)', line)
            if p:
                model = p.group(1).replace('_', ' ')
            elif state == "device":
                model = "Android Device"

        is_wifi = ":" in serial

        # Detect Android API level for connected devices
        api_level = 0
        if state == "device":
            api_level = get_android_api(serial)

        if is_wifi and state == "device":
            _save_paired(serial.split(':')[0], model)

        devices.append({
            "serial":    serial,
            "state":     state,
            "model":     model,
            "is_wifi":   is_wifi,
            "is_usb":    not is_wifi,
            "api_level": api_level,
            # Android 11+ (API 30+) supports wireless debugging pair code
            "supports_wireless_debug": api_level >= 30,
        })
    return devices


def tools_status() -> dict:
    tdir = get_tools_dir()
    adb_path = get_adb_exe()
    scrcpy_path = get_scrcpy_exe()
    return {
        "adb_found":    bool(adb_path),
        "scrcpy_found": bool(scrcpy_path),
        "tools_dir":    tdir,
        "data_dir":     DATA_DIR,
    }


# ─── Wireless Pairing & Connection ────────────────────────────────────────────

def _get_device_ips(serial: str) -> list[str]:
    _, out = _adb('shell', 'ip', '-f', 'inet', 'addr', 'show', serial=serial, timeout=4)
    ips = []
    for line in out.splitlines():
        line = line.strip()
        if 'inet ' in line and '127.0.0.1' not in line:
            m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', line)
            if m:
                ip = m.group(1)
                if ip not in ips:
                    ips.append(ip)
    return ips


def enable_wireless_legacy(serial: str) -> dict:
    """Classic tcpip 5555 method — works on ALL Android versions (requires USB first)."""
    ok, out = _adb('tcpip', '5555', serial=serial, timeout=5)
    if not ok:
        return {"success": False, "error": f"Failed to enable TCP/IP: {out}"}

    ips = _get_device_ips(serial)
    if not ips:
        return {"success": False, "error": "Could not detect device IP. Ensure phone is on Wi-Fi/Hotspot."}

    import time; time.sleep(1.5)

    for ip in ips:
        ok2, out2 = _adb('connect', f'{ip}:5555', timeout=6)
        if 'connected to' in out2.lower():
            _save_paired(ip)
            return {"success": True, "wifi_serial": f"{ip}:5555", "ip": ip, "error": None}

    return {"success": False, "error": f"Could not connect to {ips}. Check same Wi-Fi/Hotspot network."}


def pair_wireless_android11(ip_port: str, code: str) -> dict:
    """Android 11+ wireless debugging pair using pair code shown on the phone."""
    ok, out = _adb('pair', ip_port, code, timeout=15)
    if 'successfully paired' in out.lower() or 'paired' in out.lower():
        ip = ip_port.split(':')[0]
        # After pairing, connect on port 5555
        connect_ok, connect_out = _adb('connect', f'{ip}:5555', timeout=8)
        connected = 'connected to' in connect_out.lower()
        if connected:
            _save_paired(ip)
        return {"success": True, "connected": connected, "ip": ip}
    return {"success": False, "error": out or "Pairing failed. Check the code and IP:port on your phone."}


def connect_ip(ip: str, port: int = 5555) -> dict:
    """Manually connect to a device by IP address."""
    clean_ip = ip.strip().split(':')[0]
    target = f"{clean_ip}:{port}"
    ok, out = _adb('connect', target, timeout=8)
    connected = 'connected to' in out.lower()
    if connected:
        _save_paired(clean_ip)
    return {
        "success": connected,
        "wifi_serial": target if connected else None,
        "error": None if connected else out,
    }


# ─── scrcpy Launcher ──────────────────────────────────────────────────────────

def _scrcpy_flags_for_api(api_level: int, is_wifi: bool) -> list[str]:
    """Return optimized scrcpy flags based on Android API level and connection type."""
    flags = []
    if api_level >= 30:             # Android 11+: full quality
        if is_wifi:
            flags += ['--max-size=1600', '--video-bit-rate=6M', '--max-fps=60', '--audio-buffer=40']
    elif api_level >= 26:           # Android 8-10: mid quality
        if is_wifi:
            flags += ['--max-size=1280', '--video-bit-rate=4M', '--max-fps=30']
        else:
            flags += ['--max-size=1280']
    elif api_level >= 21:           # Android 5-7: low quality (older hardware)
        flags += ['--max-size=800', '--video-bit-rate=2M', '--max-fps=30']
        flags += ['--no-audio']     # Audio needs Android 11+
    return flags


def launch_scrcpy(serial: str, title: str = "Android Mirror",
                  turn_screen_off: bool = True, stay_awake: bool = True,
                  api_level: int = 0) -> dict:
    scrcpy_path = get_scrcpy_exe()
    if not scrcpy_path:
        return {"success": False, "error": "scrcpy not found. Please wait for tools to download."}

    is_wifi = ":" in serial
    cmd = [scrcpy_path, '-s', serial, f'--window-title={title}']
    if stay_awake:
        cmd.append('--stay-awake')
    if turn_screen_off:
        cmd.append('--turn-screen-off')

    cmd += _scrcpy_flags_for_api(api_level, is_wifi)

    try:
        kwargs = {}
        tdir = get_tools_dir()
        if tdir and os.path.exists(tdir):
            kwargs["cwd"] = tdir
        if IS_WINDOWS:
            proc = subprocess.Popen(cmd, **kwargs)
        else:
            # On Linux, detach from process group so closing the UI doesn't kill mirror
            proc = subprocess.Popen(cmd, start_new_session=True, **kwargs)
        return {"success": True, "pid": proc.pid}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Remote Input ─────────────────────────────────────────────────────────────

# Map of printable ASCII chars to ADB keycodes for character-by-character injection
_CHAR_KEYCODE_MAP = {
    'a':29,'b':30,'c':31,'d':32,'e':33,'f':34,'g':35,'h':36,'i':37,'j':38,
    'k':39,'l':40,'m':41,'n':42,'o':43,'p':44,'q':45,'r':46,'s':47,'t':48,
    'u':49,'v':50,'w':51,'x':52,'y':53,'z':54,
    '0':7,'1':8,'2':9,'3':10,'4':11,'5':12,'6':13,'7':14,'8':15,'9':16,
    ' ':62, '\n':66, '.':56, ',':55, '-':69, '_':69,
    '@':77, '#':18, '$':72, '!':33,
}

def send_keyevent(serial: str, keycode) -> dict:
    ok, out = _adb('shell', 'input', 'keyevent', str(keycode), serial=serial, timeout=2)
    return {"ok": ok, "output": out}

def send_text_as_keyevents(serial: str, text: str) -> dict:
    """
    Send text character-by-character as hardware keyevents.
    This bypasses Android's FLAG_SECURE text blocking on password fields.
    Works on all Android versions.
    """
    results = []
    for char in text:
        lower = char.lower()
        if lower in _CHAR_KEYCODE_MAP:
            keycode = _CHAR_KEYCODE_MAP[lower]
            is_upper = char.isupper() and char.isalpha()
            if is_upper:
                _adb('shell', 'input', 'keyevent', '--longpress', '59', serial=serial, timeout=1)
                _adb('shell', 'input', 'keyevent', str(keycode), serial=serial, timeout=1)
                _adb('shell', 'input', 'keyevent', '--longpress', '59', serial=serial, timeout=1)
            else:
                ok, out = _adb('shell', 'input', 'keyevent', str(keycode), serial=serial, timeout=1)
                results.append(ok)
        # For chars not in map, skip silently (special chars, unicode, etc.)
    return {"ok": all(results) if results else True}

def send_swipe(serial: str, x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> dict:
    ok, out = _adb('shell', 'input', 'swipe', str(x1), str(y1), str(x2), str(y2), str(ms), serial=serial, timeout=3)
    return {"ok": ok, "output": out}

def send_unlock(serial: str) -> dict:
    return send_swipe(serial, 540, 1900, 540, 500, 300)
