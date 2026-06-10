#!/bin/bash
# Launch the unified eval viewer on :8096. cloudflared points
# viewer.janbauer.cc, av-viewer.janbauer.cc and ao-viewer.janbauer.cc at this
# port; requests with an av-viewer/ao-viewer Host are redirected into /av/.
#
#   setsid nohup ./serve.sh &
#
cd "$(dirname "$0")"
# loracles .env: ANTHROPIC_API_KEY, DOCENT_*, METHOD_BENCH_DB_URL.
# local .env (gitignored, plain KEY=VALUE so Flask's dotenv autoload can
# parse it too): EVAL_VIEWER_TOKEN, AO_EVAL_DB_URL.
set -a
source /workspace-vast/jbauer/loracles-worktrees/evals_jan/.env
source .env
set +a
mkdir -p logs
exec /var/tmp/jbauer/venvs/evals_jan/bin/eval-viewer \
  --port 8096 \
  --ao-db "${METHOD_BENCH_DB_URL}" \
  --av-db "${AO_EVAL_DB_URL:-postgresql://method_bench@node-9/activation_oracles}" \
  --access-token "${EVAL_VIEWER_TOKEN}" \
  --attention-dir /workspace-vast/jbauer/activation_oracles_dev/reports/attention \
  >> logs/viewer.log 2>&1
