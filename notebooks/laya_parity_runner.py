"""One GPU queue of the Laya parity phase (run by notebooks/laya_parity_kaggle.ipynb).

    CUDA_VISIBLE_DEVICES=0 python laya_parity_runner.py PLAN DATA BASE OUT PRED RUN_ID [RUN_ID ...]

For each run: train with `laya.train.finetune` (parameters from the plan), save the checkpoint,
write a served copy of its configuration at temperature 1 (rule P4), predict every evaluation
file in the `decision_eval run` format, and mark the run DONE. A finished run is skipped; a
partial one is moved aside and rerun with the same configuration.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BATCH = 32
DEVICE = os.environ.get("LAYA_PARITY_DEVICE", "cuda")  # "mps" or "cpu" only for a local test


def now() -> str:
    """Current UTC time."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    """SHA-256 of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Rows of a JSONL file."""
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def served_config(target: Path, head_max_len: int) -> dict[str, Any]:
    """Temperature 1 and no inherited temperature buckets or binning in the served copy; the
    trained configuration is kept as rl_agent_config.trained.json."""
    path = target / "rl_agent_config.json"
    cfg = json.loads(path.read_text())
    shutil.copyfile(path, target / "rl_agent_config.trained.json")
    removed = {k: cfg.pop(k) for k in list(cfg) if "temperature_by" in k or "binning" in k}
    temps = cfg.get("temperature")
    cfg["temperature"] = [1.0] * len(temps) if isinstance(temps, list) else 1.0
    cfg["head_max_len"] = head_max_len
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    return {
        "trained_temperature": temps,
        "removed_keys": sorted(removed),
        "head_max_len": head_max_len,
    }


def predict(
    agent: Any, plan: dict[str, Any], run: dict[str, Any], data: Path, pred: Path, target: Path
) -> dict[str, int]:
    """Predictions for every evaluation file of the run's cell (dev_human tool rows sealed);
    `target` (the saved checkpoint) gets the canonical questions.json."""
    counts = {}
    canonical: dict[str, Any] = {}
    hml = run["params"]["head_max_len"]
    for item in plan["evaluation"][run["evaluation"]]:
        name = "__".join(Path(item["file"]).relative_to("data/splits").parts)
        records = read_jsonl(data / name)
        for decision in item["decisions"]:
            questions = {
                json.dumps(
                    {k: r["questions"][decision][k] for k in ("type", "instructions", "criteria")},
                    sort_keys=True,
                )
                for r in records
            }
            if len(questions) != 1:
                raise ValueError(f"{name}: the {decision} question differs between records")
            question = json.loads(questions.pop())
            canonical[decision] = question
            sealed = decision in item.get("sealed", [])
            out = pred / f"{'SEALED_' if sealed else ''}{decision}_{item['split']}.jsonl"
            rows = []
            for i in range(0, len(records), BATCH):
                chunk = records[i : i + BATCH]
                t0 = time.perf_counter()
                results = agent.predict_batch(
                    [r["state"] for r in chunk],
                    {decision: question},
                    batch_size=BATCH,
                    head_max_len=hml,
                )
                per_item = (time.perf_counter() - t0) / len(chunk)
                for r, res in zip(chunk, results, strict=True):
                    ans = res["answers"][decision]
                    rows.append(
                        {
                            "id": r["_meta"]["id"],
                            "label": r["questions"][decision]["label"],
                            "predicted": ans["choice"],
                            "probabilities": ans["probabilities"],
                            "latency_s": per_item,
                            "input_tokens": None,
                            "option_order_seed": None,
                            "backend": "kaggle-cuda-predict_batch",
                        }
                    )
            out.write_text("".join(json.dumps(x) + "\n" for x in rows))
            counts[out.name] = len(rows)
    # questions.json is a sample schema laya saves from the first training row (an augmented
    # variant here); the served copy gets the canonical questions, the trained one is kept.
    if (target / "questions.json").exists():
        shutil.copyfile(target / "questions.json", target / "questions.trained.json")
        (target / "questions.json").write_text(json.dumps(canonical, indent=2) + "\n")
    return counts


def run_one(
    plan: dict[str, Any], run: dict[str, Any], data: Path, base: Path, out: Path, pred: Path
) -> None:
    """Train, save, predict and record one run."""
    import laya
    import torch
    from laya.train import TrainConfig, finetune

    run_id = run["run_id"]
    target, run_pred = out / run_id, pred / run_id
    if (target / "DONE").exists():
        print(f"[{run_id}] already done; skipped", flush=True)
        return
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    for d in (target, run_pred):
        if d.exists():
            d.rename(d.with_name(f"{d.name}.partial-{stamp}"))
    gz = data / run["data_file"]
    if sha256(gz) != run["data_sha256"]:
        raise ValueError(f"{gz}: hash mismatch")
    scratch = Path(tempfile.gettempdir())
    train = scratch / f"{run_id}.jsonl"
    with gzip.open(gz, "rb") as src, train.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    work = scratch / f"work_{run_id}"
    shutil.rmtree(work, ignore_errors=True)
    p = run["params"]
    config = TrainConfig(
        epochs=1,  # the file holds the `epochs` Kev epoch variants in sequence (rule P2)
        encoder_lr=p["encoder_lr"],
        head_lr=p["head_lr"],
        micro_batch=p["micro_batch"],
        grad_accum=p["grad_accum"],
        loss=p["loss"],
        calib_frac=p["calib_frac"],
        head_max_len=p["head_max_len"],
        seed=run["seed"],
    )
    record: dict[str, Any] = {
        "run_id": run_id,
        "spec": run,
        "train_config": {k: getattr(config, k) for k in vars(config)},
        "base": plan["base"],
        "base_weights_sha256": sha256(base / "model.safetensors"),
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else DEVICE,
        "laya": plan["laya_version"],
        "os": platform.platform(),
        "started_utc": now(),
    }
    print(f"[{run_id}] training on {train.name} ({run['item_passes']} item passes)", flush=True)
    t0 = time.time()
    try:
        summary = finetune(str(train), str(base), str(work), config, device=DEVICE)
        record["exit"] = "ok"
    except Exception:
        record["exit"] = "failed"
        record["error"] = traceback.format_exc()
        summary = None
    record["train_seconds"] = round(time.time() - t0, 1)
    record["ended_utc"] = now()
    if record["exit"] != "ok":
        failed = out / f"{run_id}.failed-{stamp}"
        failed.mkdir(parents=True)
        (failed / "environment.json").write_text(json.dumps(record, indent=2, default=str) + "\n")
        print(f"[{run_id}] FAILED\n{record['error']}", flush=True)
        return
    shutil.rmtree(work / "checkpoint_latest", ignore_errors=True)
    shutil.copytree(work, target)
    shutil.rmtree(work, ignore_errors=True)
    train.unlink(missing_ok=True)
    record["summary"] = json.loads(json.dumps(summary, default=str))
    record["weights_sha256"] = sha256(target / "model.safetensors")
    record["served_config"] = served_config(target, p["head_max_len"])
    run_pred.mkdir(parents=True)
    agent = laya.load(str(target), device=DEVICE)
    t1 = time.time()
    record["predictions"] = predict(agent, plan, run, data, run_pred, target)
    record["predict_seconds"] = round(time.time() - t1, 1)
    del agent
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    (target / "environment.json").write_text(json.dumps(record, indent=2, default=str) + "\n")
    shutil.copyfile(target / "environment.json", run_pred / "environment.json")
    (target / "DONE").write_text(now() + "\n")
    print(
        f"[{run_id}] done: train {record['train_seconds']} s,",
        f"predict {record['predict_seconds']} s",
        flush=True,
    )


def main() -> int:
    """Run the given queue in order."""
    plan_path, data, base, out, pred, *run_ids = sys.argv[1:]
    plan = json.loads(Path(plan_path).read_text())
    specs = {r["run_id"]: r for r in plan["runs"]}
    for run_id in run_ids:
        run_one(plan, specs[run_id], Path(data), Path(base), Path(out), Path(pred))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
