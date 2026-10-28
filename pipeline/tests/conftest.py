import socket
import struct
import wave
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    """M0 acceptance: tests make no network calls. Any attempt fails loudly."""

    def _refuse(*args, **kwargs):
        raise RuntimeError("network access is blocked in pipeline tests")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)


@pytest.fixture
def sample_wav(tmp_path: Path) -> Path:
    """One second of 16 kHz mono silence-with-a-click; enough to exercise file plumbing.
    A real speech fixture with a golden transcript arrives with M1 (ASR)."""
    path = tmp_path / "sample.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        frames = [0] * 16000
        frames[8000] = 12000
        wav.writeframes(struct.pack(f"<{len(frames)}h", *frames))
    return path
