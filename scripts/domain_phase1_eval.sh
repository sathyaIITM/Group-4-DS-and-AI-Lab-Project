#!/usr/bin/env bash
# Serve one Kev checkpoint locally and collect domain predictions for the calibration and
# dev-synthetic splits (phase 1). Raw probabilities are served (KEV_TEMPERATURE=1.0); the
# temperature is fitted afterwards by analyst.evaluation.domain_eval.
#
#   scripts/domain_phase1_eval.sh <name> <run>
#   scripts/domain_phase1_eval.sh zeroshot jaredpalmer/kev-0.8b
#   scripts/domain_phase1_eval.sh train250 models/checkpoints/domain_train250
#
# Needs a Kev clone with its environment (KEV_DIR, default ~/kev-src). The server needs no key
# locally. Output: outputs/predictions/domain_<name>_{calibration,dev_synthetic}.jsonl
set -euo pipefail

NAME="${1:?name}"
RUN="${2:?checkpoint or model id}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEV_DIR="${KEV_DIR:-$HOME/kev-src}"
PORT="${PORT:-8009}"
OUT="$ROOT/outputs/predictions"
mkdir -p "$OUT" "$ROOT/outputs/logs"

case "$RUN" in
  /*|jaredpalmer/*) RUN_PATH="$RUN" ;;
  *) RUN_PATH="$ROOT/$RUN" ;;
esac

(
  cd "$KEV_DIR"
  KEV_TEMPERATURE=1.0 KEV_DTYPE=fp32 exec .venv/bin/python -m kev.serve \
    --run "$RUN_PATH" --port "$PORT" --device mps
) > "$ROOT/outputs/logs/serve_${NAME}.log" 2>&1 &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT

for _ in $(seq 1 120); do  # wait for the server to answer
  if curl -s "http://127.0.0.1:$PORT/v1/models" > /dev/null; then break; fi
  sleep 2
done
curl -s "http://127.0.0.1:$PORT/v1/models" > /dev/null || { echo "server did not start" >&2; exit 1; }

cd "$ROOT"
for SPLIT in calibration dev_synthetic; do
  KEV_BASE_URL="http://127.0.0.1:$PORT" .venv/bin/python -m analyst.evaluation.domain_eval run \
    --split "$SPLIT" --out "$OUT/domain_${NAME}_${SPLIT}.jsonl"
  echo "wrote $OUT/domain_${NAME}_${SPLIT}.jsonl"
done
