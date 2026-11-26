#!/usr/bin/env bash
# Milestone 5 test runs: the frozen test set, 3 runs per configuration, then scoring.
#
#   scripts/run_m5_test_ladder.sh plan            # checks and prints every command; no model call
#   scripts/run_m5_test_ladder.sh run --yes       # runs them (spends cloud and Jev credit)
#   scripts/run_m5_test_ladder.sh score           # scores and compares what has been run
#
# Configurations (docs: common context Section 8; report Section 4.4):
#   v2m4  v2 at the Milestone 4 commit a2c8c7d, on the 40 new test items only (the 60
#         continuity items reuse the Milestone 4 runs, outputs/predictions/final_test_v2_r*.jsonl)
#   v2    v2 at the Milestone 5 freeze (HEAD), on all 100 test items
#   v3    v3 at the freeze (pinned GEPA intent prompt, configs/model.yaml prompt_pins)
#   v4    v4 at the freeze (Kev ep3 on the domain, served locally on KEV_PORT)
#
# Measured on the Milestone 4 test runs (outputs/predictions/final_test_v*_r*.jsonl): USD 0.009 to
# 0.013 and 6 to 7 s per question with one worker. Estimate for this ladder: 1,020 questions,
# about USD 9-13 and 2 hours. --workers 1 as in Milestone 4, so latency stays comparable.
#
# Requirements: run from the repository root on the freeze commit with a clean tracked tree;
# `set -a; source .env; set +a` (Vertex project, TYPESAFE_API_KEY); the test files present and
# validated, their hashes equal to configs/evaluation.yaml; for v4 the Kev server running
# (scripts/serve_kev.sh models/checkpoints/ep3). Scorer v3 applies to the runs of this commit;
# the v2m4 runs come from the Milestone 4 code, which records no plan fields, so they are scored
# with scorer v2 only (compared with v2 under scorer v2).
set -euo pipefail

MODE="${1:?plan | run | score}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
RUNS="${RUNS:-1 2 3}"
KEV_PORT="${KEV_PORT:-8009}"
M4_COMMIT="a2c8c7d8ecde703002dbaa02e499bd71cb1499df"
M4_TREE="${M4_TREE:-$ROOT/../worktrees/m4-baseline}"
OLD="data/eval/e2e_test.v1.jsonl"
NEW="data/eval/e2e_test_ext.v1.jsonl"
PRED="outputs/predictions"
REP="outputs/reports"
mkdir -p "$PRED" "$REP" outputs/logs

say() { printf '%s\n' "$*"; }
run() { if [[ "$MODE" == "plan" ]]; then say "  $*"; else say "+ $*"; "$@"; fi; }

preflight() {
  local fail=1; [[ "$MODE" == "plan" ]] && fail=0
  if [[ ! -f "$OLD" || ! -f "$NEW" ]]; then
    say "WARNING: missing test files ($OLD, $NEW)"; [[ $fail == 1 ]] && exit 1; return 0
  fi
  if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    say "WARNING: the tracked tree has changes: commit the freeze first"; [[ $fail == 1 ]] && exit 1
  fi
  "$PY" - "$OLD" "$NEW" <<'EOF'
import hashlib, json, sys, yaml
config = yaml.safe_load(open("configs/evaluation.yaml"))
recorded = json.dumps(config)
for path in sys.argv[1:]:
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    rows = [json.loads(l) for l in open(path) if l.strip()]
    unvalidated = [r["id"] for r in rows if not r.get("validated")]
    print(f"{path}: {len(rows)} items, sha256 {digest[:16]}, unvalidated {len(unvalidated)}")
    if digest not in recorded:
        sys.exit(f"{path}: hash not recorded in configs/evaluation.yaml")
    if unvalidated:
        sys.exit(f"{path}: unvalidated items {unvalidated[:5]}")
EOF
  say "freeze commit: $(git rev-parse --short HEAD)"
}

kev_up() {
  curl -s -o /dev/null -m 3 "http://127.0.0.1:${KEV_PORT}/" || {
    say "Kev server not reachable on :${KEV_PORT}; start scripts/serve_kev.sh models/checkpoints/ep3"
    return 1
  }
}

m4_tree() {
  if [[ ! -d "$M4_TREE" ]]; then
    run git worktree add --detach "$M4_TREE" "$M4_COMMIT"
    if [[ "$MODE" != "plan" ]]; then
      for f in "$ROOT"/data/processed/*; do ln -sf "$f" "$M4_TREE/data/processed/"; done
      ln -sf "$ROOT/.venv" "$M4_TREE/.venv"
    fi
  fi
}

ladder() {
  preflight
  if [[ "$MODE" == "run" && "${2:-}" != "--yes" ]]; then
    say "live runs spend credit: add --yes"; exit 1
  fi
  say "== v2m4 (commit a2c8c7d, new items only)"
  m4_tree
  for r in $RUNS; do
    run bash -c "cd '$M4_TREE' && PYTHONPATH=src:. '$PY' -m analyst.evaluation.e2e_eval run --live --yes \
      --workers 1 --version v2 --experiment m5_test_v2m4_r$r --member T3 --set '$ROOT/$NEW' \
      --out '$ROOT/$PRED/m5_test_v2m4_r$r.jsonl'"
  done
  for v in v2 v3 v4; do
    say "== $v (freeze commit, all 100 items)"
    if [[ "$v" == "v4" && "$MODE" == "run" ]]; then kev_up; fi
    for r in $RUNS; do
      run env PYTHONPATH=src:. "$PY" -m analyst.evaluation.e2e_eval run --live --yes --workers 1 \
        --version "$v" --experiment "m5_test_${v}_r$r" --member T3 --set "$OLD" "$NEW" \
        --out "$PRED/m5_test_${v}_r$r.jsonl"
    done
  done
}

score() {
  local files
  for v in v2 v3 v4; do
    files=$(ls "$PRED"/m5_test_"$v"_r*.jsonl 2>/dev/null || true)
    [[ -n "$files" ]] || continue
    for s in v2 v3; do
      # shellcheck disable=SC2086
      run env PYTHONPATH=src:. "$PY" -m analyst.evaluation.e2e_eval score --scorer "$s" \
        --predictions $files --gold "$OLD" "$NEW" --out "$REP/m5_test_${v}_scorer_$s.json"
    done
  done
  # Continuity set (60 items): Milestone 4 v2 runs on validated gold, scorer v2 only.
  run env PYTHONPATH=src:. "$PY" -m analyst.evaluation.e2e_eval score --scorer v2 \
    --predictions "$PRED"/final_test_v2_r{1,2,3}.jsonl --gold "$OLD" \
    --out "$REP/m5_m4_v2_validated_gold_scorer_v2.json"
  # Paired comparisons on the same items.
  pair() {  # name scorer a-glob b-glob [extra args]
    local a b; a=$(ls $3 2>/dev/null || true); b=$(ls $4 2>/dev/null || true)
    [[ -n "$a" && -n "$b" ]] || return 0
    # shellcheck disable=SC2086
    run env PYTHONPATH=src:. "$PY" -m analyst.evaluation.e2e_eval compare --scorer "$2" \
      --a $a --b $b --gold "$OLD" "$NEW" --out "$REP/m5_compare_$1.json" "${@:5}"
  }
  pair v2_vs_v2m4_new_items v2 "$PRED/m5_test_v2m4_r*.jsonl" "$PRED/m5_test_v2_r*.jsonl" --only "$NEW"
  pair v3_vs_v2 v3 "$PRED/m5_test_v2_r*.jsonl" "$PRED/m5_test_v3_r*.jsonl"
  pair v4_vs_v3 v3 "$PRED/m5_test_v3_r*.jsonl" "$PRED/m5_test_v4_r*.jsonl"
  pair v4_vs_v2 v3 "$PRED/m5_test_v2_r*.jsonl" "$PRED/m5_test_v4_r*.jsonl"
}

case "$MODE" in
  plan | run) ladder "$@" ;;
  score) score ;;
  *) say "mode must be plan, run or score"; exit 1 ;;
esac
