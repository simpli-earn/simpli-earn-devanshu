from datetime import UTC, datetime

import pytest

from simpliearn_pipeline import ids
from simpliearn_pipeline.models import AudioFile, Call, CallStatus, Section, Segment
from simpliearn_pipeline.storage.db import AudioConflictError, InvalidTransitionError, SqliteRepository

WHEN = datetime(2026, 11, 4, 21, 0, tzinfo=UTC)
CID = ids.call_id("AAPL", WHEN)


@pytest.fixture
def repo():
    repository = SqliteRepository()
    yield repository
    repository.close()


@pytest.fixture
def call(repo):
    return repo.schedule_call(Call(call_id=CID, ticker="AAPL", scheduled_at=WHEN, source_hint="ir-page"))


def _chunk(idx, sha="a" * 64):
    return AudioFile(
        call_id=CID, kind="chunk", chunk_idx=idx, blob_key=ids.chunk_key(CID, idx), sha256=sha, size_bytes=3
    )


def test_schedule_call_is_idempotent(repo, call):
    again = repo.schedule_call(Call(call_id=CID, ticker="AAPL", scheduled_at=WHEN, source_hint="other"))
    assert again == call  # the first write wins; a duplicate schedule request changes nothing
    assert again.source_hint == "ir-page"


def test_status_machine_and_failure_reason(repo, call):
    repo.set_status(CID, CallStatus.RECORDING, strategy_used="replay_download")
    repo.set_status(CID, CallStatus.RECORDING)  # retry, no-op
    failed = repo.set_status(CID, CallStatus.FAILED, failure_reason="stream blocked")
    assert failed.failure_reason == "stream blocked"
    assert failed.strategy_used == "replay_download"
    resumed = repo.set_status(CID, CallStatus.RECORDING)
    assert resumed.failure_reason is None
    with pytest.raises(InvalidTransitionError):
        repo.set_status(CID, CallStatus.DONE)
    with pytest.raises(KeyError):
        repo.set_status("NOPE-2026-01-01", CallStatus.RECORDING)


def test_audio_upsert_is_idempotent_and_detects_conflicts(repo, call):
    assert repo.upsert_audio_file(_chunk(0)) is True
    assert repo.upsert_audio_file(_chunk(0)) is False
    with pytest.raises(AudioConflictError):
        repo.upsert_audio_file(_chunk(0, sha="b" * 64))
    repo.upsert_audio_file(_chunk(1))
    assert [a.chunk_idx for a in repo.list_audio_files(CID, "chunk")] == [0, 1]
    assert repo.list_audio_files(CID, "final") == []


def test_replace_segments_swaps_the_whole_set(repo, call):
    def seg(i, text):
        return Segment(
            call_id=CID, seg_idx=i, start_s=i, end_s=i + 1, text=text, section=Section.QA, asr_model="m"
        )

    repo.replace_segments(CID, [seg(0, "a"), seg(1, "b"), seg(2, "c")])
    repo.replace_segments(CID, [seg(0, "x"), seg(1, "y")])  # reprocessing with a shorter result
    assert [s.text for s in repo.get_segments(CID)] == ["x", "y"]
