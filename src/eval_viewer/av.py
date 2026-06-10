"""AV viewer blueprint (mounted at `/av`): AVBench / activation_oracles eval_runs
overview, per-run metrics / recog / open-ended examples (with on-demand Haiku
meta-judge), metric matrix, and the static attention-figure browser. Ported
from activation_oracles_dev scripts/eval_viewer.py."""
from __future__ import annotations

import json
import re
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_from_directory

from . import config
from .common import Conn, _e, _fmt_num, _fmt_ts, _qs, extract_json, haiku_call

av = Blueprint("av", __name__, url_prefix="/av")

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
code { background: #e2e8f0; padding: 1px 5px; border-radius: 3px; font-size: 12px; }
details summary { cursor: pointer; color: #1d4ed8; font-size: 12px; }
details[open] summary { color: #334155; margin-bottom: 4px; }
.score-1, .score-2 { background: #fee2e2; }
.score-3 { background: #fef3c7; }
.score-4, .score-5 { background: #dcfce7; }
.runtag { display: inline-block; padding: 2px 8px; border-radius: 3px;
          font-size: 11px; font-weight: 600; color: #fff; }
.cmp-box { border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px 12px 8px;
           margin: 0 0 10px; width: 100%; min-width: 0; background: #fff; }
.cmp-box legend { font-size: 12px; color: #64748b; padding: 0 6px; }
.cmp-grid { display: grid; gap: 1px 18px;
            grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); }
.cmp-run { display: block; font-size: 13px; white-space: nowrap;
           overflow: hidden; text-overflow: ellipsis; }
tr.item-top td { border-top: 2px solid #94a3b8; }
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
  tr.item-top td { border-top-color: #475569; }
  .cmp-box { background: #1a1d23; border-color: #374151; }
  .cmp-box legend { color: #94a3b8; }
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
    <a href="/av/" class="here">AV runs</a><a href="/av/compare">Compare</a>{att}
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
                   r.step, r.examples_seen, r.label, r.created_at
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
          <td><a href="/av/compare?runs={r['run_id']}">cmp</a></td>
        </tr>""")

    if trs:
        table = f"""<table>
          <tr><th>run_id</th><th>checkpoint</th><th>source</th><th>step</th>
              <th>examples_seen</th><th>model</th><th>label</th><th>created (UTC)</th>
              <th>cmp</th></tr>
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
             f'<a href="/av/compare?runs={run_id}">compare against other runs / baselines &rarr;</a>'
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
#  Route 3: compare runs — one macro-row per eval item
# ============================================================
# Reference/baseline runs — the published Adam Karvonen verbalizers and the
# nanoNLA full fine-tune that the comparison evals (avbench_recog_violin,
# aobplus_oe) evaluate alongside our pool AOs — are flagged so the picker
# surfaces them as natural comparison targets. `\_` escapes the LIKE
# single-char wildcard; `%%` because Conn always passes a params tuple.
_BASELINE_SQL = (r"(label ILIKE '%%ref\_%%' OR label ILIKE '%%nanonla%%' "
                 r"OR checkpoint ILIKE '%%adamkarvonen%%' "
                 r"OR checkpoint ILIKE '%%nanonla%%')")


def _short_ckpt(ckpt: str) -> str:
    """Human name for a checkpoint: HF-cache snapshot paths collapse to
    `org/repo`, local ao_checkpoints paths to `<run>/<step>`, anything else
    to its last two path components. Runs are identified by THIS everywhere
    in the compare UI — run_ids are kept only as tooltips/links."""
    m = re.search(r"models--([^/]+)--([^/]+)", ckpt)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    parts = [p for p in ckpt.split("/") if p]
    if "ao_checkpoints" in parts:
        return "/".join(parts[parts.index("ao_checkpoints") + 1:]) or ckpt
    return ckpt if len(parts) <= 2 else "/".join(parts[-2:])


def _runtag(run_id: int, idx: int, base_id: int, name: str | None = None) -> str:
    """Colored chip identifying a run by its checkpoint name; the baseline
    gets a neutral chip. The run_id lives in the tooltip."""
    txt = _e(name) if name else f"#{run_id}"
    if run_id == base_id:
        return (f'<span class="runtag" style="background:#475569" '
                f'title="run #{run_id} (baseline)">{txt} &middot; base</span>')
    return (f'<span class="runtag" style="background:hsl({(idx * 67) % 360},55%,42%)" '
            f'title="run #{run_id}">{txt}</span>')


def _run_checkbox(r, selected_ids) -> str:
    ck = " checked" if r["run_id"] in selected_ids else ""
    return (f'<label class="cmp-run"><input type="checkbox" name="runs" '
            f'value="{r["run_id"]}"{ck}> {_e(_short_ckpt(r["checkpoint"]))} '
            f'<span class="muted">#{r["run_id"]} &middot; '
            f'{_e(_fmt_ts(r["created_at"]))}</span></label>')


_CLUSTER_SCORE_CACHE: dict[tuple, dict] = {}

_CLUSTER_SYSTEM = (
    "You score a CLUSTER of verbalizations from an activation-verbalizer "
    "eval: one method's answer(s) to one question, possibly sampled several "
    "times. Given the QUESTION, the CORRECT_RESPONSE, and the rollouts (each "
    "with its primary judge score, 1=worst..5=best), respond with JSON: "
    '{"cluster_score": <1-5 int>, "digest": "- ...\\n- ..."} where '
    "cluster_score judges how well the cluster AS A WHOLE captures "
    "CORRECT_RESPONSE (consistency across rollouts counts; confident "
    "hallucinations disqualify) and digest is 2-4 terse markdown bullets, "
    "each <=12 words, summarizing what the method conveyed and the most "
    "informative failure mode if any."
)


def _item_fields(rows: list[dict]) -> tuple[str, str, str]:
    """(context, verbalizer_prompt, correct_response) for one item. Prefers
    the meta_json keys persisted by the eval writer; for older rows falls
    back to parsing the rendered prompt (chat scaffold, the Layer header and
    `?` injection-placeholder lines stripped)."""
    ctx = vp = ""
    for r in rows:
        meta = json.loads(r["meta_json"] or "{}")
        ctx = ctx or (meta.get("context") or "")
        vp = vp or (meta.get("verbalizer_prompt") or "")
        if ctx and vp:
            break
    if not vp:
        parts = []
        for ln in (rows[0]["prompt"] or "").splitlines():
            s = ln.strip()
            if (not s or s in ("user", "assistant", "<think>", "</think>")
                    or s.startswith("Layer:") or set(s) <= {"?", " "}):
                continue
            parts.append(s)
        vp = " ".join(parts)
    if not ctx:
        ctx = "(not recorded — rerun the eval to persist context)"
    return ctx, vp, rows[0]["target"] or ""


def _score_chip(score) -> str:
    """Color-coded judge-score chip (1-5) prefacing a verbalization."""
    if score is None:
        return '<span class="pill">unscored</span>'
    s = min(5, max(1, int(round(float(score)))))
    return f'<span class="pill score-{s}">{_fmt_num(score, 2)}</span>'


def _long_text(text: str, head: int = 300) -> str:
    """Head shown inline, the FULL text expandable — never truncated away."""
    text = text or ""
    if len(text) <= head:
        return _e(text)
    return (f'{_e(text[:head])}&hellip; <details><summary>full text</summary>'
            f'<div class="pre">{_e(text)}</div></details>')


@av.route("/compare")
def compare():
    # ?runs= (repeat / comma-joined) selects the methods; ?eval= picks the
    # eval_name; ?all=1 unhides historical runs in the picker.
    run_ids: list[int] = []
    for v in request.args.getlist("runs"):
        for tok in v.split(","):
            if tok.strip().isdigit() and int(tok) not in run_ids:
                run_ids.append(int(tok))

    db = _conn()
    try:
        runs_all = db.query(f"""
            SELECT run_id, checkpoint, label, source, model_name, created_at,
                   {_BASELINE_SQL} AS is_baseline
            FROM eval_runs r
            ORDER BY created_at DESC
        """)
        by_id = {r["run_id"]: r for r in runs_all}
        selected = [by_id[i] for i in run_ids if i in by_id]
        run_ids = [r["run_id"] for r in selected]
        # Baseline = neutral chip + first sub-row of each item; no extra UI.
        base_id = next((r["run_id"] for r in selected if r["is_baseline"]),
                       run_ids[0] if run_ids else None)

        sel_eval = request.args.get("eval") or ""
        eval_names: list[str] = []
        sections = ""
        if len(selected) >= 2:
            ph = ",".join(["%s"] * len(run_ids))
            eval_names = [r["eval_name"] for r in db.query(
                f"SELECT DISTINCT eval_name FROM open_ended_examples "
                f"WHERE run_id IN ({ph}) ORDER BY eval_name", tuple(run_ids))]
            if sel_eval not in eval_names:
                sel_eval = eval_names[0] if eval_names else ""
            if sel_eval:
                rows = db.query(
                    f"SELECT run_id, eval_name, mode, example_idx, prompt, "
                    f"generation, target, score, judge_justification, meta_json "
                    f"FROM open_ended_examples "
                    f"WHERE run_id IN ({ph}) AND eval_name = %s "
                    f"ORDER BY example_idx, run_id, mode",
                    tuple(run_ids) + (sel_eval,))
                sections = _render_items(selected, run_ids, base_id, rows)
            else:
                sections = _empty("The selected runs have no open-ended rows.")
    finally:
        db.close()

    # Checkbox picker (baselines fully listed; other runs capped to the most
    # recent unless ?all=1 — the DB holds 1000+ historical runs). Selected
    # runs are always listed.
    show_all = request.args.get("all", "0") == "1"
    cap = None if show_all else 40
    base_runs = [r for r in runs_all if r["is_baseline"]]
    other_runs = [r for r in runs_all if not r["is_baseline"]]
    listed_other = other_runs if cap is None else (
        other_runs[:cap] + [r for r in other_runs[cap:] if r["run_id"] in run_ids])
    base_boxes = "".join(_run_checkbox(r, run_ids) for r in base_runs)
    other_boxes = "".join(_run_checkbox(r, run_ids) for r in listed_other)
    more = ("" if cap is None or len(other_runs) <= cap else
            f'<a class="muted" href="/av/compare?all=1'
            f'{"&runs=" + ",".join(map(str, run_ids)) if run_ids else ""}'
            f'{"&eval=" + sel_eval if sel_eval else ""}">'
            f'show all {len(other_runs)} runs &rarr;</a>')
    eval_opts = "".join(
        f'<option value="{_e(en)}"{" selected" if en == sel_eval else ""}>{_e(en)}</option>'
        for en in eval_names)
    eval_sel = (f'<label>eval: <select name="eval">{eval_opts}</select></label>'
                if eval_names else "")
    hidden_all = '<input type="hidden" name="all" value="1">' if show_all else ""
    picker = f"""
    <div class="controls">
      <form method="get" style="display:block; width:100%">
        {hidden_all}
        <fieldset class="cmp-box"><legend>baselines / references</legend>
          <div class="cmp-grid">{base_boxes}</div></fieldset>
        <fieldset class="cmp-box"><legend>runs {more}</legend>
          <div class="cmp-grid">{other_boxes}</div></fieldset>
        {eval_sel}
        <button type="submit">Compare</button>
      </form>
    </div>"""

    if len(selected) < 2:
        body = picker + _empty("Tick two or more runs (methods) to compare "
                               "their verbalizations item by item.")
    else:
        body = picker + sections
    return _page("Compare runs", f"<h2>Compare runs</h2>{body}")


def _render_items(selected, run_ids, base_id, rows) -> str:
    """One macro-row per eval item: context / verbalizer_prompt /
    correct_response cells span the item's block; one sub-row per method
    (run) carrying the on-demand cluster scorer; one sub-sub-row per
    verbalization with its color-coded judge score prefacing the text.
    Items are ordered by score spread across methods (most disagreement
    first)."""
    if not rows:
        return _empty("No open-ended rows for this eval on the selected runs.")
    names = {r["run_id"]: _short_ckpt(r["checkpoint"]) for r in selected}
    idx_of = {rid: i for i, rid in enumerate(run_ids)}
    method_order = ([base_id] + [r for r in run_ids if r != base_id]
                    if base_id in run_ids else list(run_ids))

    items: dict[int, dict[int, list[dict]]] = {}
    for r in rows:
        items.setdefault(r["example_idx"], {}).setdefault(r["run_id"], []).append(r)

    def _spread(by_run) -> float:
        means = []
        for rollouts in by_run.values():
            scored = [x["score"] for x in rollouts if x["score"] is not None]
            if scored:
                means.append(sum(scored) / len(scored))
        return (max(means) - min(means)) if len(means) >= 2 else 0.0

    ordered = sorted(items.items(), key=lambda kv: (-_spread(kv[1]), kv[0]))
    eval_name = rows[0]["eval_name"]

    trs = []
    for idx, by_run in ordered:
        methods = [rid for rid in method_order if rid in by_run]
        total = sum(len(by_run[rid]) for rid in methods)
        ctx, vp, correct = _item_fields(by_run[methods[0]])
        first_item_row = True
        for rid in methods:
            rollouts = sorted(by_run[rid], key=lambda x: x["mode"])
            cl_id = f"cl_{rid}_{idx}"
            method_cell = (
                f'<td rowspan="{len(rollouts)}">'
                f'{_runtag(rid, idx_of[rid], base_id, names[rid])}'
                f'<div style="margin-top:6px">'
                f'<button class="meta-btn" data-run="{rid}" '
                f'data-eval="{_e(eval_name)}" data-idx="{idx}" '
                f'data-target="{cl_id}">&#128269; cluster score</button>'
                f'<div id="{cl_id}" class="meta-out"></div></div></td>')
            first_method_row = True
            for ro in rollouts:
                tds = []
                cls = ' class="item-top"' if first_item_row else ""
                if first_item_row:
                    tds.append(f'<td class="pre" rowspan="{total}">'
                               f'{_long_text(ctx, 400)}</td>')
                    tds.append(f'<td class="pre" rowspan="{total}">{_e(vp)}</td>')
                if first_method_row:
                    tds.append(method_cell)
                mode_tag = (f' <span class="muted">{_e(ro["mode"])}</span>'
                            if len(rollouts) > 1 else "")
                just = (f' <details><summary>judge reasoning</summary>'
                        f'<div class="judge">{_e(ro["judge_justification"])}</div></details>'
                        if ro["judge_justification"] else "")
                tds.append(f'<td class="pre">{_score_chip(ro["score"])}{mode_tag} '
                           f'{_long_text(ro["generation"])}{just}</td>')
                if first_item_row:
                    tds.append(f'<td class="pre" rowspan="{total}">{_e(correct)}</td>')
                trs.append(f'<tr{cls}>{"".join(tds)}</tr>')
                first_item_row = False
                first_method_row = False

    head = ('<tr><th style="width:24%">context</th>'
            '<th style="width:16%">verbalizer_prompt</th>'
            '<th style="width:12%">method</th>'
            '<th>verbalization(s)</th>'
            '<th style="width:13%">correct_response</th></tr>')
    note = (f'<p class="muted">{len(ordered)} items &middot; '
            f'{len(run_ids)} methods &middot; ordered by score spread '
            f'(most method disagreement first)</p>')
    return note + f"<table>{head}{''.join(trs)}</table>" + _CLUSTER_JS


_CLUSTER_JS = """
<script>
(function() {
  // One-at-a-time cluster scorer (no Anthropic concurrency).
  let BUSY = false;
  document.querySelectorAll('button.meta-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (BUSY) { alert('A cluster-score call is already in flight.'); return; }
      const tgt = document.getElementById(btn.dataset.target);
      if (!tgt) return;
      if (tgt.dataset.loaded === '1') {
        tgt.style.display = (tgt.style.display === 'none' ? 'block' : 'none');
        return;
      }
      BUSY = true; btn.disabled = true; btn.textContent = '\\u23f3 scoring\\u2026';
      tgt.style.display = 'block';
      tgt.innerHTML = '<span class="muted">loading\\u2026</span>';
      try {
        const sp = new URLSearchParams({
          run_id: btn.dataset.run, eval_name: btn.dataset.eval,
          example_idx: btn.dataset.idx,
        });
        const r = await fetch('/av/api/item_cluster_score?' + sp.toString());
        const j = await r.json();
        if (j.error) {
          tgt.innerHTML = '<span style="color:#dc2626">err: ' + j.error + '</span>';
        } else {
          const cs = j.cluster_score;
          const cls = cs == null ? '' : (cs <= 2 ? 'score-1' : cs == 3 ? 'score-3' : 'score-5');
          tgt.innerHTML = '<div class="meta-card ' + cls + '">' +
            '<strong>' + (cs == null ? '?' : cs) + '/5</strong>' +
            '<div class="meta-just">' + (j.digest || '') + '</div></div>';
        }
        tgt.dataset.loaded = '1';
      } catch (e) {
        tgt.innerHTML = '<span style="color:#dc2626">fetch err: ' + e + '</span>';
      } finally {
        BUSY = false; btn.disabled = false;
        btn.textContent = '\\ud83d\\udd0d cluster score';
      }
    });
  });
})();
</script>"""


@av.route("/api/item_cluster_score")
def api_item_cluster_score():
    """On-demand Haiku score + digest for one method's verbalization cluster
    on one item. One call per click (sequential by design); cached in-process
    so repeat clicks are free until restart."""
    run_id = request.args.get("run_id", type=int)
    eval_name = request.args.get("eval_name")
    example_idx = request.args.get("example_idx", type=int)
    if run_id is None or not eval_name or example_idx is None:
        return jsonify({"error": "run_id, eval_name, example_idx required"}), 400
    key = (run_id, eval_name, example_idx)
    if key in _CLUSTER_SCORE_CACHE:
        return jsonify(_CLUSTER_SCORE_CACHE[key])

    db = _conn()
    try:
        rows = db.query(
            "SELECT mode, prompt, generation, target, score, "
            "judge_justification, meta_json FROM open_ended_examples "
            "WHERE run_id=%s AND eval_name=%s AND example_idx=%s ORDER BY mode",
            (run_id, eval_name, example_idx))
    finally:
        db.close()
    if not rows:
        return jsonify({"error": "no rows for this cluster"}), 404

    _, vp, correct = _item_fields(rows)
    # Caps are far above real AV generations (<=150 new tokens) — they only
    # guard against pathological blobs, they never bind in practice.
    parts = [f"QUESTION:\n{vp[:4000]}\n\nCORRECT_RESPONSE:\n{correct[:4000]}\n"]
    for i, r in enumerate(rows[:30]):
        sc = "-" if r["score"] is None else f"{r['score']:.0f}"
        parts.append(f"\n[rollout {i+1}, judge={sc}] {(r['generation'] or '')[:4000]}")
    if len(rows) > 30:
        parts.append(f"\n...(+{len(rows) - 30} more rollouts omitted)...")
    try:
        # Anthropic requires thinking budget >= 1024 and max_tokens above it.
        text, usage = haiku_call(_CLUSTER_SYSTEM, "".join(parts),
                                 max_tokens=2048, thinking_budget=1024)
        cluster_score = None; digest = text.strip()
        obj = extract_json(text)
        if obj:
            try:
                if obj.get("cluster_score") is not None:
                    cluster_score = min(5, max(1, int(obj["cluster_score"])))
            except (ValueError, TypeError):
                cluster_score = None
            if obj.get("digest"):
                digest = str(obj["digest"])
        out = {
            "cluster_score": cluster_score, "digest": digest,
            "n_rollouts": len(rows),
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }
        _CLUSTER_SCORE_CACHE[key] = out
        return jsonify(out)
    except Exception as exc:
        return jsonify({"error": f"haiku call failed: {exc}"}), 500


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
