# SimpliEarn pipeline

Batch post-call pipeline for earnings calls: capture audio, transcribe, score sentiment, summarize,
serve the results over MCP. Self-contained: nothing here imports from `RAG/`, `sentiment/` or `scripts/`.

Status: M0 (test harness, models, storage interfaces). See the plan for later milestones.

```
cd pipeline
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check . && pytest
```

Tests run offline; any network access fails the test (see `tests/conftest.py`).
