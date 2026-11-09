# platform/macos/console.py
# No-op stubs: macOS has no console window to own or hide (the app is launched
# from a terminal or as a bundle), but the platform contract requires the API.
# Windows mirror: platform/windows/console.py (the real implementation).
def setup(start_in_tray=True):
    pass


def open_console():
    return False


def owns_console():
    return False


def hide():
    pass


def show():
    pass


def is_minimized():
    return False


def start_minimize_monitor(on_minimize):
    pass
