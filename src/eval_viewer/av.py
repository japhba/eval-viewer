"""AV viewer blueprint (mounted at `/av`): AVBench / activation_oracles eval_runs
overview, per-run metrics / recog / open-ended examples (with on-demand Haiku
meta-judge), metric matrix, and the static attention-figure browser. Ported
from activation_oracles_dev scripts/eval_viewer.py."""
from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_from_directory

from . import config
from .common import Conn, _e, _fmt_num, _fmt_ts, _qs, extract_json, haiku_call

av = Blueprint("av", __name__, url_prefix="/av")

# Per-row meta-judge cache. Keyed on (run_id, eval_name, example_idx). Server
# process lifetime; cleared on viewer restart. Mirrors the bench
# cluster_meta_score caching pattern.
_META_JUDGE_CACHE: dict[tuple, dict] = {}


# ---------- DB helper ----------
def _conn() -> Conn:
    """One read-only connection per request."""
    return Conn(config.av_db_url)


# ---------- HTML scaffold (unified chrome, matches the bench templates) ----
_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       margin: 0; line-height: 1.45; color: #1e293b; background: #fafafa; }
main { padding: 4px 24px 64px; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
header { background: #1f2937; color: white; padding: 14px 24px; display: flex;
         gap: 24px; align-items: center; flex-wrap: wrap; }
header h1 { margin: 0; font-size: 18px; font-weight: 600; }
header nav a { color: #cbd5e1; text-decoration: none; margin-right: 16px; font-size: 14px; }
header nav a:hover { color: white; text-decoration: none; }
header nav a.here { color: white; font-weight: 600; }
header nav .navsep { color: #4b5563; margin-right: 16px; }
header .dbinfo { margin-left: auto; color: #9ca3af; font-size: 12px; }
h2 { font-size: 14px; text-transform: uppercase; color: #6b7280;
     letter-spacing: 0.05em; margin: 28px 0 8px; }
table { border-collapse: collapse; width: 100%; font-size: 13px;
        background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
th, td { border: 1px solid #e2e8f0; padding: 5px 9px; text-align: left;
         vertical-align: top; }
th { background: #f1f5f9; position: sticky; top: 0; font-weight: 600; }
tr:hover td { background: #f8fafc; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.pre { white-space: pre-wrap; word-break: break-word; max-width: 520px;
         font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.controls { margin: 10px 0 4px; font-size: 13px; display: flex;
            flex-wrap: wrap; gap: 14px; align-items: center; }
.controls form { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.controls label { color: #475569; }
select, input[type=text] { font-size: 13px; padding: 3px 6px;
        border: 1px solid #cbd5e1; border-radius: 4px; }
button { font-size: 13px; padding: 3px 12px; border: 1px solid #cbd5e1;
         border-radius: 4px; background: #fff; cursor: pointer; }
button:hover { background: #f1f5f9; }
.toggle { font-weight: 600; padding: 4px 12px; border-radius: 6px;
          border: 1px solid #cbd5e1; display: inline-block; }
.toggle.on  { background: #1d4ed8; color: #fff; border-color: #1d4ed8; }
.toggle.off { background: #fff; color: #334155; }
.empty { color: #64748b; font-style: italic; padding: 28px 8px;
         border: 1px dashed #cbd5e1; background: #fff; text-align: center;
         border-radius: 6px; }
.muted { color: #64748b; font-size: 12px; }
.pill { display: inline-block; padding: 1px 7px; border-radius: 10px;
        font-size: 11px; background: #e2e8f0; color: #334155; }
.bar { display: inline-block; height: 10px; background: #93c5fd;
       border-radius: 2px; vertical-align: middle; }
code { background: #e2e8f0; padding: 1px 5px; border-radius: 3px; font-size: 12px; }
details summary { cursor: pointer; color: #1d4ed8; font-size: 12px; }
details[open] summary { color: #334155; margin-bottom: 4px; }
.score-1, .score-2 { background: #fee2e2; }
.score-3 { background: #fef3c7; }
.score-4, .score-5 { background: #dcfce7; }
.judge { background: #fff7ed; border-left: 3px solid #f59e0b; padding: 4px 8px;
         font-size: 12px; white-space: pre-wrap; word-break: break-word;
         font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.meta-btn { font-size: 11px; padding: 2px 7px; cursor: pointer;
            border: 1px solid #6366f1; color: #6366f1; background: #eef2ff;
            border-radius: 3px; }
.meta-btn:hover { background: #c7d2fe; }
.meta-btn[disabled] { opacity: 0.6; cursor: wait; }
.meta-out { margin-top: 4px; font-size: 12px; }
.meta-card { border-left: 3px solid #6366f1; background: #eef2ff;
             padding: 4px 8px; }
.meta-card.score-1 { border-left-color: #dc2626; background: #fee2e2; }
.meta-card.score-3 { border-left-color: #f59e0b; background: #fef3c7; }
.meta-card.score-5 { border-left-color: #16a34a; background: #dcfce7; }
.meta-just { white-space: pre-line; margin-top: 3px; }
@media (prefers-color-scheme: dark) {
  body { background: #0f1115; color: #e5e7eb; }
  a { color: #60a5fa; }
  h2 { color: #94a3b8; }
  table { background: #1a1d23; box-shadow: none; }
  th { background: #20242c; color: #cbd5e1; border-color: #2a2f37; }
  td { border-color: #2a2f37; }
  tr:hover td { background: #20242c; }
  .controls label { color: #94a3b8; }
  select, input[type=text], button { background: #0f1115; color: #e5e7eb; border-color: #374151; }
  button:hover { background: #20242c; }
  .toggle.off { background: #1a1d23; color: #cbd5e1; border-color: #374151; }
  .empty { background: #1a1d23; border-color: #374151; color: #94a3b8; }
  .muted { color: #94a3b8; }
  .pill, code { background: #2a2f37; color: #e5e7eb; }
  details summary { color: #93c5fd; }
  details[open] summary { color: #cbd5e1; }
  .score-1, .score-2 { background: #3b1416; }
  .score-3 { background: #2a2113; }
  .score-4, .score-5 { background: #14302a; }
  .judge { background: #2a2113; color: #fde68a; }
  .meta-btn { background: #1e1b4b; color: #a5b4fc; }
  .meta-btn:hover { background: #312e81; }
  .meta-card { background: #1e1b4b; }
  .meta-card.score-1 { background: #3b1416; }
  .meta-card.score-3 { background: #2a2113; }
  .meta-card.score-5 { background: #14302a; }
}
"""


def _page(title: str, body: str) -> str:
    """Wrap a body fragment in the full HTML document (unified chrome: same
    header bar + dark-mode palette as the bench templates)."""
    gate = " &middot; gated" if config.access_token else ""
    att = ('<a href="/av/attention/">Attention</a>'
           if config.attention_dir else "")
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)} &middot; AV viewer</title>
<style>{_STYLE}</style>
</head><body>
<header><h1>eval viewer</h1>
  <nav>
    <a href="/">AO bench</a><a href="/predictions">Predictions</a><a href="/agents">Agents</a>
    <span class="navsep">|</span>
    <a href="/av/" class="here">AV runs</a><a href="/av/matrix">AV matrix</a>{att}
  </nav>
  <span class="dbinfo">db: {_e(config.av_db_url)}{gate}</span>
</header>
<main>
{body}
</main>
</body></html>"""


def _empty(msg: str) -> str:
    return f'<div class="empty">{_e(msg)}</div>'


# ============================================================
#  Route 1: overview
# ============================================================
@av.route("/")
def overview():
    db = _conn()
    try:
        runs = db.query("""
            SELECT r.run_id, r.run_key, r.checkpoint, r.model_name, r.source,
                   r.step, r.examples_seen, r.label, r.created_at,
                   (SELECT count(*) FROM recog_examples e WHERE e.run_id = r.run_id)
                       AS n_recog,
                   (SELECT count(*) FROM open_ended_examples o WHERE o.run_id = r.run_id)
                       AS n_open,
                   (SELECT count(*) FROM metrics m WHERE m.run_id = r.run_id)
                       AS n_metrics
            FROM eval_runs r
            ORDER BY r.created_at DESC
        """)
        # latest run_id per checkpoint = the one with max(created_at).
        latest_ids = {
            row["run_id"]
            for row in db.query("""
                SELECT DISTINCT ON (checkpoint) run_id
                FROM eval_runs
                ORDER BY checkpoint, created_at DESC
            """)
        }
        checkpoints = sorted({r["checkpoint"] for r in runs})
    finally:
        db.close()

    if not runs:
        return _page("Overview", "<h2>Eval runs</h2>" + _empty(
            "No eval runs in the database yet. "
            "Ingestion / backfill has not been run."))

    sel_ckpt = request.args.get("checkpoint", "")
    latest_only = request.args.get("latest", "1") != "0"

    rows = runs
    if sel_ckpt:
        rows = [r for r in rows if r["checkpoint"] == sel_ckpt]
    if latest_only:
        rows = [r for r in rows if r["run_id"] in latest_ids]

    # checkpoint filter dropdown
    opts = ['<option value="">(all checkpoints)</option>']
    for c in checkpoints:
        sel = " selected" if c == sel_ckpt else ""
        opts.append(f'<option value="{_e(c)}"{sel}>{_e(c)}</option>')

    # latest-only toggle: a link that flips the flag, preserving other args.
    if latest_only:
        toggle = (f'<a class="toggle on" href="{_qs(latest="0")}">'
                  f'Latest checkpoint only: ON</a>')
    else:
        toggle = (f'<a class="toggle off" href="{_qs(latest="1")}">'
                  f'Latest checkpoint only: OFF</a>')

    controls = f"""
    <div class="controls">
      {toggle}
      <form method="get">
        <input type="hidden" name="latest" value="{'1' if latest_only else '0'}">
        <label>Checkpoint:
          <select name="checkpoint" onchange="this.form.submit()">
            {''.join(opts)}
          </select>
        </label>
        <noscript><button type="submit">Filter</button></noscript>
      </form>
      <span class="muted">{len(rows)} of {len(runs)} run(s) shown</span>
    </div>"""

    trs = []
    for r in rows:
        is_latest = r["run_id"] in latest_ids
        flag = ' <span class="pill">latest</span>' if is_latest else ""
        trs.append(f"""<tr>
          <td><a href="/av/run/{r['run_id']}">{r['run_id']}</a></td>
          <td>{_e(r['checkpoint'])}{flag}</td>
          <td><span class="pill">{_e(r['source'])}</span></td>
          <td class="num">{_e(r['step'])}</td>
          <td class="num">{_e(r['examples_seen'])}</td>
          <td>{_e(r['model_name'])}</td>
          <td>{_e(r['label'])}</td>
          <td>{_e(_fmt_ts(r['created_at']))}</td>
          <td class="num"><a href="/av/run/{r['run_id']}/recog">{r['n_recog']}</a></td>
          <td class="num"><a href="/av/run/{r['run_id']}/open_ended">{r['n_open']}</a></td>
          <td class="num"><a href="/av/run/{r['run_id']}">{r['n_metrics']}</a></td>
        </tr>""")

    if trs:
        table = f"""<table>
          <tr><th>run_id</th><th>checkpoint</th><th>source</th><th>step</th>
              <th>examples_seen</th><th>model</th><th>label</th><th>created (UTC)</th>
              <th>#recog</th><th>#open_ended</th><th>#metrics</th></tr>
          {''.join(trs)}
        </table>"""
    else:
        table = _empty("No runs match the current filter.")

    return _page("Overview", f"<h2>Eval runs</h2>{controls}{table}")


# ============================================================
#  Route 2: one run — metrics
# ============================================================
@av.route("/run/<int:run_id>")
def run_detail(run_id: int):
    db = _conn()
    try:
        runs = db.query("SELECT * FROM eval_runs WHERE run_id = %s", (run_id,))
        if not runs:
            abort(404)
        run = runs[0]
        metrics = db.query(
            "SELECT metric_key, value FROM metrics WHERE run_id = %s "
            "ORDER BY metric_key", (run_id,))
        n_recog = db.query(
            "SELECT count(*) AS c FROM recog_examples WHERE run_id = %s",
            (run_id,))[0]["c"]
        n_open = db.query(
            "SELECT count(*) AS c FROM open_ended_examples WHERE run_id = %s",
            (run_id,))[0]["c"]
    finally:
        db.close()

    info = f"""<table>
      <tr><th>run_id</th><td>{run['run_id']}</td></tr>
      <tr><th>run_key</th><td><code>{_e(run['run_key'])}</code></td></tr>
      <tr><th>checkpoint</th><td>{_e(run['checkpoint'])}</td></tr>
      <tr><th>model_name</th><td>{_e(run['model_name'])}</td></tr>
      <tr><th>source</th><td>{_e(run['source'])}</td></tr>
      <tr><th>step</th><td>{_e(run['step'])}</td></tr>
      <tr><th>examples_seen</th><td>{_e(run['examples_seen'])}</td></tr>
      <tr><th>wandb_run</th><td>{_e(run['wandb_run'])}</td></tr>
      <tr><th>label</th><td>{_e(run['label'])}</td></tr>
      <tr><th>created (UTC)</th><td>{_e(_fmt_ts(run['created_at']))}</td></tr>
    </table>"""

    links = (f'<div class="controls">'
             f'<a href="/av/run/{run_id}/recog">recog examples ({n_recog})</a>'
             f'<a href="/av/run/{run_id}/open_ended">open-ended examples ({n_open})</a>'
             f'</div>')

    if metrics:
        mrows = "".join(
            f'<tr><td><code>{_e(m["metric_key"])}</code></td>'
            f'<td class="num">{_fmt_num(m["value"], 6)}</td></tr>'
            for m in metrics)
        mtable = (f'<table><tr><th>metric_key</th><th>value</th></tr>'
                  f'{mrows}</table>')
    else:
        mtable = _empty("No metrics recorded for this run.")

    body = (f'<h2>Run {run_id} &mdash; {_e(run["checkpoint"])}</h2>'
            f'{info}{links}'
            f'<h2>Metrics ({len(metrics)})</h2>{mtable}')
    return _page(f"Run {run_id}", body)


# ============================================================
#  Route 3: one run — recog examples
# ============================================================
@av.route("/run/<int:run_id>/recog")
def run_recog(run_id: int):
    db = _conn()
    try:
        runs = db.query("SELECT * FROM eval_runs WHERE run_id = %s", (run_id,))
        if not runs:
            abort(404)
        run = runs[0]
        suites = [r["suite"] for r in db.query(
            "SELECT DISTINCT suite FROM recog_examples WHERE run_id = %s "
            "ORDER BY suite", (run_id,))]
        tasks = [r["task"] for r in db.query(
            "SELECT DISTINCT task FROM recog_examples WHERE run_id = %s "
            "ORDER BY task", (run_id,))]
        tiers = [r["tier"] for r in db.query(
            "SELECT DISTINCT tier FROM recog_examples WHERE run_id = %s "
            "ORDER BY tier", (run_id,))]

        sel_suite = request.args.get("suite", "")
        sel_task = request.args.get("task", "")
        sel_tier = request.args.get("tier", "")

        where = ["run_id = %s"]
        params: list = [run_id]
        if sel_suite:
            where.append("suite = %s")
            params.append(sel_suite)
        if sel_task:
            where.append("task = %s")
            params.append(sel_task)
        if sel_tier:
            where.append("tier = %s")
            params.append(sel_tier)
        clause = " AND ".join(where)

        rows = db.query(
            f"SELECT suite, task, tier, example_idx, entry_id, p_correct, "
            f"neg_log_p, logp_a, logp_b, correct_response, "
            f"incorrect_plausible_response "
            f"FROM recog_examples WHERE {clause} "
            f"ORDER BY suite, task, tier, example_idx LIMIT 2000", tuple(params))
        agg = db.query(
            f"SELECT count(*) AS n, avg(p_correct) AS mp, avg(neg_log_p) AS mnlp "
            f"FROM recog_examples WHERE {clause}", tuple(params))[0]
    finally:
        db.close()

    def _sel(name, values, cur):
        opts = [f'<option value="">(all {name})</option>']
        for v in values:
            s = " selected" if v == cur else ""
            opts.append(f'<option value="{_e(v)}"{s}>{_e(v)}</option>')
        return (f'<label>{name}: <select name="{name}" '
                f'onchange="this.form.submit()">{"".join(opts)}</select></label>')

    controls = f"""
    <div class="controls">
      <form method="get">
        {_sel("suite", suites, sel_suite)}
        {_sel("task", tasks, sel_task)}
        {_sel("tier", tiers, sel_tier)}
        <noscript><button type="submit">Filter</button></noscript>
      </form>
      <span class="muted">{agg['n']} example(s)
        &middot; mean p_correct {_fmt_num(agg['mp'])}
        &middot; mean neg_log_p {_fmt_num(agg['mnlp'])}</span>
    </div>"""

    if not rows:
        table = _empty("No recog examples for this run / filter. "
                       "(Per-example backfill may not be done yet.)")
    else:
        trs = []
        for r in rows:
            p = r["p_correct"]
            barw = int(round(max(0.0, min(1.0, float(p))) * 80)) if p is not None else 0
            trs.append(f"""<tr>
              <td>{_e(r['suite'])}</td>
              <td>{_e(r['task'])}</td>
              <td><span class="pill">{_e(r['tier'])}</span></td>
              <td class="num">{_e(r['example_idx'])}</td>
              <td>{_e(r['entry_id'])}</td>
              <td class="num">{_fmt_num(p)}
                <span class="bar" style="width:{barw}px"></span></td>
              <td class="num">{_fmt_num(r['neg_log_p'])}</td>
              <td class="num">{_fmt_num(r['logp_a'])}</td>
              <td class="num">{_fmt_num(r['logp_b'])}</td>
              <td class="pre">{_e(r['correct_response'])}</td>
              <td class="pre">{_e(r['incorrect_plausible_response'])}</td>
            </tr>""")
        cap = ('<p class="muted">Showing first 2000 rows.</p>'
               if len(rows) == 2000 else "")
        table = f"""{cap}<table>
          <tr><th>suite</th><th>task</th><th>tier</th><th>idx</th><th>entry_id</th>
              <th>p_correct</th><th>neg_log_p</th><th>logp_a</th><th>logp_b</th>
              <th>correct_response</th><th>incorrect_plausible_response</th></tr>
          {''.join(trs)}
        </table>"""

    body = (f'<h2>Run {run_id} recog &mdash; {_e(run["checkpoint"])}</h2>'
            f'<p class="muted"><a href="/av/run/{run_id}">&larr; back to run</a></p>'
            f'{controls}{table}')
    return _page(f"Run {run_id} recog", body)


# ============================================================
#  Route 4: one run — open-ended examples
# ============================================================
_SCORE_BUCKETS = {
    "": ("", None, None),  # all
    "fail": ("fail (≤2)", 0, 2),
    "mid": ("mid (=3)", 3, 3),
    "pass": ("pass (≥4)", 4, 5),
}
_SORT_OPTS = {
    "": "default (eval, idx)",
    "score_asc": "score ↑ (failures first)",
    "score_desc": "score ↓ (best first)",
}


@av.route("/run/<int:run_id>/open_ended")
def run_open_ended(run_id: int):
    db = _conn()
    try:
        runs = db.query("SELECT * FROM eval_runs WHERE run_id = %s", (run_id,))
        if not runs:
            abort(404)
        run = runs[0]
        eval_names = [r["eval_name"] for r in db.query(
            "SELECT DISTINCT eval_name FROM open_ended_examples WHERE run_id = %s "
            "ORDER BY eval_name", (run_id,))]
        modes = [r["mode"] for r in db.query(
            "SELECT DISTINCT mode FROM open_ended_examples WHERE run_id = %s "
            "ORDER BY mode", (run_id,))]

        sel_eval = request.args.get("eval_name", "")
        sel_mode = request.args.get("mode", "")
        sel_bucket = request.args.get("bucket", "")
        sel_sort = request.args.get("sort", "")
        if sel_bucket not in _SCORE_BUCKETS:
            sel_bucket = ""
        if sel_sort not in _SORT_OPTS:
            sel_sort = ""

        where = ["run_id = %s"]
        params: list = [run_id]
        if sel_eval:
            where.append("eval_name = %s"); params.append(sel_eval)
        if sel_mode:
            where.append("mode = %s"); params.append(sel_mode)
        _, lo, hi = _SCORE_BUCKETS[sel_bucket]
        if lo is not None:
            where.append("score >= %s"); params.append(lo)
        if hi is not None:
            where.append("score <= %s"); params.append(hi)
        clause = " AND ".join(where)

        order = "ORDER BY eval_name, mode, example_idx"
        if sel_sort == "score_asc":
            order = "ORDER BY score ASC NULLS FIRST, eval_name, example_idx"
        elif sel_sort == "score_desc":
            order = "ORDER BY score DESC NULLS LAST, eval_name, example_idx"

        rows = db.query(
            f"SELECT eval_name, mode, example_idx, prompt, generation, target, "
            f"score, score_kind, judge_justification, meta_json "
            f"FROM open_ended_examples WHERE {clause} "
            f"{order} LIMIT 1000", tuple(params))
        agg = db.query(
            f"SELECT count(*) AS n, avg(score) AS ms, "
            f"sum(CASE WHEN score <= 2 THEN 1 ELSE 0 END) AS n_fail, "
            f"sum(CASE WHEN score = 3 THEN 1 ELSE 0 END) AS n_mid, "
            f"sum(CASE WHEN score >= 4 THEN 1 ELSE 0 END) AS n_pass "
            f"FROM open_ended_examples WHERE {clause}", tuple(params))[0]
    finally:
        db.close()

    def _sel(name, label, values, cur):
        opts = [f'<option value="">(all {label})</option>']
        for v in values:
            s = " selected" if v == cur else ""
            shown = v if v != "" else "(none)"
            opts.append(f'<option value="{_e(v)}"{s}>{_e(shown)}</option>')
        return (f'<label>{label}: <select name="{name}" '
                f'onchange="this.form.submit()">{"".join(opts)}</select></label>')

    def _sel_kv(name, label, kv_pairs, cur):
        opts = []
        for v, txt in kv_pairs:
            s = " selected" if v == cur else ""
            opts.append(f'<option value="{_e(v)}"{s}>{_e(txt or "(all)")}</option>')
        return (f'<label>{label}: <select name="{name}" '
                f'onchange="this.form.submit()">{"".join(opts)}</select></label>')

    bucket_pairs = [(k, v[0] or "(all scores)") for k, v in _SCORE_BUCKETS.items()]
    sort_pairs = list(_SORT_OPTS.items())

    fail_pct = (100.0 * (agg['n_fail'] or 0) / agg['n']) if agg['n'] else 0.0
    controls = f"""
    <div class="controls">
      <form method="get">
        {_sel("eval_name", "eval_name", eval_names, sel_eval)}
        {_sel("mode", "mode", modes, sel_mode)}
        {_sel_kv("bucket", "judge bucket", bucket_pairs, sel_bucket)}
        {_sel_kv("sort", "sort", sort_pairs, sel_sort)}
        <noscript><button type="submit">Filter</button></noscript>
      </form>
      <span class="muted">{agg['n']} example(s)
        &middot; mean correctness {_fmt_num(agg['ms'])}
        &middot; <strong>{agg['n_fail'] or 0} fail (≤2, {fail_pct:.0f}%)</strong>
        &middot; {agg['n_mid'] or 0} mid &middot; {agg['n_pass'] or 0} pass (≥4)
      </span>
    </div>"""

    if not rows:
        table = _empty("No open-ended examples for this run / filter.")
    else:
        trs = []
        for r in rows:
            mode = r["mode"] if r["mode"] else "(none)"
            score = r["score"]
            score_cls = ""
            if score is not None:
                score_cls = f"score-{int(round(score))}"
            # Pull specificity out of meta_json if present.
            spec = ""
            try:
                meta = json.loads(r.get("meta_json") or "{}")
                if isinstance(meta, dict) and meta.get("specificity") is not None:
                    spec = _fmt_num(meta["specificity"])
            except Exception:
                pass
            gen = r["generation"] or ""
            gen_short = gen if len(gen) <= 200 else gen[:200] + "…"
            tgt = r["target"] or ""
            tgt_short = tgt if len(tgt) <= 200 else tgt[:200] + "…"
            prompt = r["prompt"] or ""

            meta_id = f"meta_{r['example_idx']}_{r['eval_name'].replace('.','_')}"
            trs.append(f"""<tr class="{score_cls}">
              <td>{_e(r['eval_name'])}</td>
              <td class="num">{_e(r['example_idx'])}</td>
              <td class="num"><strong>{_fmt_num(r['score'])}</strong></td>
              <td class="num">{spec}</td>
              <td class="pre">{_e(gen_short)}{(
                  '<details><summary>full generation</summary>'
                  f'<div class="pre">{_e(gen)}</div></details>'
                  ) if len(gen) > 200 else ''}</td>
              <td class="pre">{_e(tgt_short)}{(
                  '<details><summary>full target</summary>'
                  f'<div class="pre">{_e(tgt)}</div></details>'
                  ) if len(tgt) > 200 else ''}</td>
              <td><details><summary>judge reasoning</summary>
                  <div class="judge">{_e(r['judge_justification'] or '(none)')}</div>
                  </details>
                  <div style="margin-top:6px">
                    <button class="meta-btn" data-run="{run_id}"
                            data-eval="{_e(r['eval_name'])}"
                            data-idx="{_e(r['example_idx'])}"
                            data-target="{meta_id}">🔍 meta-judge (Haiku 4.5)</button>
                    <div id="{meta_id}" class="meta-out"></div>
                  </div>
              </td>
              <td><details><summary>prompt</summary>
                  <div class="pre">{_e(prompt)}</div></details></td>
            </tr>""")
        cap = ('<p class="muted">Showing first 1000 rows.</p>'
               if len(rows) == 1000 else "")
        table = f"""{cap}<table>
          <tr><th>eval_name</th><th>idx</th><th>corr</th><th>spec</th>
              <th>generation</th><th>target</th>
              <th>judge reasoning &amp; meta</th><th>prompt</th></tr>
          {''.join(trs)}
        </table>
        <script>
        (function() {{
          // One-at-a-time meta-judge fetch (CLAUDE.md: no Anthropic concurrency).
          let META_BUSY = false;
          document.querySelectorAll('button.meta-btn').forEach((btn) => {{
            btn.addEventListener('click', async () => {{
              if (META_BUSY) {{ alert('A meta-judge call is already in flight.'); return; }}
              const tgt = document.getElementById(btn.dataset.target);
              if (!tgt) return;
              if (tgt.dataset.loaded === '1') {{
                tgt.style.display = (tgt.style.display === 'none' ? 'block' : 'none');
                return;
              }}
              META_BUSY = true;
              btn.disabled = true; btn.textContent = '⏳ haiku thinking…';
              tgt.style.display = 'block';
              tgt.innerHTML = '<span class="muted">loading…</span>';
              try {{
                const sp = new URLSearchParams({{
                  run_id: btn.dataset.run,
                  eval_name: btn.dataset.eval,
                  example_idx: btn.dataset.idx,
                }});
                const r = await fetch('/av/api/oe_meta_score?' + sp.toString());
                const j = await r.json();
                if (j.error) {{
                  tgt.innerHTML = '<span style="color:#dc2626">err: ' + j.error + '</span>';
                }} else {{
                  const ms = j.meta_score == null ? '?' : j.meta_score;
                  const ps = j.primary_score == null ? '?' : j.primary_score;
                  const agree = j.agree == null ? '?' : (j.agree ? '✓ agree' : '✗ disagree');
                  const cls = (j.meta_score == null) ? '' :
                              (j.meta_score <= 2 ? 'score-1' :
                               j.meta_score == 3 ? 'score-3' : 'score-5');
                  tgt.innerHTML =
                    '<div class="meta-card ' + cls + '">' +
                    '<strong>meta=' + ms + '</strong> · primary=' + ps + ' · ' + agree +
                    '<div class="meta-just">' + (j.meta_justification || '') + '</div>' +
                    '</div>';
                }}
                tgt.dataset.loaded = '1';
              }} catch (e) {{
                tgt.innerHTML = '<span style="color:#dc2626">fetch err: ' + e + '</span>';
              }} finally {{
                META_BUSY = false;
                btn.disabled = false; btn.textContent = '🔍 meta-judge (Haiku 4.5)';
              }}
            }});
          }});
        }})();
        </script>"""

    body = (f'<h2>Run {run_id} open-ended &mdash; {_e(run["checkpoint"])}</h2>'
            f'<p class="muted"><a href="/av/run/{run_id}">&larr; back to run</a></p>'
            f'{controls}{table}')
    return _page(f"Run {run_id} open-ended", body)


# ============================================================
#  Route 4b: per-row meta-judge (Anthropic Haiku 4.5 second opinion)
# ============================================================
_META_SYSTEM = (
    "You are a meta-judge auditing an automated grader for an activation "
    "oracle (AO) eval. Given QUESTION asked of the AO, its AO_RESPONSE, "
    "the GROUND_TRUTH, and the PRIMARY JUDGE's score (1=worst, 5=best) "
    "+ short reasoning, produce a TERSE second-opinion JSON:\n"
    "  meta_score (1-5 int) — your own correctness call.\n"
    "  agree (true/false) — within ±1 of the primary score?\n"
    "  meta_justification — 2-4 short markdown bullets (`- ...\\n- ...`), "
    "each ≤12 words. Cover: (a) what the AO actually conveyed vs GT, "
    "(b) the most informative failure mode if any, "
    "(c) brief stance on the primary judge.\n"
    "Respond as JSON: "
    '{"meta_score": <1-5>, "agree": <bool>, "meta_justification": "- ..."}'
)


@av.route("/api/oe_meta_score")
def api_oe_meta_score():
    """On-demand Anthropic Haiku 4.5 second-opinion meta-judge for one row.

    Per CLAUDE.md no-Anthropic-concurrency rule, this fires one call per
    request — the UI button is sequential by user click, not auto-fanned out.
    Caches in-process so repeat clicks return instantly."""
    run_id = request.args.get("run_id", type=int)
    eval_name = request.args.get("eval_name")
    example_idx = request.args.get("example_idx", type=int)
    if run_id is None or not eval_name or example_idx is None:
        return jsonify({"error": "run_id, eval_name, example_idx required"}), 400

    key = (run_id, eval_name, example_idx)
    if key in _META_JUDGE_CACHE:
        return jsonify(_META_JUDGE_CACHE[key])

    db = _conn()
    try:
        rows = db.query(
            "SELECT prompt, generation, target, score, score_kind, "
            "judge_justification, meta_json "
            "FROM open_ended_examples "
            "WHERE run_id=%s AND eval_name=%s AND example_idx=%s LIMIT 1",
            (run_id, eval_name, example_idx))
    finally:
        db.close()
    if not rows:
        return jsonify({"error": "row not found"}), 404
    r = rows[0]

    user_text = (
        f"QUESTION:\n{(r['prompt'] or '')[:3000]}\n\n"
        f"AO_RESPONSE:\n{(r['generation'] or '')[:3000]}\n\n"
        f"GROUND_TRUTH:\n{(r['target'] or '')[:3000]}\n\n"
        f"PRIMARY JUDGE score ({r['score_kind'] or 'unknown_kind'}): "
        f"{r['score'] if r['score'] is not None else '(none)'}\n"
        f"PRIMARY JUDGE reasoning: {(r['judge_justification'] or '(none)')[:1500]}\n"
    )
    try:
        text, usage = haiku_call(_META_SYSTEM, user_text, max_tokens=600)
        meta_score = None; agree = None; meta_just = text.strip()
        obj = extract_json(text)
        if obj:
            try:
                if obj.get("meta_score") is not None:
                    meta_score = int(obj["meta_score"])
                if obj.get("agree") is not None:
                    agree = bool(obj["agree"])
            except (ValueError, TypeError):
                meta_score = None; agree = None
            if obj.get("meta_justification"):
                meta_just = str(obj["meta_justification"])
        out = {
            "meta_score": meta_score, "agree": agree,
            "meta_justification": meta_just,
            "primary_score": r["score"],
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }
        _META_JUDGE_CACHE[key] = out
        return jsonify(out)
    except Exception as exc:
        return jsonify({"error": f"haiku call failed: {exc}"}), 500


# ============================================================
#  Route 5: metric_key x checkpoint matrix
# ============================================================
@av.route("/matrix")
def matrix():
    db = _conn()
    try:
        # latest run per checkpoint (max created_at).
        latest = db.query("""
            SELECT DISTINCT ON (checkpoint)
                   run_id, checkpoint, created_at
            FROM eval_runs
            ORDER BY checkpoint, created_at DESC
        """)
        cells: dict[tuple[str, str], float] = {}
        metric_keys: set[str] = set()
        if latest:
            run_ids = [r["run_id"] for r in latest]
            run_to_ckpt = {r["run_id"]: r["checkpoint"] for r in latest}
            placeholders = ",".join(["%s"] * len(run_ids))
            mrows = db.query(
                f"SELECT run_id, metric_key, value FROM metrics "
                f"WHERE run_id IN ({placeholders})", tuple(run_ids))
            for m in mrows:
                ckpt = run_to_ckpt[m["run_id"]]
                cells[(m["metric_key"], ckpt)] = m["value"]
                metric_keys.add(m["metric_key"])
    finally:
        db.close()

    if not latest:
        return _page("Metric matrix", "<h2>Metric matrix</h2>" + _empty(
            "No eval runs in the database yet."))
    if not metric_keys:
        return _page("Metric matrix", "<h2>Metric matrix</h2>" + _empty(
            "No metrics recorded for any run yet."))

    checkpoints = sorted({r["checkpoint"] for r in latest})
    header = ("<tr><th>metric_key</th>"
              + "".join(f'<th>{_e(c)}</th>' for c in checkpoints)
              + "</tr>")
    trs = []
    for mk in sorted(metric_keys):
        tds = [f'<td><code>{_e(mk)}</code></td>']
        for c in checkpoints:
            v = cells.get((mk, c))
            tds.append(f'<td class="num">{_fmt_num(v, 5)}</td>')
        trs.append(f'<tr>{"".join(tds)}</tr>')

    note = (f'<p class="muted">{len(metric_keys)} metric(s) &times; '
            f'{len(checkpoints)} checkpoint(s). One column per checkpoint, '
            f'using its latest eval run.</p>')
    table = f'<table>{header}{"".join(trs)}</table>'
    return _page("Metric matrix", f"<h2>Metric matrix</h2>{note}{table}")


# ============================================================
#  Route 6: static attention-matrix files (reports/attention/*)
# ============================================================
# Configured by `--attention-dir` on the CLI; gated by the same capability
# URL as everything else. Serves the plotly HTML / PNG files produced by
# activation_oracles_dev scripts/capture_attention_posthoc.py.
@av.route("/attention/")
@av.route("/attention/<path:subpath>")
def attention(subpath: str = ""):
    """Browse + serve attention figures. Sub-paths resolve to either a
    directory listing (HTML index) or the file itself."""
    if config.attention_dir is None:
        abort(404)
    target = (config.attention_dir / subpath).resolve()
    # Refuse anything that escapes the configured root.
    if not str(target).startswith(str(config.attention_dir.resolve())):
        abort(403)
    if target.is_file():
        return send_from_directory(config.attention_dir, subpath)
    if not target.is_dir():
        abort(404)
    # Directory listing — show subdirs and files as links.
    entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    rows: list[str] = []
    if subpath:
        parent = "/".join(subpath.rstrip("/").split("/")[:-1])
        rows.append(f'<li><a href="/av/attention/{parent}">..</a></li>')
    for p in entries:
        if p.name.startswith("_") or p.name.startswith("."):
            continue
        rel = (Path(subpath) / p.name).as_posix() if subpath else p.name
        suffix = "/" if p.is_dir() else ""
        size = "" if p.is_dir() else f" <small>({p.stat().st_size//1024} KB)</small>"
        rows.append(f'<li><a href="/av/attention/{rel}{suffix}">{p.name}{suffix}</a>{size}</li>')
    body = f"<h2>attention / {subpath}</h2><ul>{''.join(rows)}</ul>"
    return _page(f"attention / {subpath}", body)


@av.app_errorhandler(404)
def _not_found(_e):
    return _page("Not found", _empty("404 — no such run or page.")), 404
