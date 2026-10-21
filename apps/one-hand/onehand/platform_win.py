"""Windows backend: a low-level keyboard hook and SendInput, using only ctypes."""
import ctypes
import os
import threading
import time
from ctypes import wintypes

from .engine import PASS, SUPPRESS, Tap
from .keys import WIN_CODES, WIN_EXTENDED, WIN_GENERIC

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_QUIT = 0x0012
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x0001, 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Marks keys we type ourselves so the hook lets them through. Keys typed by
# other software (on-screen keyboards, switch access, voice control) still
# go through the engine.
MAGIC = 0x4C534F48  # "LSOH"

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                               ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

VK_TO_NAME = {v: k for k, v in WIN_CODES.items()} | WIN_GENERIC


class WindowsBackend:
    platform = "windows"

    def __init__(self):
        self.engine = None
        self._thread = None
        self._thread_id = None
        self._proc = HOOKPROC(self._hook)   # keep a reference so it isn't garbage collected
        self._hook_handle = None
        self._app_cache = (None, None)
        self.error = None

    # ---- lifecycle ----------------------------------------------------

    def start(self, engine):
        self.engine = engine
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait(5)
        if self.error:
            raise RuntimeError(self.error)

    def _run(self, ready):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc,
                                                     kernel32.GetModuleHandleW(None), 0)
        if not self._hook_handle:
            self.error = f"Could not watch the keyboard (error {ctypes.get_last_error()})."
            ready.set()
            return
        ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(self._hook_handle)

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    # ---- the hook -----------------------------------------------------

    def _hook(self, code, wparam, lparam):
        if code == 0:
            kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            name = VK_TO_NAME.get(kb.vkCode)
            if name and kb.dwExtraInfo != MAGIC:
                down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                try:
                    action = self.engine.handle(name, down, time.monotonic(), self.front_app())
                except Exception:
                    action = PASS
                if action == SUPPRESS:
                    return 1
                if isinstance(action, Tap):
                    self.send(action)
                    return 1
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def send(self, tap):
        keys = list(tap.mods) + [tap.key]
        events = [(k, False) for k in keys] + [(k, True) for k in reversed(keys)]
        self._send_input(events, MAGIC)

    def inject(self, key, up):
        """Type a key as if from another program (the hook will see it). Used by --self-test."""
        self._send_input([(key, up)], 0)

    def _send_input(self, events, extra):
        arr = (INPUT * len(events))()
        for i, (k, up) in enumerate(events):
            flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if k in WIN_EXTENDED else 0)
            arr[i].type = INPUT_KEYBOARD
            arr[i].u.ki = KEYBDINPUT(WIN_CODES[k], 0, flags, 0, extra)
        user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))

    # ---- which app is in front ---------------------------------------

    def front_app(self):
        hwnd = user32.GetForegroundWindow()
        if hwnd and hwnd == self._app_cache[0]:
            return self._app_cache[1]
        name = None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if handle:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                name = os.path.basename(buf.value)
            kernel32.CloseHandle(handle)
        self._app_cache = (hwnd, name)
        return name

    # ---- feedback -----------------------------------------------------

    def play_sound(self, on):
        import winsound
        winsound.MessageBeep(winsound.MB_OK if on else winsound.MB_ICONASTERISK)

    def speak(self, text):
        import subprocess
        script = ("Add-Type -AssemblyName System.Speech; "
                  f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')")
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
                         creationflags=0x08000000)  # CREATE_NO_WINDOW

    def permission_help(self):
        return "Windows would not let the app watch the keyboard. Try restarting the app."

    def open_permission_settings(self):
        pass
