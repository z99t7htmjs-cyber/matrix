"""
Desktop integration: things that make Matrix behave like an installed program.

  * open_target()  opens a Windows settings page or tool. Only names from the
                   fixed list below are accepted, so the dashboard can never ask
                   the server to run an arbitrary command.
  * autostart      start Matrix in the background when you sign in to Windows
                   (a per-user "Run" entry, the same mechanism Task Manager's
                   Startup apps list shows; no administrator rights needed)
  * open_window()  show the dashboard in its own app window (Chrome or Edge in
                   "app" mode: no tabs or address bar), or a normal browser tab
"""

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from paths import APP_DIR, DATA_DIR, IS_WINDOWS

# name -> what to open. "ms-settings:" and "windowsdefender:" are Windows' own links to settings pages.
TARGETS = {
    "windowsupdate": "ms-settings:windowsupdate",
    "security": "windowsdefender:",
    "startupapps": "ms-settings:startupapps",
    "apps": "ms-settings:appsfeatures",
    "storage": "ms-settings:storagesense",
    "power": "ms-settings:powersleep",
    "gamemode": "ms-settings:gaming-gamemode",
    "graphics": "ms-settings:display-advancedgraphics",
    "remotedesktop": "ms-settings:remotedesktop",
    "wifi": "ms-settings:network-wifi",
    "uac": ["UserAccountControlSettings.exe"],
    "taskmanager": ["taskmgr.exe"],
    "eventviewer": ["eventvwr.msc"],
    "reliability": ["perfmon.exe", "/rel"],
    "datafolder": ["explorer.exe", str(DATA_DIR)],
    "matrix-update": "https://github.com/z99t7htmjs-cyber/matrix",
    "accounts": "ms-settings:otherusers",
    "backup": "ms-settings:backup",
    "sharing": ["control.exe", "/name", "Microsoft.NetworkAndSharingCenter"],
}


def open_target(name):
    if not IS_WINDOWS:
        raise ValueError("Opening Windows pages only works on Windows.")
    target = TARGETS.get(name)
    if target is None:
        raise ValueError("Unknown page.")
    if isinstance(target, str):
        os.startfile(target)  # opens the link with its registered handler (Settings, Windows Security)
    elif target[0].endswith(".msc"):
        os.startfile(target[0])
    else:
        subprocess.Popen(target)


# --- auto-start ----------------------------------------------------------------------------

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "Matrix"


def background_python():
    """pythonw.exe runs Python without a console window."""
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    return windowless if windowless.exists() else exe


def autostart_command(open_window):
    script = APP_DIR / "server" / "matrix_server.py"
    flag = "--open" if open_window else "--background"
    return f'"{background_python()}" "{script}" {flag}'


def autostart_enabled():
    if not IS_WINDOWS:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_VALUE)
            return True
    except OSError:
        return False


def set_autostart(enabled, open_window=False):
    if not IS_WINDOWS:
        raise ValueError("Auto-start only works on Windows.")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, autostart_command(open_window))
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


# --- app window ------------------------------------------------------------------------------

def _browser():
    """Chrome first (what you use), then Edge (always present on Windows)."""
    if not IS_WINDOWS:
        return shutil.which("google-chrome") or shutil.which("chromium")
    candidates = []
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.append(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
    for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES")):
        if base:
            candidates.append(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    return next((str(p) for p in candidates if p.exists()), None)


def open_window(url):
    browser = _browser()
    if browser:
        subprocess.Popen([browser, f"--app={url}", "--window-size=1600,950"])
    else:
        webbrowser.open(url)
