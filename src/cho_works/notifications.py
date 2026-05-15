from __future__ import annotations

import platform
import shutil
import subprocess


def notify(title: str, message: str) -> bool:
    system = platform.system()
    try:
        if system == "Darwin":
            script = f'display notification "{_escape(message)}" with title "{_escape(title)}"'
            subprocess.run(["osascript", "-e", script], check=False, timeout=3)
            return True
        if system == "Linux" and shutil.which("notify-send"):
            subprocess.run(["notify-send", title, message], check=False, timeout=3)
            return True
    except Exception:
        return False
    return False


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')

