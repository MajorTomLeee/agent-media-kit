# Contributing

Start with a reproducible media observation problem: source type, expected timestamp or transcript, actual result, and installed FFmpeg/Python versions. Do not upload private recordings, credentials, or copyrighted fixtures.

Run `uv sync --extra dev`, `uv run ruff check src tests`, `uv run ruff format --check src tests`, and `uv run pytest` before submitting a change. Prefer tests that generate synthetic media over large committed binaries.

This project was initially built with AI assistance under Bowie's direction. AI-assisted contributions are welcome; contributors remain responsible for understanding and verifying their changes.
