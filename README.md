# Android Control Center — Standalone App

A self-contained desktop application for discovering, connecting, mirroring, and remotely controlling Android devices (Android 5 through latest).

**No installation required** — just run the executable. ADB and scrcpy download automatically on first launch.

---

## Features
- 🔍 Auto-detect USB and Wi-Fi connected Android devices
- 📱 Full screen mirror via native scrcpy window
- ⌨️ Remote PIN/Password keypad (bypasses FLAG_SECURE black screen)
- 🖱️ Physical keyboard → keypad (type 0-9, Backspace, Enter directly)
- 🔑 Android 11+ Wireless Debug pair code support
- 📡 Manual IP connect for any Wi-Fi/Hotspot network
- 🔋 Hardware controls: Power, Volume, Sleep, Wake, Unlock, Notifications
- 🤖 Android 5–15 compatibility with auto-tuned scrcpy quality settings

---

## Building

### Prerequisites
- Python 3.10+
- Node.js 18+ and npm

### Windows `.exe`
```
cd scrcpy-app
python build/build_windows.py
```
Output: `dist/windows/AndroidControlCenter.exe`

### Linux binary (Ubuntu)
```bash
cd scrcpy-app
python3 build/build_linux.py
```
Output: `dist/linux/AndroidControlCenter`

---

## Development (Run Without Building)

```bash
# 1. Start backend
cd backend
pip install -r requirements.txt
python main.py

# 2. Start frontend dev server (separate terminal)
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173 in your browser.

---

## Android Version Compatibility

| Android | Method | Notes |
|---------|--------|-------|
| 5.0–10  | USB → `adb tcpip 5555` → Wi-Fi | USB required for initial pairing |
| 11+     | Wireless Debugging pair code | No USB needed at first |
| All     | Manual IP input | Universal fallback |

**Audio mirroring requires Android 11+** (scrcpy limitation).

---

## How Tools Are Downloaded

On first launch, the app downloads into:
- **Windows**: `%APPDATA%\AndroidControlCenter\tools\`
- **Linux**: `~/.local/share/AndroidControlCenter/tools\`

Total download: ~15 MB (ADB platform-tools + scrcpy)
