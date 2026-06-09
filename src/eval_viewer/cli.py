"""CLI entrypoint. Designed for SSH-port-forwarded or cloudflared access:

  eval-viewer --port 8096 --access-token <TOKEN> \
      --attention-dir /workspace-vast/jbauer/activation_oracles_dev/reports/attention

  bench UI (method_bench DB)        ->  /
  AO UI (activation_oracles DB)     ->  /ao/

Serves only on 127.0.0.1 by default — tunnel back to your laptop, or put
cloudflared in front (both viewer.janbauer.cc hostnames point at this one
port; requests with an ao-viewer.* Host are redirected into /ao/)."""
from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

from . import config
from .app import create_app
from .common import Conn


def main():
    ap = argparse.ArgumentParser(
        description="Unified eval viewer: method_bench at /, Activation Oracles at /ao.")
    ap.add_argument("--bench-db", default="${METHOD_BENCH_DB_URL}",
                    help="Postgres URL for method_bench.")
    ap.add_argument("--ao-db",
                    default=os.environ.get(
                        "AO_EVAL_DB_URL",
                        "postgresql://method_bench@node-9/activation_oracles"),
                    help="Postgres URL for activation_oracles.")
    ap.add_argument("--host", default="127.0.0.1",
                    help="Bind host (default: localhost-only — tunnel via SSH).")
    ap.add_argument("--port", type=int, default=8096)
    ap.add_argument("--access-token", default=os.environ.get("EVAL_VIEWER_TOKEN"),
                    help="If set, gate all requests by capability URL "
                         "(?key=<TOKEN>). Use 'auto' to generate one.")
    ap.add_argument("--attention-dir",
                    default=os.environ.get("EVAL_VIEWER_ATTENTION_DIR"),
                    help="Directory served at /ao/attention/ (plotly HTML / PNG "
                         "from capture_attention_posthoc.py). Unset disables it.")
    args = ap.parse_args()

    config.bench_db_url = os.path.expandvars(args.bench_db)
    config.ao_db_url = os.path.expandvars(args.ao_db)
    if args.attention_dir:
        config.attention_dir = Path(args.attention_dir).resolve()
    if args.access_token == "auto":
        config.access_token = secrets.token_urlsafe(32)
    elif args.access_token:
        config.access_token = args.access_token
    if args.host != "127.0.0.1" and config.access_token is None:
        raise SystemExit(
            "Refusing to bind a non-localhost host without --access-token. "
            "Pass --access-token <TOKEN> (or 'auto' to generate one).")

    # Fail fast if either DB is unreachable.
    Conn(config.bench_db_url).close()
    Conn(config.ao_db_url).close()

    print("  unified eval viewer", flush=True)
    print(f"  bench db:  {config.bench_db_url}  ->  /", flush=True)
    print(f"  ao db:     {config.ao_db_url}  ->  /ao/", flush=True)
    if config.attention_dir:
        print(f"  attention: /ao/attention/  ->  {config.attention_dir}", flush=True)
    print(f"  on http://{args.host}:{args.port}", flush=True)
    if config.access_token:
        print("  access gate: ENABLED (capability URL)", flush=True)
        print(f"  magic URL:   http://{args.host}:{args.port}/?key={config.access_token}",
              flush=True)
        print("  share this URL only with people you trust — "
              "anyone with it has full read access.", flush=True)
    else:
        print("  access gate: DISABLED (localhost-only)", flush=True)
        print(f"  ssh tunnel from your laptop:  "
              f"ssh -L {args.port}:localhost:{args.port} <this-host>", flush=True)

    app = create_app()
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
