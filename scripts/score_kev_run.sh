#!/usr/bin/env bash
# Score one Kev checkpoint on the domain decision: serve it locally, collect predictions for
# calibration.v2 and dev_synthetic.v2, fit the temperature on calibration and score dev.
#
#   scripts/score_kev_run.sh b0_s0                      # models/checkpoints/b0_s0
#   scripts/score_kev_run.sh zeroshot_v2 released       # released Kev-0.8B (pinned revision)
#   SPLITS="dev_human" scripts/score_kev_run.sh b0_s0   # after the dev_human freeze only
#   LIMIT=5 scripts/score_kev_run.sh pipeline_check models/checkpoints/smoke_local  # path check only
#
# Outputs: outputs/predictions/domain_<run>_<split>.jsonl,
# outputs/reports/score_domain_<run>.json and outputs/figures/reliability_domain_<run>.png.
# The local machine is the canonical scoring backend for accuracy and ECE (one backend for
# every run); latency figures from this script are local-machine figures.
set -euo pipefail

RUN_ID="${1:?run id}"
SOURCE="${2:-models/checkpoints/$RUN_ID}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8009}"
SPLITS="${SPLITS:-calibration dev_synthetic}"
PRED="$ROOT/outputs/predictions"
mkdir -p "$PRED" "$ROOT/outputs/reports" "$ROOT/outputs/figures" "$ROOT/outputs/logs"

cd "$ROOT"
# The evaluation files must match the hashes in configs/train.yaml (missing counts as a failure).
.venv/bin/python -m analyst.models.kev_runs check-data

if [[ "$SOURCE" == "released" ]]; then
  SERVE_ARGS=""
else
  SERVE_ARGS="$SOURCE"
fi
# shellcheck disable=SC2086  # SERVE_ARGS is empty or one path without spaces
PORT="$PORT" DEVICE="${DEVICE:-mps}" "$ROOT/scripts/serve_kev.sh" $SERVE_ARGS \
  > "$ROOT/outputs/logs/serve_${RUN_ID}.log" 2>&1 &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT

for _ in $(seq 1 150); do
  if curl -s "http://127.0.0.1:$PORT/v1/models" > /dev/null; then break; fi
  sleep 2
done
curl -s "http://127.0.0.1:$PORT/v1/models" > /dev/null || { echo "server did not start" >&2; exit 1; }

for SPLIT in $SPLITS; do
  case "$SPLIT" in
    dev_human) FILE="data/splits/kev_domain/dev_human.v1.jsonl" ;;
    *) FILE="data/splits/kev_domain/${SPLIT}.v2.jsonl" ;;
  esac
  OUT_FILE="$PRED/domain_${RUN_ID}_${SPLIT}.jsonl"
  # decision_eval resumes an existing file; refuse unless RESUME=1, so a new run never mixes
  # with an older file of the same name (for example v1 predictions).
  if [[ -e "$OUT_FILE" && "${RESUME:-0}" != "1" ]]; then
    echo "$OUT_FILE exists; use another run id or RESUME=1 to continue it" >&2; exit 1
  fi
  KEV_BASE_URL="http://127.0.0.1:$PORT" .venv/bin/python -m analyst.evaluation.decision_eval run \
    --decision domain --file "$FILE" --out "$OUT_FILE" ${LIMIT:+--limit "$LIMIT"}
  # Provenance beside the predictions: which checkpoint, which data file, which device.
  .venv/bin/python - "$RUN_ID" "$SOURCE" "$FILE" "$OUT_FILE" "${DEVICE:-mps}" <<'PY'
import hashlib, json, sys
from datetime import UTC, datetime
from pathlib import Path

run_id, source, data, out, device = sys.argv[1:]
digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
weights = {}
if source != "released":
    for name in ("adapter_model.safetensors", "head.pt", "adapter_config.json"):
        if (Path(source) / name).exists():
            weights[name] = digest(Path(source) / name)
meta = {"run_id": run_id, "checkpoint": source, "weights_sha256": weights, "data": data,
        "data_sha256": digest(data), "predictions_sha256": digest(out), "device": device,
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds")}
Path(out).with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n")
PY
done

if [[ "$SPLITS" == *calibration* && "$SPLITS" == *dev_synthetic* ]]; then
  .venv/bin/python -m analyst.evaluation.decision_eval score --decision domain \
    --calibration "$PRED/domain_${RUN_ID}_calibration.jsonl" \
    --dev "$PRED/domain_${RUN_ID}_dev_synthetic.jsonl" \
    --figure "outputs/figures/reliability_domain_${RUN_ID}.png" \
    --out "outputs/reports/score_domain_${RUN_ID}.json"
fi
