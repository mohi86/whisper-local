# platform/windows/mouse.py
# A mouse button as a push-to-talk trigger (issue #36, Wispr Flow's "Mouse
# Flow"): hold the middle or a side button to dictate. Uses a low-level mouse
# hook (WH_MOUSE_LL) on its own message-loop thread, because only a hook can
# both see the side buttons and stop the button's normal action (a side button
# would otherwise also go Back in the browser).
# macOS mirror: platform/macos/mouse.py (not supported yet).

import ctypes
import ctypes.wintypes as wintypes
import logging
import threading

logger = logging.getLogger(__name__)

# Private handles, not the shared ctypes.windll ones: the argtypes set below
# would otherwise change these functions' signatures for every other module in
# the process. use_last_error makes ctypes.get_last_error() meaningful.
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

WH_MOUSE_LL = 14
WM_QUIT = 0x0012
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020B, 0x020C
XBUTTON1, XBUTTON2 = 0x0001, 0x0002

# Config value -> the buttons it means. "both" is either side button.
BUTTONS = {
    'middle': ('middle',),
    'x1': ('x1',),
    'x2': ('x2',),
    'both': ('x1', 'x2'),
}


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('pt', wintypes.POINT), ('mouseData', wintypes.DWORD),
                ('flags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def is_supported() -> bool:
    return True


# Which configured button a hook message is about, and whether it is a press.
# Returns (None, None) for every other message, mouse moves included.
def _decode(wparam, lparam):
    if wparam in (WM_MBUTTONDOWN, WM_MBUTTONUP):
        return 'middle', wparam == WM_MBUTTONDOWN
    if wparam in (WM_XBUTTONDOWN, WM_XBUTTONUP):
        info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        which = (info.mouseData >> 16) & 0xFFFF
        name = {XBUTTON1: 'x1', XBUTTON2: 'x2'}.get(which)
        return name, wparam == WM_XBUTTONDOWN
    return None, None


class MouseButtonTrigger:
    """Calls on_press / on_release when the chosen button goes down / up, and
    swallows those events so the button's own action doesn't happen.

    Every mouse event in the system passes through the hook, so the callback
    does the least possible: decode, hand the work to a thread, return. A hook
    that is slow to return makes the whole mouse stutter, and Windows silently
    removes one that keeps timing out. is_active() (the pause state) is read
    per event: while paused the button behaves normally again."""

    def __init__(self, button: str, on_press, on_release, is_active=lambda: True):
        if button not in BUTTONS:
            raise ValueError(f"Unknown mouse button {button!r}; use one of {', '.join(BUTTONS)}")
        self.buttons = BUTTONS[button]
        self.on_press = on_press
        self.on_release = on_release
        self.is_active = is_active
        self._hook = None
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()
        self._held = set()
        self._proc = HOOKPROC(self._hook_proc)   # referenced for the hook's lifetime

    def _hook_proc(self, n_code, wparam, lparam):
        if n_code == 0:
            try:
                name, pressed = _decode(wparam, lparam)
                if name in self.buttons:
                    # A release whose press we swallowed is always swallowed
                    # too, even if pause flipped in between, so no app ever
                    # sees a lone "up".
                    if pressed and self.is_active():
                        self._held.add(name)
                        threading.Thread(target=self.on_press, daemon=True,
                                         name='mouse-ptt-press').start()
                        return 1
                    if not pressed and name in self._held:
                        self._held.discard(name)
                        threading.Thread(target=self.on_release, daemon=True,
                                         name='mouse-ptt-release').start()
                        return 1
            except Exception as e:
                logger.debug(f"Mouse hook error: {e}")
        return user32.CallNextHookEx(None, n_code, wparam, lparam)

    # The hook lives on the thread that installed it, and that thread must
    # pump messages for the hook to be called at all.
    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc,
                                              kernel32.GetModuleHandleW(None), 0)
        self._ready.set()
        if not self._hook:
            logger.error(f"Could not install the mouse hook (error {ctypes.get_last_error()})")
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name='mouse-ptt-hook')
        self._thread.start()
        self._ready.wait(timeout=2.0)
        if self._hook:
            logger.info(f"Mouse push-to-talk on: {'/'.join(self.buttons)}")
        return bool(self._hook)

    def stop(self):
        if self._thread_id and self._thread and self._thread.is_alive():
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(timeout=2.0)
        self._thread = None
        self._held.clear()
