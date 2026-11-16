#!/usr/bin/env bash
# Serve one Kev checkpoint at a pinned revision for the agent's v4 runs and the model evaluation.
#
#   scripts/serve_kev.sh                      # released Kev-0.8B at the revision in train.yaml
#   scripts/serve_kev.sh models/checkpoints/b0_s0   # a fine-tuned checkpoint (local directory)
#
# The released model is served from the Hugging Face snapshot of the exact revision pinned in
# configs/train.yaml (`init_from.revision`), never from a moving `main`. The server returns raw
# probabilities (KEV_TEMPERATURE=1.0); the client applies the temperature fitted on the
# calibration split (configs/model.yaml, `kev.temperature`), so serving and evaluation agree.
#
# Needs a Kev clone with its environment (KEV_DIR, default ~/kev-src). Environment: PORT (8009),
# DEVICE (auto; mps on Apple silicon, cuda on a GPU host, cpu otherwise), KEV_API_KEY (optional
# bearer token; set it whenever the port is reachable beyond this machine).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEV_DIR="${KEV_DIR:-$HOME/kev-src}"
PORT="${PORT:-8009}"
DEVICE="${DEVICE:-auto}"
PY="$KEV_DIR/.venv/bin/python"

if [[ $# -ge 1 ]]; then
  case "$1" in
    /*) RUN="$1" ;;
    *) RUN="$ROOT/$1" ;;
  esac
  [[ -f "$RUN/adapter_model.safetensors" ]] || { echo "no adapter in $RUN" >&2; exit 1; }
  echo "serving fine-tuned checkpoint $RUN"
else
  read -r MODEL REVISION < <("$PY" - "$ROOT/configs/train.yaml" <<'EOF'
import sys
import yaml

config = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["init_from"]
print(config["model"], config["revision"])
EOF
)
  RUN="$("$KEV_DIR/.venv/bin/hf" download "$MODEL" --revision "$REVISION" --quiet)"
  echo "serving $MODEL at revision $REVISION from $RUN"
fi

cd "$KEV_DIR"
KEV_TEMPERATURE=1.0 KEV_DTYPE=fp32 exec "$PY" -m kev.serve --run "$RUN" --port "$PORT" --device "$DEVICE"
