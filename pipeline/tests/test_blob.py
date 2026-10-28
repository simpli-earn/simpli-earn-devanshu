import pytest

from simpliearn_pipeline import ids
from simpliearn_pipeline.storage.blob import BlobConflictError, LocalBlobStore


def test_put_is_idempotent_and_detects_conflicts(tmp_path):
    store = LocalBlobStore(tmp_path)
    key = ids.chunk_key("AAPL-2026-11-04", 0)
    assert store.put(key, b"abc") is True
    assert store.put(key, b"abc") is False  # retried recorder: no-op
    with pytest.raises(BlobConflictError):
        store.put(key, b"different")
    assert store.get(key) == b"abc"


def test_list_returns_ordered_keys_and_ignores_temp_files(tmp_path):
    store = LocalBlobStore(tmp_path)
    for i in (2, 0, 1):
        store.put(ids.chunk_key("AAPL-2026-11-04", i), bytes([i]))
    (tmp_path / "audio" / "AAPL-2026-11-04" / "chunks" / "junk.tmp").write_bytes(b"x")
    keys = store.list("audio/AAPL-2026-11-04/chunks")
    assert keys == [ids.chunk_key("AAPL-2026-11-04", i) for i in range(3)]
    assert store.list("audio/NOPE") == []


def test_keys_cannot_escape_root(tmp_path):
    store = LocalBlobStore(tmp_path / "root")
    with pytest.raises(ValueError):
        store.put("../outside", b"x")


def test_sample_wav_round_trips(tmp_path, sample_wav):
    store = LocalBlobStore(tmp_path / "blobs")
    data = sample_wav.read_bytes()
    key = ids.final_audio_key("AAPL-2026-11-04")
    store.put(key, data)
    assert store.get(key) == data
