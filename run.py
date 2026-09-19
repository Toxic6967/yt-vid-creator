from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path
from threading import Timer

ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"


def _relaunch_in_venv() -> None:
    if sys.prefix == sys.base_prefix and VENV_PYTHON.exists():
        raise SystemExit(subprocess.call([str(VENV_PYTHON), str(Path(__file__).resolve())]))


def _open_browser() -> None:
    try:
        webbrowser.open(URL)
    except Exception:
        pass


if __name__ == "__main__":
    _relaunch_in_venv()
    import uvicorn

    print("\nShorts Studio V1")
    print(f"Opening {URL}\n")
    Timer(1.2, _open_browser).start()
    uvicorn.run("shorts_studio.main:app", host=HOST, port=PORT, reload=False)
