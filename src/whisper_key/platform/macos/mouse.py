# platform/macos/mouse.py
# Mirror of platform/windows/mouse.py. A mouse button as push-to-talk isn't
# implemented on macOS yet: is_supported() is False, and the hotkey listener
# logs that and carries on with the keyboard hotkey alone.

BUTTONS = {
    'middle': ('middle',),
    'x1': ('x1',),
    'x2': ('x2',),
    'both': ('x1', 'x2'),
}


def is_supported() -> bool:
    return False


class MouseButtonTrigger:
    def __init__(self, button, on_press, on_release, is_active=lambda: True):
        raise NotImplementedError("Mouse push-to-talk isn't available on macOS yet")
