"""Native macOS folder dialog ("Escolher pasta") driven through `osascript`.

The script text is a constant. The prompt (chosen server-side from a fixed
`purpose` map) is `argv` item 1 and the optional starting folder is item 2;
neither is ever interpolated into the script. The dialog runs on the machine
hosting the server, which is the user's own machine in this app.
"""

import subprocess
import sys
import threading
from pathlib import Path
from typing import Literal

OSASCRIPT = "/usr/bin/osascript"
TIMEOUT_SECONDS = 300
_USER_CANCELED = "(-128)"

Purpose = Literal["data", "notebooks"]
_PROMPTS: dict[str, str] = {
    "data": "Choose the data directory",
    "notebooks": "Choose the notebooks folder",
}

# `tell current application to activate` brings the dialog to the front
# without the Automation permission that targeting System Events would need.
_SCRIPT = (
    "on run argv",
    'tell current application to activate',
    "set promptText to item 1 of argv",
    "if (count of argv) > 1 then",
    "set chosen to choose folder with prompt promptText default location (POSIX file (item 2 of argv) as alias)",
    "else",
    "set chosen to choose folder with prompt promptText",
    "end if",
    "return POSIX path of chosen",
    "end run",
)

_lock = threading.Lock()


class PickerError(Exception):
    status_code = 500


class PickerUnsupported(PickerError):
    status_code = 501


class PickerBusy(PickerError):
    status_code = 409


class PickerTimeout(PickerError):
    status_code = 504


def _valid_default(default: str | None) -> str | None:
    """Return `default` only if it is an absolute path to an existing directory."""
    if not default or not default.startswith("/") or "\x00" in default:
        return None
    try:
        return default if Path(default).is_dir() else None
    except OSError:
        return None


def choose_directory(default: str | None = None, purpose: Purpose = "data") -> str | None:
    """Open the dialog and block until it closes.

    Returns the absolute POSIX path (no trailing slash except `/`), or None if
    the user cancelled. Raises PickerError subclasses otherwise.
    """
    if sys.platform != "darwin":
        raise PickerUnsupported("The native picker is only available on macOS.")
    if not _lock.acquire(blocking=False):
        raise PickerBusy("A folder picker is already open.")
    try:
        cmd = [OSASCRIPT]
        for line in _SCRIPT:
            cmd += ["-e", line]
        cmd.append(_PROMPTS[purpose])
        start = _valid_default(default)
        if start:
            cmd.append(start)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired as exc:
            raise PickerTimeout("Timed out waiting for a folder to be chosen.") from exc
        except OSError as exc:
            raise PickerError("Could not open the folder picker.") from exc
    finally:
        _lock.release()

    if proc.returncode != 0:
        if _USER_CANCELED in proc.stderr:
            return None
        raise PickerError("The folder picker failed.")
    path = proc.stdout.rstrip("\r\n")
    if not path.startswith("/"):
        raise PickerError("The folder picker returned an invalid path.")
    return path.rstrip("/") or "/"
