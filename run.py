from __future__ import annotations

import webbrowser
from threading import Timer

import uvicorn

HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"


def _open_browser() -> None:
    try:
        webbrowser.open(URL)
    except Exception:
        pass


if __name__ == "__main__":
    print("\nShorts Studio V1")
    print(f"Opening {URL}\n")
    Timer(1.2, _open_browser).start()
    uvicorn.run("shorts_studio.main:app", host=HOST, port=PORT, reload=False)
