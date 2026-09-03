#!/usr/bin/env python3
"""
Build script for Linux binary.
Run from the scrcpy-app root: python3 build/build_linux.py
No global installs needed — uses backend/.venv
"""
import os, sys, subprocess, shutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BACKEND  = os.path.join(ROOT, 'backend')
FRONTEND = os.path.join(ROOT, 'frontend')
DIST_DIR = os.path.join(ROOT, 'dist', 'linux')
FRONTEND_DIST = os.path.join(BACKEND, 'frontend_dist')
VENV_PY  = os.path.join(BACKEND, '.venv', 'bin', 'python3')

PY = VENV_PY if os.path.exists(VENV_PY) else sys.executable

def run(cmd, cwd=None):
    print(f'\n>  {" ".join(cmd) if isinstance(cmd, list) else cmd}')
    r = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str))
    if r.returncode != 0:
        print(f'❌  Command failed (exit {r.returncode})')
        sys.exit(r.returncode)

print('=' * 60)
print('  scrcpy-app - Linux Build')
print('=' * 60)

# 0. Create venv if it doesn't exist
venv_dir = os.path.join(BACKEND, '.venv')
if not os.path.exists(VENV_PY):
    if os.path.exists(venv_dir):
        print('\n[0/4] Removing invalid/cross-platform .venv folder...')
        shutil.rmtree(venv_dir, ignore_errors=True)
    print('\n[0/4] Creating Python .venv...')
    real_py = sys.executable
    run([real_py, '-m', 'venv', venv_dir])

# Update PY to point to the venv python now that it definitely exists
PY = VENV_PY

# 1. Install Python dependencies inside venv
print('\n[1/4] Installing Python dependencies into .venv...')
run([PY, '-m', 'pip', 'install', '-q', '--upgrade', 'pip', 'setuptools'], cwd=BACKEND)
run([PY, '-m', 'pip', 'install', '-q', '-r', 'requirements.txt'], cwd=BACKEND)
run([PY, '-m', 'pip', 'install', '-q', 'pyinstaller'], cwd=BACKEND)

# 2. Build React frontend
print('\n[2/4] Building React frontend...')
run('npm install', cwd=FRONTEND)
run('npm run build', cwd=FRONTEND)

if not os.path.isdir(FRONTEND_DIST):
    print('❌  Frontend build failed — frontend_dist missing')
    sys.exit(1)

# 3. PyInstaller bundle (Linux uses : as separator in --add-data)
print('\n[3/4] Bundling with PyInstaller...')
os.makedirs(DIST_DIR, exist_ok=True)

pyinstaller_cmd = [
    PY, '-m', 'PyInstaller',
    '--clean',
    '--onefile',
    '--name', 'scrcpy-app',
    '--distpath', DIST_DIR,
    '--workpath', os.path.join(ROOT, 'build', '_pyinstaller_tmp'),
    '--specpath', os.path.join(ROOT, 'build'),
    '--add-data', f'{FRONTEND_DIST}:frontend_dist',
    '--hidden-import', 'uvicorn.logging',
    '--hidden-import', 'uvicorn.loops',
    '--hidden-import', 'uvicorn.loops.auto',
    '--hidden-import', 'uvicorn.protocols',
    '--hidden-import', 'uvicorn.protocols.http',
    '--hidden-import', 'uvicorn.protocols.http.auto',
    '--hidden-import', 'uvicorn.protocols.websockets',
    '--hidden-import', 'uvicorn.protocols.websockets.auto',
    '--hidden-import', 'uvicorn.lifespan',
    '--hidden-import', 'uvicorn.lifespan.on',
    '--hidden-import', 'uvicorn.lifespan.off',
    '--hidden-import', 'fastapi',
    '--hidden-import', 'starlette',
    '--hidden-import', 'anyio._backends._asyncio',
    '--hidden-import', 'pkg_resources',
    '--collect-data', 'setuptools',
    # Exclude pywebview on Linux — we open system browser instead (no GTK required)
    '--exclude-module', 'webview',
    '--exclude-module', 'gi',
    '--exclude-module', 'gtk',
    'main.py',
]
run(pyinstaller_cmd, cwd=BACKEND)

# 4. Make executable
binary = os.path.join(DIST_DIR, 'scrcpy-app')
if os.path.exists(binary):
    os.chmod(binary, 0o755)
    size_mb = os.path.getsize(binary) / 1024 / 1024
    print(f'\n✅  Build successful!')
    print(f'   Output: {binary}')
    print(f'   Size:   {size_mb:.1f} MB')
    print(f'\n   To run:')
    print(f'   chmod +x {binary}')
    print(f'   {binary}')
    print(f'\n   On first launch it will auto-download ADB + scrcpy (~15MB).')
else:
    print('❌  Build failed — binary not found')
    sys.exit(1)
