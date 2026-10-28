from datetime import UTC, date, datetime

import pytest

from simpliearn_pipeline import ids


def test_call_id_is_deterministic_per_ticker_and_day():
    morning = datetime(2026, 11, 4, 13, 0, tzinfo=UTC)
    evening = datetime(2026, 11, 4, 21, 30, tzinfo=UTC)
    assert ids.call_id("aapl", morning) == ids.call_id(" AAPL ", evening) == "AAPL-2026-11-04"
    assert ids.call_id("AAPL", date(2026, 11, 5)) != ids.call_id("AAPL", morning)


@pytest.mark.parametrize("bad", ["", "  ", "AA PL", "AAPL/../x"])
def test_invalid_ticker_rejected(bad):
    with pytest.raises(ValueError):
        ids.normalize_ticker(bad)


def test_chunk_keys_sort_in_order_and_reject_negative():
    keys = [ids.chunk_key("AAPL-2026-11-04", i) for i in (0, 2, 10)]
    assert keys == sorted(keys)
    with pytest.raises(ValueError):
        ids.chunk_key("AAPL-2026-11-04", -1)
