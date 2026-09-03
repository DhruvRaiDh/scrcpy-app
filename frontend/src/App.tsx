import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Smartphone, RefreshCw, Wifi, Usb, AlertCircle, CheckCircle2,
  Loader2, Cast, Plug, Radio, ArrowLeft, Home, Square,
  Power, Volume2, Volume1, VolumeX, Moon, Sun, Bell,
  Settings, Unlock, Delete, CornerDownLeft, Send, Download,
  X, KeyRound, FolderOpen,
} from 'lucide-react';
import { get, post } from './lib/api';

// ── Types ─────────────────────────────────────────────────────────────────────
interface Device {
  serial: string; state: string; model: string;
  is_wifi: boolean; is_usb: boolean;
  api_level: number; supports_wireless_debug: boolean;
}
interface ToolsStatus { adb_found: boolean; scrcpy_found: boolean; tools_dir: string; installed: boolean; }
interface StatusResp { tools: ToolsStatus; devices: Device[]; }
interface DownloadProgress { phase: string; percent: number; message: string; error: string; }

// ── Pair Code Modal ────────────────────────────────────────────────────────────
function PairCodeModal({
  onClose, onPaired,
}: { onClose: () => void; onPaired: () => void }) {
  const [ipPort, setIpPort] = useState('');
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');

  const doPair = async () => {
    if (!ipPort.trim() || !code.trim()) return;
    setLoading(true); setErr('');
    try {
      const r = await post<any>('/connect/pair-code', { ip_port: ipPort.trim(), code: code.trim() });
      if (r.success) { onPaired(); onClose(); }
      else setErr(r.error || 'Pairing failed.');
    } catch (e: any) { setErr(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="flex-row" style={{ marginBottom: 6 }}>
          <KeyRound size={18} color="var(--purple)" />
          <span className="modal__title">Wireless Pair (Android 11+)</span>
        </div>
        <p className="modal__desc">
          On your phone: <strong>Settings → Developer Options → Wireless Debugging → Pair device with pairing code</strong>.
          Enter the <strong>IP address:port</strong> and <strong>6-digit code</strong> shown on your phone.
        </p>
        <div style={{ marginBottom: 10 }}>
          <div className="modal__label">IP Address : Port (shown on phone)</div>
          <input className="input" placeholder="e.g. 192.168.1.5:37256"
            value={ipPort} onChange={e => setIpPort(e.target.value)} />
        </div>
        <div>
          <div className="modal__label">6-Digit Pairing Code</div>
          <input className="input" placeholder="e.g. 123456" maxLength={8}
            value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
            onKeyDown={e => e.key === 'Enter' && doPair()} />
        </div>
        {err && <div className="error-alert" style={{ marginTop: 10 }}><AlertCircle size={14} />{err}</div>}
        <div className="modal__actions">
          <button className="btn btn-secondary btn-sm" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary btn-sm" onClick={doPair} disabled={loading || !ipPort || !code}>
            {loading ? <Loader2 size={13} className="spin" /> : <KeyRound size={13} />} Pair Device
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Download Screen ────────────────────────────────────────────────────────────
function DownloadScreen({ progress }: { progress: DownloadProgress }) {
  return (
    <div className="download-screen">
      <Download size={52} className="download-screen__icon" />
      <div className="download-screen__title">Setting Up Android Tools</div>
      <div className="download-screen__msg">{progress.message || 'Initializing...'}</div>
      <div className="download-screen__bar-wrap">
        <div className="download-screen__bar" style={{ width: `${progress.percent}%` }} />
      </div>
      <div className="hint">{progress.percent}% complete — ADB + scrcpy</div>
      {progress.error && <div className="error-alert"><AlertCircle size={14} />{progress.error}</div>}
    </div>
  );
}

// ── App ────────────────────────────────────────────────────────────────────────
export default function App() {
  const [status, setStatus] = useState<StatusResp | null>(null);
  const [scanning, setScanning] = useState(true);
  const [error, setError] = useState('');
  const [selectedSerial, setSelectedSerial] = useState('');
  const [launchingSerial, setLaunchingSerial] = useState<string | null>(null);
  const [pairingSerial, setPairingSerial] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [turnScreenOff, setTurnScreenOff] = useState(true);
  const [showPairModal, setShowPairModal] = useState(false);
  const [manualIp, setManualIp] = useState('');
  const [connectingIp, setConnectingIp] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState<DownloadProgress | null>(null);
  const [pinBuffer, setPinBuffer] = useState<string[]>([]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [customText, setCustomText] = useState('');
  const rightPanelRef = useRef<HTMLDivElement>(null);

  const [needsFolderSetup, setNeedsFolderSetup] = useState(false);

  // ── Poll download progress if tools missing ──────────────────────────────────
  useEffect(() => {
    let timer: ReturnType<typeof setInterval>;
    const checkDownload = async () => {
      try {
        const prog = await get<DownloadProgress>('/tools/progress');
        if (prog.phase === 'idle') {
          // nothing yet
        } else if (prog.phase === 'done') {
          setDownloadProgress(null);
          clearInterval(timer);
          scan();
        } else if (prog.phase === 'error') {
          setDownloadProgress(prog);
        } else {
          setDownloadProgress(prog);
        }
      } catch { /* backend not ready yet */ }
    };

    // On startup: tools are bundled on Linux — no folder picker needed ever
    const init = async () => {
      try {
        const s = await get<ToolsStatus>('/tools/status');
        if (!s.installed) {
          // Auto-download (handles both bundled-tools copy and actual internet download)
          await post('/tools/use-default-folder', {});
          await post('/tools/download', {});
        } else {
          const sFull = await get<StatusResp>('/status');
          setStatus(sFull);
          autoSelectDevice(sFull.devices);
          setScanning(false);
        }
      } catch {
        setTimeout(init, 800);
      }
    };
    init();

    timer = setInterval(checkDownload, 800);
    return () => clearInterval(timer);
  }, []);

  const handleSelectFolder = async () => {
      try {
          const r = await post<{path: string}>('/tools/select-folder', {});
          if (r.path) {
              // Now trigger download
              setNeedsFolderSetup(false);
              await post('/tools/download', {});
          }
      } catch (e: any) {
          setError(e.message || "Failed to select folder");
      }
  };

  const handleUseDefaultFolder = async () => {
      try {
          const r = await post<{path: string}>('/tools/use-default-folder', {});
          if (r.path) {
              setNeedsFolderSetup(false);
              await post('/tools/download', {});
          }
      } catch (e: any) {
          setError(e.message || "Failed to set default folder");
      }
  };

  const autoSelectDevice = (devices: Device[]) => {
    const ready = devices.filter(d => d.state === 'device');
    if (ready.length > 0) setSelectedSerial(prev =>
      ready.some(d => d.serial === prev) ? prev : ready[0].serial
    );
  };

  const scan = useCallback(async () => {
    setScanning(true); setError('');
    try {
      const data = await get<StatusResp>('/status');
      setStatus(data);
      autoSelectDevice(data.devices);
    } catch (e: any) { setError(e.message || 'Could not reach backend'); }
    finally { setScanning(false); }
  }, []);

  // ── Device actions ───────────────────────────────────────────────────────────
  const handleLaunchMirror = async (device: Device) => {
    setLaunchingSerial(device.serial); setError('');
    try {
      const r = await post<any>('/mirror/launch', {
        serial: device.serial,
        title: `Mirror — ${device.model || device.serial}`,
        turn_screen_off: turnScreenOff,
        stay_awake: true,
        api_level: device.api_level,
      });
      if (!r.success) setError(r.error || 'Failed to launch mirror');
    } catch (e: any) { setError(e.message); }
    finally { setTimeout(() => setLaunchingSerial(null), 1200); }
  };

  const handleEnableWireless = async (device: Device) => {
    setPairingSerial(device.serial); setError('');
    try {
      const r = await post<any>('/connect/wireless-legacy', { serial: device.serial });
      if (r.success) scan();
      else setError(r.error || 'Wireless pairing failed');
    } catch (e: any) { setError(e.message); }
    finally { setPairingSerial(null); }
  };

  const handleConnectIp = async () => {
    if (!manualIp.trim()) return;
    setConnectingIp(true); setError('');
    try {
      const r = await post<any>('/connect/ip', { ip: manualIp.trim() });
      if (r.success) { setManualIp(''); scan(); }
      else setError(r.error || `Could not connect to ${manualIp}`);
    } catch (e: any) { setError(e.message); }
    finally { setConnectingIp(false); }
  };

  // ── Remote Input ─────────────────────────────────────────────────────────────
  const currentDevice = status?.devices.find(d => d.serial === selectedSerial && d.state === 'device');

  const flashKey = (label: string) => {
    setActiveKey(label);
    setTimeout(() => setActiveKey(null), 150);
  };

  const sendKey = async (keycode: number | string, label: string) => {
    if (!currentDevice) return;
    flashKey(label);
    setActionLoading(label);
    try {
      await post('/input/key', { serial: currentDevice.serial, keycode });
    } catch { }
    finally { setTimeout(() => setActionLoading(null), 200); }
  };

  const sendDigit = (digit: string, keycode: number) => {
    setPinBuffer(prev => [...prev, digit]);
    sendKey(keycode, digit);
  };

  const sendDelete = () => {
    setPinBuffer(prev => prev.slice(0, -1));
    sendKey(67, 'del');
  };

  const sendEnter = () => {
    setPinBuffer([]);
    sendKey(66, 'enter');
  };

  const sendText = async () => {
    if (!currentDevice || !customText.trim()) return;
    try {
      await post('/input/text', { serial: currentDevice.serial, text: customText });
      setCustomText('');
    } catch { }
  };

  // ── Physical Keyboard → Keypad Mapping ───────────────────────────────────────
  useEffect(() => {
    const DIGIT_MAP: Record<string, { keycode: number; digit: string }> = {
      '0': { keycode: 7,  digit: '0' },
      '1': { keycode: 8,  digit: '1' },
      '2': { keycode: 9,  digit: '2' },
      '3': { keycode: 10, digit: '3' },
      '4': { keycode: 11, digit: '4' },
      '5': { keycode: 12, digit: '5' },
      '6': { keycode: 13, digit: '6' },
      '7': { keycode: 14, digit: '7' },
      '8': { keycode: 15, digit: '8' },
      '9': { keycode: 16, digit: '9' },
    };

    const handler = (e: KeyboardEvent) => {
      // Don't capture when user is typing in an input
      if ((e.target as HTMLElement).tagName === 'INPUT') return;
      if (!currentDevice) return;

      if (DIGIT_MAP[e.key]) {
        const { keycode, digit } = DIGIT_MAP[e.key];
        sendDigit(digit, keycode);
      } else if (e.key === 'Backspace') {
        sendDelete();
      } else if (e.key === 'Enter') {
        sendEnter();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [currentDevice]);

  // ── Derived ──────────────────────────────────────────────────────────────────
  const connectedDevices = status?.devices.filter(d => d.state === 'device') ?? [];
  const unauthorizedDevices = status?.devices.filter(d => d.state === 'unauthorized') ?? [];

  // ── Show Folder Selection Screen ──────────────────────────────────────────────
  if (needsFolderSetup) {
      return (
        <div className="app">
          <div className="titlebar">
            <div className="titlebar__logo">
              <Smartphone size={18} />
              <span>scrcpy</span>
            </div>
          </div>
          <div className="download-screen">
            <FolderOpen size={52} className="download-screen__icon" style={{color: 'var(--blue)'}} />
            <div className="download-screen__title">Select Installation Folder</div>
            <div className="download-screen__msg" style={{ maxWidth: 400, textAlign: 'center', marginBottom: 20 }}>
              To connect to and mirror your Android device, we need to download <strong>ADB</strong> and <strong>scrcpy</strong> (~15MB). <br/><br/>
              Please choose where you would like to store these tools.
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
              <button className="btn btn-primary" onClick={handleSelectFolder} style={{ padding: '10px 20px', fontSize: 14 }}>
                 <FolderOpen size={16} /> Browse / Select Folder...
              </button>
              <button className="btn btn-secondary" onClick={handleUseDefaultFolder} style={{ padding: '10px 20px', fontSize: 14 }}>
                 Use Default Location
              </button>
            </div>
            {error && <div className="error-alert" style={{marginTop: 20}}><AlertCircle size={14} />{error}</div>}
          </div>
        </div>
      );
  }

  // ── Show download screen ──────────────────────────────────────────────────────
  if (downloadProgress && downloadProgress.phase !== 'done' && downloadProgress.phase !== 'idle') {
    return (
      <div className="app">
        <div className="titlebar">
          <div className="titlebar__logo">
            <Smartphone size={18} />
            <span>scrcpy</span>
            <span className="titlebar__version">v1.0</span>
          </div>
        </div>
        <DownloadScreen progress={downloadProgress} />
      </div>
    );
  }

  return (
    <div className="app">
      {/* ── Titlebar ── */}
      <div className="titlebar">
        <div className="titlebar__logo">
          <Smartphone size={18} />
          <span>scrcpy</span>
          <span className="titlebar__version">v1.0</span>
        </div>
        <div className="titlebar__spacer" />
        {status && (
          <>
            <div className={`titlebar__pill ${status.tools.adb_found ? 'ok' : 'err'}`}>
              {status.tools.adb_found ? <CheckCircle2 size={11}/> : <AlertCircle size={11}/>} ADB
            </div>
            <div className={`titlebar__pill ${status.tools.scrcpy_found ? 'ok' : 'err'}`}>
              {status.tools.scrcpy_found ? <CheckCircle2 size={11}/> : <AlertCircle size={11}/>} scrcpy
            </div>
          </>
        )}
        <button className="btn btn-secondary btn-sm btn-icon" onClick={scan} disabled={scanning} title="Refresh devices">
          {scanning ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
        </button>
      </div>

      <div className="split">
        {/* ════════════════════════════════════════════════════════
            LEFT PANEL — Connection Manager
        ════════════════════════════════════════════════════════ */}
        <div className="left-panel">
          {error && (
            <div className="error-alert">
              <AlertCircle size={14} style={{ flexShrink: 0 }} />
              <span>{error}</span>
              <button style={{ marginLeft:'auto', background:'none', border:'none', cursor:'pointer', color:'inherit' }}
                onClick={() => setError('')}><X size={13}/></button>
            </div>
          )}

          {/* Sleep Mode Toggle */}
          <div className="card">
            <div className="toggle-row">
              <label className="toggle" htmlFor="sleep-toggle">
                <input id="sleep-toggle" type="checkbox" checked={turnScreenOff}
                  onChange={e => setTurnScreenOff(e.target.checked)} />
                <div className="toggle__track" />
                <div className="toggle__thumb" />
              </label>
              <div>
                <div className="flex-row gap-4">
                  <Moon size={13} color="var(--purple)" />
                  <label htmlFor="sleep-toggle" style={{ cursor: 'pointer', fontSize: 13, fontWeight: 500 }}>
                    Turn off phone screen while mirroring
                  </label>
                </div>
                <div className="hint" style={{ marginTop: 2 }}>Saves battery — press Alt+O in mirror window to toggle</div>
              </div>
            </div>
          </div>

          {/* Connected Devices */}
          {connectedDevices.length > 0 && (
            <div className="card">
              <div className="card__title">Available Devices ({connectedDevices.length})</div>
              <div className="flex-col gap-6">
                {connectedDevices.map(d => {
                  const isActive = d.serial === selectedSerial;
                  return (
                    <div key={d.serial} className={`device-card ${isActive ? 'active' : ''}`}
                      onClick={() => setSelectedSerial(d.serial)}>
                      <div className="device-card__icon">
                        {d.is_wifi
                          ? <Wifi size={22} color="var(--blue)" />
                          : <Usb size={22} color="var(--accent)" />}
                      </div>
                      <div className="device-card__info">
                        <div className="device-card__model">{d.model || 'Android Device'}</div>
                        <div className="device-card__serial">{d.serial}</div>
                        <div className="device-card__badges">
                          <span className={`badge ${d.is_wifi ? 'wifi' : 'usb'}`}>
                            {d.is_wifi ? 'Wi-Fi' : 'USB'}
                          </span>
                          {d.api_level > 0 && (
                            <span className="badge api">
                              Android {d.api_level >= 35 ? '15' : d.api_level >= 34 ? '14' : d.api_level >= 33 ? '13' : d.api_level >= 31 ? '12' : d.api_level >= 30 ? '11' : d.api_level >= 28 ? '9' : d.api_level >= 26 ? '8' : d.api_level >= 23 ? '6' : d.api_level >= 21 ? '5' : '?'} (API {d.api_level})
                            </span>
                          )}
                          {isActive && <span className="badge ctrl">CONTROLLED</span>}
                        </div>
                      </div>
                      <div className="flex-col" style={{ gap: 6 }} onClick={e => e.stopPropagation()}>
                        <button className="btn btn-primary btn-sm"
                          onClick={() => handleLaunchMirror(d)}
                          disabled={launchingSerial === d.serial}
                          title="Open full mirror window">
                          {launchingSerial === d.serial
                            ? <Loader2 size={12} className="spin"/>
                            : d.is_wifi ? <Cast size={12}/> : <Plug size={12}/>}
                          Mirror
                        </button>
                        {d.is_usb && (
                          <>
                            <button className="btn btn-blue btn-sm"
                              onClick={() => handleEnableWireless(d)}
                              disabled={pairingSerial === d.serial}>
                              {pairingSerial === d.serial
                                ? <Loader2 size={12} className="spin"/>
                                : <Radio size={12}/>}
                              → Wi-Fi
                            </button>
                            {d.supports_wireless_debug && (
                              <button className="btn btn-sm"
                                style={{ background:'rgba(139,92,246,0.12)', borderColor:'rgba(139,92,246,0.35)', color:'var(--purple)' }}
                                onClick={() => setShowPairModal(true)}>
                                <KeyRound size={12}/> Pair Code
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Unauthorized devices */}
          {unauthorizedDevices.length > 0 && (
            <div className="card">
              <div className="card__title" style={{ color: 'var(--orange)' }}>Authorization Required</div>
              {unauthorizedDevices.map(d => (
                <div key={d.serial} className="flex-row" style={{ marginBottom: 6 }}>
                  <AlertCircle size={14} color="var(--orange)" />
                  <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{d.serial}</span>
                  <span className="badge unauth">ALLOW USB DEBUGGING</span>
                </div>
              ))}
              <div className="hint">Tap "Allow" on your phone's USB debugging prompt, then refresh.</div>
            </div>
          )}

          {/* No devices */}
          {!scanning && connectedDevices.length === 0 && unauthorizedDevices.length === 0 && (
            <div className="card">
              <div className="empty-state">
                <Smartphone size={44} className="empty-state__icon" />
                <h3>Connect Your Android Phone</h3>
                <p>Choose USB or Wireless to get started:</p>
                <ol>
                  <li>Enable <strong>Developer Options</strong> on your phone</li>
                  <li>Turn on <strong>USB Debugging</strong></li>
                  <li>Plug in via USB cable or enter phone IP below</li>
                  <li>Tap <strong>Allow</strong> when prompted on your phone</li>
                </ol>
              </div>
            </div>
          )}

          {/* Manual IP Connect */}
          <div className="card">
            <div className="card__title" style={{ display:'flex', alignItems:'center', gap:6 }}>
              <Wifi size={12} color="var(--blue)" /> Direct Wi-Fi / Hotspot Connect
            </div>
            <div className="input-row">
              <input className="input" placeholder="Phone IP  (e.g. 192.168.29.82 or 192.168.43.1)"
                value={manualIp} onChange={e => setManualIp(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleConnectIp()} />
              <button className="btn btn-primary btn-sm"
                onClick={handleConnectIp} disabled={!manualIp.trim() || connectingIp}>
                {connectingIp ? <Loader2 size={13} className="spin"/> : null}
                Connect
              </button>
            </div>
            <div className="hint mt-2">
              For Android 11+: also try the <strong>Pair Code</strong> button on a USB-connected device.
            </div>
          </div>
        </div>

        {/* ════════════════════════════════════════════════════════
            RIGHT PANEL — Remote Control Deck
        ════════════════════════════════════════════════════════ */}
        <div className="right-panel" ref={rightPanelRef}>
          {/* Header */}
          <div className="card remote-header">
            <div className="flex-row">
              <Smartphone size={16} color="var(--accent)" />
              <span className="remote-header__device">
                {currentDevice
                  ? `${currentDevice.model || 'Device'} · ${currentDevice.is_wifi ? 'Wi-Fi' : 'USB'}`
                  : 'No Device Selected'}
              </span>
            </div>
            <span className={`live-dot ${currentDevice ? '' : 'off'}`}>
              {currentDevice ? '● READY' : '● OFFLINE'}
            </span>
          </div>

          {/* Navigation Bar */}
          <div className="card">
            <div className="card__title">Navigation Bar</div>
            <div className="nav-grid">
              <button className="nav-btn" onClick={() => sendKey(4, 'back')} disabled={!currentDevice} title="Back">
                <ArrowLeft size={18} /><span>Back</span>
              </button>
              <button className="nav-btn" onClick={() => sendKey(3, 'home')} disabled={!currentDevice} title="Home">
                <Home size={18} /><span>Home</span>
              </button>
              <button className="nav-btn" onClick={() => sendKey(187, 'tabs')} disabled={!currentDevice} title="Recents">
                <Square size={18} /><span>Recents</span>
              </button>
            </div>
          </div>

          {/* PIN & Password Keypad */}
          <div className="card">
            <div className="flex-row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
              <div className="card__title" style={{ margin: 0 }}>PIN & Password Keypad</div>
              <span className="tag-green" style={{ fontSize: 10 }}>Bypasses secure screen</span>
            </div>

            {/* PIN Display */}
            <div className="pin-display">
              {pinBuffer.length === 0
                ? <span style={{ color: 'var(--text-3)', fontSize: 14, letterSpacing: 0 }}>tap keys or type on keyboard</span>
                : pinBuffer.map((_, i) => <span key={i}>●</span>)}
            </div>

            {/* Keypad grid */}
            <div className="keypad-grid">
              {[
                { label: '1', kc: 8 }, { label: '2', kc: 9 },  { label: '3', kc: 10 },
                { label: '4', kc: 11 },{ label: '5', kc: 12 }, { label: '6', kc: 13 },
                { label: '7', kc: 14 },{ label: '8', kc: 15 }, { label: '9', kc: 16 },
              ].map(b => (
                <button key={b.label}
                  className={`keypad-btn ${activeKey === b.label ? 'active-press' : ''}`}
                  onClick={() => sendDigit(b.label, b.kc)}
                  disabled={!currentDevice}>
                  {b.label}
                </button>
              ))}
              <button className={`keypad-btn del ${activeKey === 'del' ? 'active-press' : ''}`}
                onClick={sendDelete} disabled={!currentDevice} title="Backspace">
                <Delete size={18} />
              </button>
              <button className={`keypad-btn ${activeKey === '0' ? 'active-press' : ''}`}
                onClick={() => sendDigit('0', 7)} disabled={!currentDevice}>
                0
              </button>
              <button className={`keypad-btn enter ${activeKey === 'enter' ? 'active-press' : ''}`}
                onClick={sendEnter} disabled={!currentDevice} title="Enter / Confirm">
                <CornerDownLeft size={18} />
              </button>
            </div>

            {/* Text injection */}
            <div className="text-bar">
              <input className="input" placeholder="Type text / password → sends as keyevents..."
                value={customText} onChange={e => setCustomText(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && sendText()}
                disabled={!currentDevice} />
              <button className="btn btn-primary btn-sm btn-icon" onClick={sendText}
                disabled={!currentDevice || !customText.trim()} title="Send to phone">
                <Send size={14} />
              </button>
            </div>
          </div>

          {/* Hardware & Quick Actions */}
          <div className="card">
            <div className="card__title">Hardware & Quick Actions</div>
            <div className="hw-grid">
              {[
                { label: 'Power',   icon: <Power size={14} color="var(--red)"/>,    kc: 26,  title: 'Power button' },
                { label: 'Unlock',  icon: <Unlock size={14} color="var(--accent)"/>,kc: null,title: 'Swipe up unlock', swipe: true },
                { label: 'Sleep',   icon: <Moon size={14} color="var(--purple)"/>,  kc: 223, title: 'Force sleep' },
                { label: 'Wake',    icon: <Sun size={14} color="var(--orange)"/>,   kc: 224, title: 'Force wake' },
                { label: 'Vol +',   icon: <Volume2 size={14} />,                    kc: 24,  title: 'Volume up' },
                { label: 'Vol −',   icon: <Volume1 size={14} />,                    kc: 25,  title: 'Volume down' },
                { label: 'Mute',    icon: <VolumeX size={14} />,                    kc: 164, title: 'Mute' },
                { label: 'Notifs',  icon: <Bell size={14} />,                       kc: 83,  title: 'Notification panel' },
                { label: 'Settings',icon: <Settings size={14}/>,                    kc: 283, title: 'Quick settings' },
              ].map(b => (
                <button key={b.label} className="hw-btn" disabled={!currentDevice} title={b.title}
                  onClick={() => {
                    if (!currentDevice) return;
                    if (b.swipe) {
                      post('/input/unlock', { serial: currentDevice.serial });
                    } else if (b.kc != null) {
                      sendKey(b.kc, b.label);
                    }
                  }}>
                  {b.icon}<span>{b.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Pair Code Modal */}
      {showPairModal && (
        <PairCodeModal
          onClose={() => setShowPairModal(false)}
          onPaired={() => { setShowPairModal(false); scan(); }}
        />
      )}
    </div>
  );
}
