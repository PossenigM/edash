"""Lock, sleep and shutdown events on Windows, via a hidden window and ctypes (no extra deps)."""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes

from edash.host.platform.base import EventCallback

log = logging.getLogger(__name__)

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_POWERBROADCAST = 0x0218
WM_WTSSESSION_CHANGE = 0x02B1
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0

POWER_EVENTS = {PBT_APMSUSPEND: "suspend", PBT_APMRESUMESUSPEND: "resume", PBT_APMRESUMEAUTOMATIC: "resume"}
SESSION_EVENTS = {WTS_SESSION_LOCK: "lock", WTS_SESSION_UNLOCK: "unlock"}

# Windows allows about 2 s for PBT_APMSUSPEND and a few seconds for WM_ENDSESSION.
# Holding the window procedure that long gives the serial write and the
# device a head start before USB power may drop.
HOLD_S = {"suspend": 1.5, "shutdown": 3.0}

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def _api():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]  # fmt: skip
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = LRESULT
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    wtsapi32.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
    wtsapi32.WTSRegisterSessionNotification.restype = wintypes.BOOL
    wtsapi32.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    return user32, wtsapi32, kernel32


class WindowsEventWatcher:
    """Owns a hidden top-level window on its own thread.

    Not a message-only window: those do not receive broadcasts such as
    WM_POWERBROADCAST and WM_ENDSESSION.
    """

    def __init__(self, callback: EventCallback):
        self._callback = callback
        self._user32, self._wtsapi32, self._kernel32 = _api()
        self.hwnd: int | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="windows-events", daemon=True)

    def start(self) -> WindowsEventWatcher:
        self._thread.start()
        self._ready.wait(5)
        return self

    def stop(self) -> None:
        if self.hwnd:
            self._user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        self._thread.join(timeout=3)

    def _run(self) -> None:
        user32 = self._user32
        self._wndproc = WNDPROC(self._handle)  # keep a reference, or ctypes frees the callback
        instance = self._kernel32.GetModuleHandleW(None)
        class_name = f"eDashEvents{id(self)}"
        wndclass = WNDCLASSW(lpfnWndProc=self._wndproc, hInstance=instance, lpszClassName=class_name)
        if not user32.RegisterClassW(ctypes.byref(wndclass)):
            log.warning("cannot register window class (error %s); lock/sleep events disabled", ctypes.get_last_error())
            self._ready.set()
            return
        hwnd = user32.CreateWindowExW(0, class_name, "eDash events", 0, 0, 0, 0, 0, None, None, instance, None)
        if not hwnd:
            log.warning("cannot create event window (error %s); lock/sleep events disabled", ctypes.get_last_error())
            user32.UnregisterClassW(class_name, instance)
            self._ready.set()
            return
        if not self._wtsapi32.WTSRegisterSessionNotification(hwnd, NOTIFY_FOR_THIS_SESSION):
            log.warning("cannot subscribe to lock events (error %s)", ctypes.get_last_error())
        self.hwnd = hwnd
        self._ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        self.hwnd = None
        user32.UnregisterClassW(class_name, instance)

    def _handle(self, hwnd, msg, wparam, lparam):
        try:
            event = None
            if msg == WM_POWERBROADCAST:
                event = POWER_EVENTS.get(wparam)
            elif msg == WM_WTSSESSION_CHANGE:
                event = SESSION_EVENTS.get(wparam)
            elif msg == WM_QUERYENDSESSION:
                return 1  # never block shutdown
            elif msg == WM_ENDSESSION and wparam:
                event = "shutdown"
            elif msg == WM_CLOSE:
                self._user32.DestroyWindow(hwnd)
                return 0
            elif msg == WM_DESTROY:
                self._wtsapi32.WTSUnRegisterSessionNotification(hwnd)
                self._user32.PostQuitMessage(0)
                return 0
            if event:
                self._callback(event)
                time.sleep(HOLD_S.get(event, 0))
                if msg == WM_POWERBROADCAST:
                    return 1
                if msg == WM_ENDSESSION:
                    return 0
        except Exception:
            log.exception("handling window message 0x%04x failed", msg)
        return self._user32.DefWindowProcW(hwnd, msg, wparam, lparam)
