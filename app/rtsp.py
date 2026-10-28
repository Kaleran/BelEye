from __future__ import annotations

from urllib.parse import quote

from .config import CameraConfig


def build_rtsp_url(camera: CameraConfig, password: str = "") -> str:
    """
    Build an RTSP URL. If `camera.path` is empty or just "/", do NOT append
    a path — many cameras (Hikvision, Dahua default) reject `rtsp://host:554/`
    but accept `rtsp://host:554`. Equivalent to the working `ffplay` example:
        ffplay -rtsp_transport tcp rtsp://admin:password@192.168.0.63:554

    When the path is left at its default ("/"), the ``stream_type`` field
    selects a sensible default: "main" keeps the root path, "sub" appends
    "/substream".
    """
    raw_path = (camera.path or "").strip()
    if raw_path in ("", "/"):
        if camera.stream_type == "sub":
            path = "/substream"
        else:
            path = ""
    else:
        path = raw_path if raw_path.startswith("/") else "/" + raw_path

    user = quote(camera.username, safe="")
    pwd = quote(password, safe="")

    if user and pwd:
        auth = f"{user}:{pwd}@"
    elif user:
        auth = f"{user}@"
    else:
        auth = ""

    return f"rtsp://{auth}{camera.host}:{camera.port}{path}"
