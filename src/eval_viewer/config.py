"""Runtime configuration. Set once by cli.main() before the app starts."""
from __future__ import annotations

from pathlib import Path

bench_db_url: str = ""
ao_db_url: str = ""
access_token: str | None = None
attention_dir: Path | None = None
