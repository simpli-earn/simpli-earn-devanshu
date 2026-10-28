"""Plain data models shared by every stage."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CallStatus(StrEnum):
    SCHEDULED = "scheduled"
    RECORDING = "recording"
    RECORDED = "recorded"
    TRANSCRIBING = "transcribing"
    DONE = "done"
    FAILED = "failed"


# Forward moves only, plus failure from anywhere and retry from failed. A stage re-entering the state
# it is already in is allowed so a retried job is a no-op rather than an error.
_ALLOWED_TRANSITIONS: dict[CallStatus, set[CallStatus]] = {
    CallStatus.SCHEDULED: {CallStatus.RECORDING, CallStatus.RECORDED, CallStatus.FAILED},
    CallStatus.RECORDING: {CallStatus.RECORDED, CallStatus.FAILED},
    CallStatus.RECORDED: {CallStatus.TRANSCRIBING, CallStatus.FAILED},
    CallStatus.TRANSCRIBING: {CallStatus.DONE, CallStatus.FAILED},
    # Replay from stored audio: a finished call can be transcribed again.
    CallStatus.DONE: {CallStatus.TRANSCRIBING},
    CallStatus.FAILED: {CallStatus.SCHEDULED, CallStatus.RECORDING, CallStatus.TRANSCRIBING},
}


def can_transition(current: CallStatus, new: CallStatus) -> bool:
    return current == new or new in _ALLOWED_TRANSITIONS[current]


class Section(StrEnum):
    PREPARED = "prepared"
    QA = "qa"
    UNKNOWN = "unknown"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Call(_Model):
    call_id: str
    ticker: str
    scheduled_at: datetime
    source_hint: str | None = None
    status: CallStatus = CallStatus.SCHEDULED
    strategy_used: str | None = None
    failure_reason: str | None = None

    @model_validator(mode="after")
    def _tz_aware(self):
        if self.scheduled_at.tzinfo is None:
            raise ValueError("scheduled_at must be timezone-aware")
        return self


class AudioFile(_Model):
    call_id: str
    kind: str = Field(pattern="^(chunk|final)$")
    chunk_idx: int = Field(ge=0)  # 0 for the final file
    blob_key: str
    sha256: str
    size_bytes: int = Field(ge=0)
    duration_s: float | None = None


class Segment(_Model):
    call_id: str
    seg_idx: int = Field(ge=0)
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    text: str
    speaker: str | None = None
    section: Section = Section.UNKNOWN
    asr_model: str

    @model_validator(mode="after")
    def _ordered(self):
        if self.end_s < self.start_s:
            raise ValueError("end_s must be >= start_s")
        return self
