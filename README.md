# eval-viewer

Unified web viewer for two eval Postgres databases, one Flask process:

| viewer | mount | DB | UI |
|--------|-------|----|----|
| **AO viewer** | `/` | `method_bench` | task x method score matrix, paged predictions/cluster table, per-cell drill-down, agent-run traces |
| **AV viewer** | `/av/` | `activation_oracles` | AVBench eval_runs overview, per-run metrics, per-item run comparison (see below), attention-figure browser |

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

`ANTHROPIC_API_KEY` enables the on-demand Haiku scorer endpoints;
`DOCENT_COLLECTION_ID` enables the Docent cross-links on the AO pages. Both
are optional.

## Using `/av/compare` (humans and agents)

Compares what several verbalizer runs ("methods") said on the same AVBench
open-ended items, against the gold answer.

- **Auth**: hit any URL once with `?key=$EVAL_VIEWER_TOKEN` (sets a cookie),
  or send `X-Access-Token: $EVAL_VIEWER_TOKEN` per request. Base URL
  `http://127.0.0.1:8096` locally, `https://av-viewer.janbauer.cc` via the
  tunnel.
- **Open**: `/av/compare?runs=1683,1682,1681&eval=adam_hallucination` —
  `runs=` takes 2+ eval_run ids (comma or repeated; tick checkboxes on the
  page, reference checkpoints are listed first under "baselines /
  references"; `all=1` unhides historical runs), `eval=` picks one eval_name
  from the dropdown.
- **Reading the table**: one macro-row per item with columns
  `context | verbalizer_prompt | method | verbalization(s) | correct_response`.
  Within an item: one sub-row per method (baseline first, grey chip), one row
  per rollout of that method. The color-coded chip prefacing each
  verbalization is its primary judge score (red &le;2, yellow 3, green
  &ge;4); "judge reasoning" expands the judge's text. Items are ordered by
  score spread across methods, so the page starts where methods disagree
  most.
- **Cluster score**: the button in a method cell calls
  `GET /av/api/item_cluster_score?run_id=&eval_name=&example_idx=` returning
  `{"cluster_score": 1-5, "digest": "- ..."}` — Haiku judging that method's
  rollouts as a whole against `correct_response`. Cached in-process. Agents
  may call the endpoint directly (with the header auth) but must fire
  sequentially — never in parallel.
- `context`/`verbalizer_prompt` come from `meta_json` (persisted by the
  ao_dev eval writers); rows ingested before that change fall back to
  parsing the rendered prompt, with context shown as "(not recorded)".

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
