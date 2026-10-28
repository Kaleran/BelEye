"""Unit tests for BelEye core modules (no Qt required)."""

from __future__ import annotations

import json
import struct

from app.config import CameraConfig
from app.nvr_config import NvrConfig
from app.rtsp import build_rtsp_url
from dvrip.auth import sofia_hash
from dvrip.packet import HEADER_SIZE, HEADER_STRUCT, Packet, pack, unpack
from dvrip.sofia_frame import SofiaFrameParser, detect_codec

# ---------------------------------------------------------------------------
# sofia_frame
# ---------------------------------------------------------------------------


def _make_sofia_frame(marker: int, payload: bytes) -> bytes:
    """Build a Sofia sub-frame matching the parser layout:
    buf[0:16] is the header (startcode+marker+12 bytes, length LE at buf[12:16]),
    payload follows at buf[16:].
    """
    header = bytearray(16)
    header[0:3] = b"\x00\x00\x01"
    header[3] = marker
    struct.pack_into("<I", header, 12, len(payload))
    return bytes(header) + payload


def test_sofia_iframe_yields_payload_and_counts_iframe() -> None:
    p = SofiaFrameParser()
    payload = b"\x67\x42\x00\x0a"  # fake SPS
    frame = _make_sofia_frame(0xFC, payload)
    out = p.feed(frame)
    assert out == payload
    assert p.iframes_seen == 1
    assert p._frames_seen == 1


def test_sofia_pframe_yields_payload_no_iframe_count() -> None:
    p = SofiaFrameParser()
    payload = b"\x41\x42"
    frame = (
        b"\x00\x00\x01\xfd" + struct.pack("<I", len(payload)) + payload
    )  # 8-byte hdr
    out = p.feed(frame)
    assert out == payload
    assert p.iframes_seen == 0


def test_sofia_audio_dropped() -> None:
    p = SofiaFrameParser()
    payload = b"\x00" * 10
    frame = (
        b"\x00\x00\x01\xfa" + struct.pack("<H", len(payload)) + b"\x00\x00" + payload
    )
    out = p.feed(frame)
    assert out == b""


def test_sofia_resync_on_garbage() -> None:
    p = SofiaFrameParser()
    garbage = b"\x00\x00\x01\x00\x00\x00\x00\x00"  # unknown marker -> resync
    good = _make_sofia_frame(0xFC, b"\x65")
    out = p.feed(garbage + good)
    assert out == b"\x65"


def test_sofia_passthrough_raw_h264() -> None:
    p = SofiaFrameParser()
    raw = b"\x00\x00\x00\x01\x67\x42\x00\x0a" + b"\x00" * 50
    out = p.feed(raw)
    assert out == raw
    assert p._passthrough is True


def test_detect_codec_h264_sps() -> None:
    assert detect_codec(b"\x00\x00\x00\x01\x67\x42\x00\x0a") == "h264"


def test_detect_codec_hevc_vps() -> None:
    # HEVC VPS: nal_type 32 -> byte (32<<1)|forbidden0 = 0x40
    assert detect_codec(b"\x00\x00\x00\x01\x40\x00\x00") == "hevc"


def test_detect_codec_hevc_idr() -> None:
    # HEVC IDR_N_LP: nal_type 20 -> byte 0x28 (forbidden_zero=0)
    assert detect_codec(b"\x00\x00\x00\x01\x28\x00\x00") == "hevc"


def test_detect_codec_none() -> None:
    assert detect_codec(b"\x00\x00\x00\x02\xff\xff") is None


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------


def test_sofia_hash_length() -> None:
    h = sofia_hash("admin")
    assert len(h) == 8


def test_sofia_hash_deterministic() -> None:
    assert sofia_hash("admin") == sofia_hash("admin")


def test_sofia_hash_empty_constant() -> None:
    # Well-known Xiongmai empty-password constant.
    assert sofia_hash("") == "tlJwpbo6"


# ---------------------------------------------------------------------------
# packet
# ---------------------------------------------------------------------------


def test_packet_pack_unpack_roundtrip() -> None:
    pkt = Packet(msg_id=1000, payload=b'{"a":1}', session_id=0x12345678, sequence=7)
    wire = pack(pkt)
    out, consumed = unpack(wire, 0)
    assert consumed == len(wire)
    assert out is not None
    assert out.msg_id == 1000
    assert out.payload == b'{"a":1}'
    assert out.session_id == 0x12345678
    assert out.sequence == 7


def test_packet_header_size() -> None:
    assert HEADER_SIZE == 20
    assert HEADER_STRUCT.size == 20


def test_packet_unpack_bad_flag_resyncs() -> None:
    # garbage byte then a valid packet
    pkt = Packet(msg_id=1001, payload=b"x")
    wire = b"\x00" + pack(pkt)
    out, consumed = unpack(wire, 0)
    assert out is None
    assert consumed == 1  # skipped the garbage byte
    out2, _ = unpack(wire, consumed)
    assert out2 is not None
    assert out2.msg_id == 1001


# ---------------------------------------------------------------------------
# rtsp url builder
# ---------------------------------------------------------------------------


def _cam(password: str = "", **overrides) -> CameraConfig:
    d = {
        "id": "cid",
        "name": "Cam",
        "host": "192.168.0.63",
        "port": 554,
        "username": "",
        "path": "/",
        "transport": "tcp",
        "stream_type": "main",
    }
    d.update(overrides)
    return CameraConfig(**d), password


def test_build_rtsp_url_no_auth_default_path() -> None:
    cam, _ = _cam()
    url = build_rtsp_url(cam)
    assert url == "rtsp://192.168.0.63:554"


def test_build_rtsp_url_empty_path_main() -> None:
    cam, _ = _cam(path="")
    url = build_rtsp_url(cam)
    assert url == "rtsp://192.168.0.63:554"


def test_build_rtsp_url_substream_appends() -> None:
    cam, _ = _cam(path="/", stream_type="sub")
    url = build_rtsp_url(cam)
    assert url == "rtsp://192.168.0.63:554/substream"


def test_build_rtsp_url_explicit_path() -> None:
    cam, _ = _cam(path="/Streaming/Channels/101")
    url = build_rtsp_url(cam)
    assert url == "rtsp://192.168.0.63:554/Streaming/Channels/101"


def test_build_rtsp_url_path_without_slash() -> None:
    cam, _ = _cam(path="live.sdp")
    url = build_rtsp_url(cam)
    assert url == "rtsp://192.168.0.63:554/live.sdp"


def test_build_rtsp_url_with_auth() -> None:
    cam, _ = _cam(username="admin", password="pw")
    url = build_rtsp_url(cam, "pw")
    assert url == "rtsp://admin:pw@192.168.0.63:554"


def test_build_rtsp_url_special_chars_escaped() -> None:
    cam, _ = _cam(username="a b", password="p@ss")
    url = build_rtsp_url(cam, "p@ss")
    assert "a%20b" in url
    assert "p%40ss" in url


def test_build_rtsp_url_username_only() -> None:
    cam, _ = _cam(username="admin", password="")
    url = build_rtsp_url(cam, "")
    assert url == "rtsp://admin@192.168.0.63:554"


# ---------------------------------------------------------------------------
# config dataclasses
# ---------------------------------------------------------------------------


def test_camera_config_roundtrip() -> None:
    cam = CameraConfig(name="X", host="1.2.3.4", port=554, stream_type="sub")
    d = cam.to_dict()
    cam2 = CameraConfig.from_dict(d)
    assert cam2.name == "X"
    assert cam2.stream_type == "sub"
    assert cam.id == cam2.id  # from_dict preserves id


def test_nvr_config_roundtrip() -> None:
    nvr = NvrConfig(name="N", host="10.0.0.1", port=34567)
    d = nvr.to_dict()
    nvr2 = NvrConfig.from_dict(d)
    assert nvr2.name == "N"
    assert nvr2.port == 34567
    assert nvr.id == nvr2.id


def test_load_nvrs_does_not_write_side_effect(monkeypatch, tmp_path) -> None:
    """load_nvrs must normalize in memory without writing back to disk."""
    import app.nvr_config as nvrcfg

    nvrs_file = nvrcfg.nvrs_file
    nvrcfg.nvrs_file = lambda: tmp_path / "nvrs.json"

    try:
        (tmp_path / "nvrs.json").write_text(
            json.dumps(
                [
                    {
                        "id": "n1",
                        "name": "N",
                        "host": "1.2.3.4",
                        "port": 34567,
                        "username": "admin",
                        "prefer_substream": True,
                        "channels": [],
                    }
                ]
            ),
            encoding="utf-8",
        )
        loaded = nvrcfg.load_nvrs()
        assert loaded[0].prefer_substream is False
        # File must be untouched (no side-effect write).
        assert (tmp_path / "nvrs.json").exists()
        data = json.loads((tmp_path / "nvrs.json").read_text(encoding="utf-8"))
        assert data[0]["prefer_substream"] is True
    finally:
        nvrcfg.nvrs_file = nvrs_file
