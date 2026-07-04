# rewind (server)

FastAPI backend for REWIND: a recording proxy plus the timeline and fork/replay
API over an append-only SQLite event log. See the [project README](../README.md)
for the full picture.

```bash
pip install -e ".[dev]"
uvicorn rewind.app:app --reload   # :8000, mock upstream by default
pytest -q
```
