"""Repository interface plus a SQLite implementation used by tests and local runs.

The production implementation (Postgres on the existing Supabase project, tables prefixed
`pipeline_`) lands with M1, when the first stage writes real results. Both satisfy `Repository`.
"""

import sqlite3
from datetime import datetime
from typing import Protocol

from simpliearn_pipeline.models import (
    AudioFile,
    Call,
    CallStatus,
    Section,
    Segment,
    can_transition,
)


class InvalidTransitionError(Exception):
    pass


class AudioConflictError(Exception):
    """The same chunk was recorded twice with different bytes."""


class Repository(Protocol):
    def schedule_call(self, call: Call) -> Call:
        """Insert the call, or return the existing one with the same call_id (idempotent)."""

    def get_call(self, call_id: str) -> Call | None: ...

    def set_status(
        self,
        call_id: str,
        status: CallStatus,
        *,
        strategy_used: str | None = None,
        failure_reason: str | None = None,
    ) -> Call: ...

    def upsert_audio_file(self, audio: AudioFile) -> bool:
        """Return True if inserted, False if an identical row already existed."""

    def list_audio_files(self, call_id: str, kind: str | None = None) -> list[AudioFile]: ...

    def replace_segments(self, call_id: str, segments: list[Segment]) -> None:
        """Atomically swap in a full set of segments, so reprocessing never leaves a mix."""

    def get_segments(self, call_id: str) -> list[Segment]: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline_calls (
    call_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    source_hint TEXT,
    status TEXT NOT NULL,
    strategy_used TEXT,
    failure_reason TEXT
);
CREATE TABLE IF NOT EXISTS pipeline_audio_files (
    call_id TEXT NOT NULL REFERENCES pipeline_calls(call_id),
    kind TEXT NOT NULL,
    chunk_idx INTEGER NOT NULL,
    blob_key TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    duration_s REAL,
    PRIMARY KEY (call_id, kind, chunk_idx)
);
CREATE TABLE IF NOT EXISTS pipeline_transcript_segments (
    call_id TEXT NOT NULL REFERENCES pipeline_calls(call_id),
    seg_idx INTEGER NOT NULL,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    text TEXT NOT NULL,
    speaker TEXT,
    section TEXT NOT NULL,
    asr_model TEXT NOT NULL,
    PRIMARY KEY (call_id, seg_idx)
);
"""


class SqliteRepository:
    def __init__(self, path: str = ":memory:"):
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    # calls

    def schedule_call(self, call: Call) -> Call:
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO pipeline_calls "
                "(call_id, ticker, scheduled_at, source_hint, status) VALUES (?, ?, ?, ?, ?)",
                (
                    call.call_id,
                    call.ticker,
                    call.scheduled_at.isoformat(),
                    call.source_hint,
                    call.status.value,
                ),
            )
        stored = self.get_call(call.call_id)
        assert stored is not None
        return stored

    def get_call(self, call_id: str) -> Call | None:
        row = self._db.execute("SELECT * FROM pipeline_calls WHERE call_id = ?", (call_id,)).fetchone()
        if row is None:
            return None
        return Call(
            call_id=row["call_id"],
            ticker=row["ticker"],
            scheduled_at=datetime.fromisoformat(row["scheduled_at"]),
            source_hint=row["source_hint"],
            status=CallStatus(row["status"]),
            strategy_used=row["strategy_used"],
            failure_reason=row["failure_reason"],
        )

    def set_status(
        self,
        call_id: str,
        status: CallStatus,
        *,
        strategy_used: str | None = None,
        failure_reason: str | None = None,
    ) -> Call:
        current = self.get_call(call_id)
        if current is None:
            raise KeyError(call_id)
        if not can_transition(current.status, status):
            raise InvalidTransitionError(f"{call_id}: {current.status.value} -> {status.value}")
        with self._db:
            self._db.execute(
                "UPDATE pipeline_calls SET status = ?, "
                "strategy_used = COALESCE(?, strategy_used), failure_reason = ? WHERE call_id = ?",
                (
                    status.value,
                    strategy_used,
                    failure_reason if status == CallStatus.FAILED else None,
                    call_id,
                ),
            )
        updated = self.get_call(call_id)
        assert updated is not None
        return updated

    # audio

    def upsert_audio_file(self, audio: AudioFile) -> bool:
        existing = self._db.execute(
            "SELECT sha256 FROM pipeline_audio_files WHERE call_id = ? AND kind = ? AND chunk_idx = ?",
            (audio.call_id, audio.kind, audio.chunk_idx),
        ).fetchone()
        if existing is not None:
            if existing["sha256"] != audio.sha256:
                raise AudioConflictError(f"{audio.call_id} {audio.kind} {audio.chunk_idx}: sha256 differs")
            return False
        with self._db:
            self._db.execute(
                "INSERT INTO pipeline_audio_files "
                "(call_id, kind, chunk_idx, blob_key, sha256, size_bytes, duration_s) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    audio.call_id,
                    audio.kind,
                    audio.chunk_idx,
                    audio.blob_key,
                    audio.sha256,
                    audio.size_bytes,
                    audio.duration_s,
                ),
            )
        return True

    def list_audio_files(self, call_id: str, kind: str | None = None) -> list[AudioFile]:
        query = "SELECT * FROM pipeline_audio_files WHERE call_id = ?"
        params: list = [call_id]
        if kind is not None:
            query += " AND kind = ?"
            params.append(kind)
        rows = self._db.execute(query + " ORDER BY kind, chunk_idx", params).fetchall()
        return [AudioFile(**{k: row[k] for k in row.keys()}) for row in rows]

    # transcript

    def replace_segments(self, call_id: str, segments: list[Segment]) -> None:
        with self._db:  # one transaction: delete + insert commit together or not at all
            self._db.execute("DELETE FROM pipeline_transcript_segments WHERE call_id = ?", (call_id,))
            self._db.executemany(
                "INSERT INTO pipeline_transcript_segments "
                "(call_id, seg_idx, start_s, end_s, text, speaker, section, asr_model) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (call_id, s.seg_idx, s.start_s, s.end_s, s.text, s.speaker, s.section.value, s.asr_model)
                    for s in segments
                ],
            )

    def get_segments(self, call_id: str) -> list[Segment]:
        rows = self._db.execute(
            "SELECT * FROM pipeline_transcript_segments WHERE call_id = ? ORDER BY seg_idx", (call_id,)
        ).fetchall()
        return [
            Segment(**{**{k: row[k] for k in row.keys()}, "section": Section(row["section"])}) for row in rows
        ]
