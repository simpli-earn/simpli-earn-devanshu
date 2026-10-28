"""Deterministic identifiers, so retried jobs address the same rows and blobs."""

import hashlib
from datetime import date, datetime


def normalize_ticker(ticker: str) -> str:
    cleaned = ticker.strip().upper()
    if not cleaned or not all(ch.isalnum() or ch in ".-" for ch in cleaned):
        raise ValueError(f"Invalid ticker: {ticker!r}")
    return cleaned


def call_id(ticker: str, call_date: date | datetime) -> str:
    """Same ticker and calendar date always give the same id, which makes scheduling idempotent."""
    day = call_date.date() if isinstance(call_date, datetime) else call_date
    return f"{normalize_ticker(ticker)}-{day.isoformat()}"


def chunk_key(cid: str, index: int) -> str:
    if index < 0:
        raise ValueError("chunk index must be >= 0")
    return f"audio/{cid}/chunks/{index:06d}.bin"


def final_audio_key(cid: str, extension: str = "wav") -> str:
    return f"audio/{cid}/final.{extension.lstrip('.')}"


def manifest_key(cid: str) -> str:
    return f"audio/{cid}/manifest.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
