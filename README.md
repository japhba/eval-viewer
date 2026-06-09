# eval-viewer

Unified web viewer for the two eval Postgres databases on node-9:

| mount  | DB                   | UI |
|--------|----------------------|----|
| `/`    | `method_bench`       | task x method matrix, paged predictions/cluster table, per-cell drill-down, agent-run traces (ported from loracles `scripts/eval_viewer.py`) |
| `/ao/` | `activation_oracles` | eval_runs overview, per-run metrics / recog / open-ended examples, metric matrix, attention-figure browser (ported from activation_oracles_dev `scripts/eval_viewer.py`) |

Both old single-purpose viewers are deprecated and deleted from their repos;
this package is the single source.

## Run

```bash
setsid nohup ./serve.sh &        # serves :8096, reads ./.env (gitignored)
```

or directly:

```bash
eval-viewer --port 8096 \
    --bench-db "$METHOD_BENCH_DB_URL" \
    --ao-db "$AO_EVAL_DB_URL" \
    --access-token "$EVAL_VIEWER_TOKEN" \
    --attention-dir /workspace-vast/jbauer/activation_oracles_dev/reports/attention
```

Binds 127.0.0.1 only unless `--access-token` is set (capability URL:
`/?key=<TOKEN>` converts to a cookie). cloudflared
(`~/.cloudflared/config.yml`) fronts the single port with both hostnames:

- `viewer.janbauer.cc` -> bench UI at `/`
- `ao-viewer.janbauer.cc` -> same port; the app redirects non-`/ao` paths on
  this Host into `/ao/...`, so old bookmarks keep working

`ANTHROPIC_API_KEY` enables the on-demand Haiku meta-judge / summarizer
endpoints; `DOCENT_COLLECTION_ID` enables the Docent cross-links on the bench
pages. Both are optional.

## Layout

- `common.py` — shared plumbing: read-only psycopg wrapper (accepts `?` and
  `%s` placeholders), HTML/format helpers, Haiku call + tolerant JSON parse
- `app.py` — app factory: blueprints, capability-URL gate, ao-viewer host redirect
- `bench.py` + `templates/*.html` — method_bench UI (templates are substituted
  via `str.replace`, not Jinja — they are full of literal JS braces)
- `ao.py` — AO UI (server-rendered f-strings, unified chrome with dark mode)
- `cli.py` — argparse entrypoint (`eval-viewer`)

The viewer never writes to either DB. Schema + ingestion live with the
producers: loracles `src/method_bench/db.py` and activation_oracles_dev
`nl_probes/eval_db.py`.

## Install into a repo env

Both loracles (evals_jan) and activation_oracles_dev depend on this package
via an editable path source in their `pyproject.toml`:

```toml
[tool.uv.sources]
eval-viewer = { path = "/workspace-vast/jbauer/eval-viewer", editable = true }
```

so `uv sync` keeps it installed. On a fresh box, check this repo out at the
same path (or adjust the source) before syncing.
