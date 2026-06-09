#!/bin/bash
# Launch the unified eval viewer on :8096. cloudflared points both
# viewer.janbauer.cc and ao-viewer.janbauer.cc at this port; requests with an
# ao-viewer Host are redirected into /ao/ by the app.
#
#   setsid nohup ./serve.sh &
#
cd "$(dirname "$0")"
set -a; source .env; set +a   # ANTHROPIC_API_KEY, DOCENT_*, METHOD_BENCH_DB_URL, EVAL_VIEWER_TOKEN
mkdir -p logs
exec /var/tmp/jbauer/venvs/evals_jan/bin/eval-viewer \
  --port 8096 \
  --bench-db "${METHOD_BENCH_DB_URL}" \
  --ao-db "${AO_EVAL_DB_URL:-postgresql://method_bench@node-9/activation_oracles}" \
  --access-token "${EVAL_VIEWER_TOKEN}" \
  --attention-dir /workspace-vast/jbauer/activation_oracles_dev/reports/attention \
  >> logs/viewer.log 2>&1
