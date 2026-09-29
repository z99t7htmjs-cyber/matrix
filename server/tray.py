"""
The Matrix icon in the Windows system tray (the icons next to the clock).

  * Left-click: open the Matrix window.
  * Right-click: Open Matrix, Start with Windows (tick), Stop Matrix.
  * Colour shows status: green all clear, amber something to look at,
    red when something critical needs attention.
  * Notifications for critical events appear as Windows notifications
    coming from this icon.

Uses the Windows API directly through ctypes (no extra libraries). The icon
lives in its own thread with its own hidden window, which Windows needs to
send clicks and menu choices to.
"""

import ctypes
import threading
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_USER = 0x0400
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_APP_TRAY = WM_USER + 20
WM_APP_UPDATE = WM_USER + 21

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
NIIF_INFO, NIIF_WARNING = 0x1, 0x2

IMAGE_ICON = 1
SM_CXSMICON = 49
LR_LOADFROMFILE = 0x10
LR_DEFAULTSIZE = 0x40

MF_STRING, MF_SEPARATOR, MF_CHECKED = 0x0, 0x800, 0x8
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY = 0x2, 0x100, 0x80

CMD_OPEN, CMD_AUTOSTART, CMD_STOP = 1, 2, 3


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID), ("hBalloonIcon", wintypes.HICON),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
    ]


# Declare argument types so 64-bit handles aren't truncated.
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.RegisterWindowMessageW.restype = wintypes.UINT
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class TrayIcon:
    """Create with callbacks, then start(). Thread-safe: set_status() and notify() may be called from anywhere."""

    def __init__(self, icon_dir, on_open, on_stop, get_autostart, set_autostart):
        self.icons = {name: str(Path(icon_dir) / f"tray-{name}.ico") for name in ("ok", "warn", "alert")}
        self.on_open, self.on_stop = on_open, on_stop
        self.get_autostart, self.set_autostart = get_autostart, set_autostart
        self.hwnd = None
        self.status = ("ok", "Matrix: all systems nominal")
        self.pending_note = None
        self.lock = threading.Lock()
        self._handles = {}
        self._proc = WNDPROC(self._wndproc)  # keep a reference so it isn't garbage-collected

    # --- public ---------------------------------------------------------------------------

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="tray").start()

    def set_status(self, level, tip):
        with self.lock:
            if self.status == (level, tip):
                return
            self.status = (level, tip)
        self._post(WM_APP_UPDATE)

    def notify(self, title, message):
        with self.lock:
            self.pending_note = (title[:63], message[:255])
        self._post(WM_APP_UPDATE)

    def remove(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    # --- internals ------------------------------------------------------------------------

    def _post(self, message):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, message, 0, 0)

    def _icon(self, level):
        if level not in self._handles:
            # Ask for the small-icon size Windows uses in the tray (16 px at 100% scaling, larger on high-DPI screens).
            size = user32.GetSystemMetrics(SM_CXSMICON) or 16
            self._handles[level] = user32.LoadImageW(None, self.icons[level], IMAGE_ICON, size, size, LR_LOADFROMFILE)
        return self._handles[level]

    def _data(self):
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        return data

    def _show(self, action):
        level, tip = self.status
        data = self._data()
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_APP_TRAY
        data.hIcon = self._icon(level)
        data.szTip = tip[:127]
        shell32.Shell_NotifyIconW(action, ctypes.byref(data))

    def _balloon(self, title, message):
        data = self._data()
        data.uFlags = NIF_INFO
        data.szInfoTitle = title
        data.szInfo = message
        data.dwInfoFlags = NIIF_WARNING
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data))

    def _menu(self):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, CMD_OPEN, "Open Matrix")
        user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if self.get_autostart() else 0), CMD_AUTOSTART, "Start with Windows")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, CMD_STOP, "Stop Matrix")
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self.hwnd)  # so the menu closes when you click elsewhere
        choice = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY, point.x, point.y, 0, self.hwnd, None)
        user32.DestroyMenu(menu)
        return choice

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_APP_TRAY:
                event = lparam & 0xFFFF
                if event == WM_LBUTTONUP:
                    self.on_open()
                elif event == WM_RBUTTONUP:
                    choice = self._menu()
                    if choice == CMD_OPEN:
                        self.on_open()
                    elif choice == CMD_AUTOSTART:
                        self.set_autostart(not self.get_autostart())
                    elif choice == CMD_STOP:
                        self.on_stop()
                return 0
            if msg == WM_APP_UPDATE:
                self._show(NIM_MODIFY)
                with self.lock:
                    note, self.pending_note = self.pending_note, None
                if note:
                    self._balloon(*note)
                return 0
            if msg == self._taskbar_created:  # Explorer restarted: put the icon back
                self._show(NIM_ADD)
                return 0
            if msg == WM_CLOSE:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._data()))
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception as err:  # never let an exception escape into Windows
            print(f"[matrix] Tray icon error: {err}")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run(self):
        instance = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = instance
        wc.lpszClassName = "MatrixTrayWindow"
        user32.RegisterClassW(ctypes.byref(wc))
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self.hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "Matrix", 0, 0, 0, 0, 0, None, None, instance, None)
        if not self.hwnd:
            print("[matrix] Couldn't create the tray icon window.")
            return
        self._show(NIM_ADD)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
