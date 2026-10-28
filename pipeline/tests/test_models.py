from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from simpliearn_pipeline.models import Call, CallStatus, Segment, can_transition


def test_call_requires_timezone_aware_datetime():
    with pytest.raises(ValidationError):
        Call(call_id="X-2026-01-01", ticker="X", scheduled_at=datetime(2026, 1, 1))


def test_segment_end_must_not_precede_start():
    with pytest.raises(ValidationError):
        Segment(call_id="X", seg_idx=0, start_s=5, end_s=4, text="t", asr_model="m")


def test_status_transitions():
    assert can_transition(CallStatus.RECORDING, CallStatus.RECORDING)  # retry is a no-op
    assert can_transition(CallStatus.RECORDING, CallStatus.FAILED)
    assert can_transition(CallStatus.DONE, CallStatus.TRANSCRIBING)  # replay from stored audio
    assert not can_transition(CallStatus.DONE, CallStatus.RECORDING)
    assert not can_transition(CallStatus.RECORDED, CallStatus.SCHEDULED)


def test_models_are_immutable():
    call = Call(call_id="X-2026-01-01", ticker="X", scheduled_at=datetime(2026, 1, 1, tzinfo=UTC))
    with pytest.raises(ValidationError):
        call.ticker = "Y"
