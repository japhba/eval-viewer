# eval-viewer

Unified web viewer for two eval Postgres databases, one Flask process:

| viewer | mount | DB | UI |
|--------|-------|----|----|
| **AO viewer** | `/` | `method_bench` | task x method score matrix, paged predictions/cluster table, per-cell drill-down, agent-run traces |
| **AV viewer** | `/av/` | `activation_oracles` | AVBench eval_runs overview, per-run metrics / recog / open-ended examples (with on-demand Haiku meta-judge), metric matrix, attention-figure browser |

Both originated as single-purpose `scripts/eval_viewer.py` files in the
loracles and activation_oracles_dev repos; those are deleted and this package
is the single source.

## Run

```bash
setsid nohup ./serve.sh &        # serves :8096, reads ./.env (gitignored)
```

or directly:

```bash
eval-viewer --port 8096 \
    --ao-db "$METHOD_BENCH_DB_URL" \
    --av-db "$AO_EVAL_DB_URL" \
    --access-token "$EVAL_VIEWER_TOKEN" \
    --attention-dir <reports/attention dir>
```

Both `--ao-db` / `--av-db` default to the local node-9 Postgres
(`postgresql://method_bench@node-9/{method_bench,activation_oracles}` via env
vars); startup fails fast if either DB is unreachable.

Binds 127.0.0.1 only unless `--access-token` is set (capability URL:
`/?key=<TOKEN>` converts to a cookie). cloudflared
(`~/.cloudflared/config.yml`) fronts the single port with all hostnames:

- `loracle-viewer.janbauer.cc` (alias: `viewer.janbauer.cc`) -> AO viewer at `/`
- `av-viewer.janbauer.cc` (and the legacy `ao-viewer.janbauer.cc`) -> same
  port; the app redirects non-`/av` paths on these Hosts into `/av/...`, so
  old bookmarks keep working

`ANTHROPIC_API_KEY` enables the on-demand Haiku meta-judge / summarizer
endpoints; `DOCENT_COLLECTION_ID` enables the Docent cross-links on the AO
pages. Both are optional.

## Layout

- `common.py` — shared plumbing: read-only psycopg wrapper (accepts `?` and
  `%s` placeholders), HTML/format helpers, Haiku call + tolerant JSON parse
- `app.py` — app factory: blueprints, capability-URL gate, av-viewer host redirect
- `ao.py` + `templates/*.html` — AO viewer (templates are substituted via
  `str.replace`, not Jinja — they are full of literal JS braces)
- `av.py` — AV viewer (server-rendered f-strings, unified chrome with dark mode)
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
