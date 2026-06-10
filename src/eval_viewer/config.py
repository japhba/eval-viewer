"""Runtime configuration. Set once by cli.main() before the app starts."""
from __future__ import annotations

from pathlib import Path

ao_db_url: str = ""   # method_bench DB -> AO viewer at /
av_db_url: str = ""   # activation_oracles DB -> AV viewer at /av
access_token: str | None = None
attention_dir: Path | None = None
