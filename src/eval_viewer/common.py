"""Shared plumbing: read-only Postgres access, HTML/format helpers, Haiku calls.

The viewer never writes to either database — schema and ingestion are owned by
the producing repos (loracles `src/method_bench/db.py`, activation_oracles_dev
`nl_probes/eval_db.py`).
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import re
from urllib.parse import urlencode

import psycopg
from flask import request
from psycopg.rows import dict_row

POSTGRES_PREFIXES = ("postgresql://", "postgres://")


class Conn:
    """Read-only psycopg-v3 wrapper, one per request.

    Accepts both `?` and `%s` placeholders (the method_bench queries predate
    the Postgres move and still mix the two). Always passes a params tuple to
    psycopg, so literal `%` in SQL must be doubled (`%%`) — same contract as
    the original BenchDB."""

    def __init__(self, url: str):
        self.url = url
        if not url.startswith(POSTGRES_PREFIXES):
            raise ValueError(f"eval-viewer requires a Postgres URL, got {url!r}")
        self._conn = psycopg.connect(url, row_factory=dict_row, autocommit=True)

    def execute(self, sql: str, params: tuple = ()):
        return self._conn.execute(sql.replace("?", "%s"), params)

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(r) for r in self.execute(sql, params).fetchall()]

    def column_names(self, table: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT column_name AS name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s", (table,)).fetchall()
        return {r["name"] for r in rows}

    def close(self):
        self._conn.close()


# ---------- formatting helpers ----------
def _e(x) -> str:
    """HTML-escape a value (None -> empty string)."""
    return "" if x is None else html.escape(str(x))


def _fmt_ts(ts) -> str:
    """Unix float -> human-readable UTC string."""
    if ts is None:
        return ""
    return _dt.datetime.utcfromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_num(x, digits: int = 4) -> str:
    """Round a float for display; pass through non-numbers."""
    if x is None:
        return ""
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, (int, float)):
        return f"{float(x):.{digits}g}"
    return _e(x)


def _qs(**overrides) -> str:
    """Current query string with overrides applied; '' values drop the key."""
    args = request.args.to_dict(flat=True)
    args.pop("key", None)
    for k, v in overrides.items():
        if v in (None, ""):
            args.pop(k, None)
        else:
            args[k] = v
    return ("?" + urlencode(args)) if args else ""


# ---------- Anthropic Haiku helper ----------
def haiku_call(system: str, user: str, *, max_tokens: int,
               thinking_budget: int | None = None) -> tuple[str, object]:
    """One claude-haiku-4-5 call; returns (joined_text, usage).

    Sequential by design (no Anthropic concurrency): every caller is a
    user-clicked button or an in-process-cached endpoint, never a fan-out.
    System prompt is cached via Anthropic prompt caching."""
    import anthropic
    client = anthropic.Anthropic()
    kwargs: dict = dict(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    if thinking_budget:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
    msg = client.messages.create(**kwargs)
    text = "".join(b.text for b in msg.content
                   if getattr(b, "type", None) == "text" and hasattr(b, "text"))
    return text, msg.usage


def _json_candidates(text: str):
    """Brace-BALANCED {...} substrings (string-aware), from each of the first
    few '{'s — the old greedy regex grabbed first-{ to LAST-} and choked on
    trailing prose; non-greedy truncates at the first nested '}'."""
    starts = [i for i, c in enumerate(text) if c == "{"][:5]
    for s in starts:
        depth, in_str, esc = 0, False, False
        for j in range(s, len(text)):
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    yield text[s:j + 1]
                    break


def _repair_json(s: str) -> str:
    """Mechanical repairs for the judge's common failure modes: raw control
    characters inside string values (newlines in multi-bullet digests) and
    trailing commas."""
    out, in_str, esc = [], False, False
    for c in s:
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            elif c == "\n":
                out.append("\\n")
                continue
            elif c == "\t":
                out.append("\\t")
                continue
            elif c == "\r":
                continue
        elif c == '"':
            in_str = True
        out.append(c)
    return re.sub(r",\s*([}\]])", r"\1", "".join(out))


def extract_json(text: str) -> dict | None:
    """Tolerant JSON extraction with a repair ladder — the model may wrap the
    object in fences/prose, put raw newlines inside strings, leave trailing
    commas, or get truncated mid-string. Returns None only when nothing
    salvageable is found."""
    if not text:
        return None
    t = re.sub(r"^```(?:json)?\s*", "", text.strip())
    t = re.sub(r"\s*```$", "", t)
    candidates = list(_json_candidates(t))
    if not candidates and "{" in t:
        # truncated object (generation hit max_tokens mid-string): try closing it
        stub = t[t.index("{"):]
        candidates = [stub + '"}', stub + "}"]
    for cand in candidates:
        for attempt in (cand, _repair_json(cand)):
            try:
                obj = json.loads(attempt)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
    return None
