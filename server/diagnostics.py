"""
Troubleshooting helpers: a screenshot of the Matrix window copied to the
clipboard, and a plain-text diagnostics report.

Screenshots use Pillow (installed by "Install or Update Matrix") and the
Windows clipboard. They capture only the window in front, which is Matrix
at the moment you press the button, and are also saved in the data folder
under screenshots\\.
"""

import ctypes
import ctypes.wintypes
import io
import platform
import sys
import time
from datetime import datetime

from paths import DATA_DIR, LOG_FILE, VERSION, IS_WINDOWS

SCREENSHOT_DIR = DATA_DIR / "screenshots"
KEEP_SCREENSHOTS = 20


def _window_rect():
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    hwnd = user32.GetForegroundWindow()
    rect = ctypes.wintypes.RECT()
    # DWM gives the visible frame without the invisible resize border.
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    got = ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS,
                                                    ctypes.byref(rect), ctypes.sizeof(rect)) == 0
    if not got:
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def _to_clipboard(image):
    """Put an image on the Windows clipboard as a bitmap (what Ctrl+V pastes)."""
    w = ctypes.wintypes

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "BMP")
    dib = buffer.getvalue()[14:]  # the clipboard wants the bitmap without its 14-byte file header

    kernel32, user32 = ctypes.windll.kernel32, ctypes.windll.user32
    kernel32.GlobalAlloc.restype = w.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [w.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [w.HGLOBAL]
    user32.SetClipboardData.argtypes = [w.UINT, w.HANDLE]
    user32.SetClipboardData.restype = w.HANDLE
    GMEM_MOVEABLE, CF_DIB = 0x0002, 8

    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dib))
    pointer = kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, dib, len(dib))
    kernel32.GlobalUnlock(handle)
    for _ in range(10):  # another app may be holding the clipboard for a moment
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise ValueError("The clipboard is busy. Try again.")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_DIB, handle):
            raise ValueError("Windows didn't accept the image on the clipboard.")
    finally:
        user32.CloseClipboard()


def screenshot():
    if not IS_WINDOWS:
        raise ValueError("Screenshots work on Windows only.")
    try:
        from PIL import ImageGrab
    except ImportError:
        raise ValueError("Screenshots need Pillow. Run \"Install or Update Matrix\" again to install it.")
    bbox = _window_rect()
    image = ImageGrab.grab(bbox=bbox, all_screens=True)
    _to_clipboard(image)
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    path = SCREENSHOT_DIR / f"matrix-{datetime.now():%Y%m%d-%H%M%S}.png"
    image.save(path)
    for old in sorted(SCREENSHOT_DIR.glob("matrix-*.png"))[:-KEEP_SCREENSHOTS]:
        old.unlink(missing_ok=True)
    return str(path)


def _log_tail(lines=40):
    try:
        text = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ["(no log file)"]
    interesting = [l for l in text if any(w in l.lower() for w in ("fail", "error", "couldn't", "could not", "denied", "starting"))]
    return interesting[-lines:] or ["(no errors logged)"]


def report(state, monitors, ai_status, history):
    """Plain text for pasting into a chat when asking for help. No MAC addresses or device names."""
    system, meta = state["system"], state["meta"]
    now = datetime.now()

    def age(ts):
        return f"{int(time.time() - ts)}s ago" if ts else "not yet"

    lines = [
        f"Matrix {VERSION} diagnostics · {now:%Y-%m-%d %H:%M}",
        f"Windows: {system.get('os')} · Python {sys.version.split()[0]} ({platform.machine()})",
        f"CPU: {system.get('cpuName')} · live vitals: {'on' if system.get('available') else 'OFF (psutil missing)'}",
        f"GPU: {', '.join(g['name'] for g in system.get('gpus') or []) or 'none reported (nvidia-smi not found?)'}",
        f"Uptime: {(system.get('uptimeSeconds') or 0) // 3600} h",
        "",
        "Background checks:",
    ]
    for name, mon in monitors.items():
        status = f"last ran {age(mon.checked_at)}" + (f" · ERROR: {mon.error}" if getattr(mon, "error", None) else "")
        lines.append(f"  {name}: {status}")
    nodes = state["network"]["nodes"]
    lines += [
        f"  Network: {len(nodes)} nodes, {sum(n['status'] == 'online' for n in nodes)} online · maker list: {meta.get('vendorDb')}",
        f"  Ask Matrix: Ollama {'running' if ai_status['running'] else 'NOT running'}, "
        f"model {ai_status['model']} {'ready' if ai_status['installed'] else 'NOT downloaded'}",
        f"  History: {history.size_mb()} MB, {history.device_count()} devices remembered",
        "",
        "Advisor:",
    ]
    for a in state.get("advice") or []:
        lines.append(f"  [{a['urgency']}] {a['title']}")
    for a in state.get("handled") or []:
        lines.append(f"  ({a['status']}) {a['title']}")
    if not state.get("advice") and not state.get("handled"):
        lines.append("  (nothing)")
    lines += ["", "Recent log lines:"] + [f"  {l}" for l in _log_tail()]
    return "\n".join(lines)
