import os
import subprocess
import sys


def open_file(filepath: str):
    """
    Safely attempts to open an exported file on macOS if running interactively,
    never raising an exception or blocking automated pipelines.
    """
    if not filepath or not os.path.exists(filepath):
        return
    if os.environ.get("CI") or os.environ.get("HEADLESS", "1") == "1":
        return
    try:
        if sys.platform == "darwin":
            subprocess.Popen(
                ["open", filepath],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass
