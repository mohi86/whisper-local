# ui_theme.py
# Light, dark or follow-the-system for the app's windows (Settings, History,
# the welcome window, cheat sheet, capture window, add-word dialog), like
# Wispr Flow's hub themes. The windows are written against one dark palette;
# c() maps each of those colours to its counterpart in the active theme, so a
# window opts in by wrapping its colour literals and nothing else changes.
# The floating level pill stays dark: it sits over arbitrary content.

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

THEMES = ('system', 'dark', 'light')

# Dark colour -> light counterpart. Roles, in order: window background,
# panel, raised control, border, text, dimmed text (x2), accent, link,
# success (+hover), danger.
_LIGHT = {
    '#0d1117': '#ffffff',
    '#161b22': '#f6f8fa',
    '#21262d': '#eaeef2',
    '#30363d': '#d0d7de',
    '#c9d1d9': '#1f2328',
    '#8b949e': '#59636e',
    '#7d8590': '#59636e',
    '#1f6feb': '#0969da',
    '#58a6ff': '#0969da',
    '#3fb950': '#1a7f37',
    '#46c155': '#1f883d',
    '#f85149': '#cf222e',
}

_resolved = None   # 'dark' or 'light', worked out once per process


# Whether the OS is in dark mode. Windows: the "app mode" switch in Settings >
# Personalization > Colors. macOS: AppleInterfaceStyle is "Dark" only in dark
# mode. Anything unreadable counts as light, the OS default.
def system_prefers_dark() -> bool:
    try:
        if sys.platform == 'win32':
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                return winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] == 0
        if sys.platform == 'darwin':
            out = subprocess.run(['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                                 capture_output=True, text=True, timeout=2)
            return out.stdout.strip().lower() == 'dark'
    except Exception as e:
        logger.debug(f"Could not read the system theme: {e}")
    return False


# ui.theme from the user's settings file, read directly rather than through
# ConfigManager so any window can ask cheaply. Missing or invalid -> system.
def configured_theme() -> str:
    try:
        from pathlib import Path
        from ruamel.yaml import YAML
        from .utils import get_user_app_data_path
        path = Path(get_user_app_data_path()) / 'user_settings.yaml'
        if path.exists():
            with open(path, encoding='utf-8') as f:
                data = YAML(typ='safe').load(f) or {}
            theme = str(((data.get('ui') or {}).get('theme')) or 'system').strip().lower()
            if theme in THEMES:
                return theme
    except Exception as e:
        logger.debug(f"Could not read ui.theme: {e}")
    return 'system'


def resolve(theme: str = None) -> str:
    theme = theme or configured_theme()
    if theme == 'system':
        return 'dark' if system_prefers_dark() else 'light'
    return theme if theme in ('dark', 'light') else 'dark'


def active() -> str:
    global _resolved
    if _resolved is None:
        _resolved = resolve()
    return _resolved


# The active theme's version of one of the dark palette's colours.
def c(dark_color: str) -> str:
    if active() == 'light':
        return _LIGHT.get(dark_color.lower(), dark_color)
    return dark_color
