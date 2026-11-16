"""Kev-0.8B training runs: the sweep plan, train-size subsets and the model registry.

    # the run plan (one command per run) from configs/train.yaml, as JSON and shell lines
    python -m analyst.models.kev_runs plan [--data <train file>] [--out <plan.json>]
    # train-size subsets (250, 500, 1000) of the training file, stratified by label
    python -m analyst.models.kev_runs subsets [--data <train file>]
    # after a run: add or update its entry in models/registry.json
    python -m analyst.models.kev_runs register <run dir> --run-id b0_s0 \
        [--drive-path Group4/checkpoints/b0_s0] [--scores <decision_eval score json>]

The registry entry follows the T3 brief (Section 5, Artifacts): run id, base, `init_from`,
data hash, flags, seed, temperature, scores, SHA-256 of the adapter and head, Drive path,
and the gradient-norm summary that kev.train writes (clipped steps per epoch).
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from analyst.decisions.phase1 import read_jsonl, subsample, write_jsonl

ROOT = Path(__file__).resolve().parents[3]
TRAIN_CONFIG = ROOT / "configs" / "train.yaml"
REGISTRY = ROOT / "models" / "registry.json"
WEIGHT_FILES = ("adapter_model.safetensors", "head.pt")


def load_config(path: Path = TRAIN_CONFIG) -> dict[str, Any]:
    config: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return config


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------- plan


class RunSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    factor: str
    data: str
    lr: float
    epochs: int
    batch: int
    accum: int
    lora: int
    lora_targets: str
    dtype: str
    weights_dtype: str
    max_state: int
    seed: int
    device: str
    init_from: str | None
    base: str
    base_revision: str

    def command(self) -> str:
        parts = [
            "python -m kev.train",
            f"--data {self.data}",
            f"--base {self.base}",
            f"--base_revision {self.base_revision}",
        ]
        if self.init_from:
            parts.append(f"--init_from {self.init_from}")
        parts += [
            f"--lr {self.lr:g}",
            f"--epochs {self.epochs}",
            f"--batch {self.batch}",
            f"--accum {self.accum}",
            f"--lora {self.lora}",
            f"--lora_targets {self.lora_targets}",
            f"--dtype {self.dtype}",
            f"--weights_dtype {self.weights_dtype}",
            f"--max_state {self.max_state}",
            f"--seed {self.seed}",
            f"--device {self.device}",
            f"--out runs/{self.run_id}",
        ]
        return " ".join(parts)


def _subset_path(config: dict[str, Any], train: Path, size: int) -> str:
    return str(Path(config["data"]["subsets_dir"]) / f"{train.stem}.n{size}.jsonl")


def plan(config: dict[str, Any], train: Path | None = None) -> list[RunSpec]:
    """B0, then one factor at a time. Runs that only differ in seed share a factor name.
    The seed runs of the best setting are added once the sweep has chosen it."""
    train = train or Path(config["data"]["train"])
    b0 = dict(config["b0"])
    common = {
        "base": config["base"]["model"],
        "base_revision": config["base"]["revision"],
        "data": str(train),
    }
    init_from = config["init_from"]["model"]
    runs: list[RunSpec] = []

    def add(run_id: str, factor: str, from_base: bool = False, **changes: Any) -> None:
        values = {**b0, **common, **changes}
        runs.append(
            RunSpec(
                run_id=run_id, factor=factor, init_from=None if from_base else init_from, **values
            )
        )

    add("b0_s0", "b0")
    sweep = config["sweep"]
    for lr in sweep["lr"]:
        if lr != b0["lr"]:
            add(f"lr{lr:g}", "lr", lr=lr)
    for epochs in sweep["epochs"]:
        if epochs != b0["epochs"]:
            add(f"ep{epochs}", "epochs", epochs=epochs)
    for size in sweep["train_size"]:
        if size != "full":
            add(f"n{size}", "train_size", data=_subset_path(config, train, int(size)))
    for seed in sweep["seeds"]:
        if seed != b0["seed"]:
            add(f"b0_s{seed}", "seed", seed=seed)
    for rank in sweep["from_base"]["lora"]:
        add(f"base_r{rank}", "from_base_lora", from_base=True, lora=rank)
    ids = [r.run_id for r in runs]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate run ids in the plan: {ids}")
    return runs


def write_subsets(config: dict[str, Any], train: Path | None = None) -> dict[str, Any]:
    """Nested, label-stratified subsets of the training file; returns their hashes."""
    train = train or Path(config["data"]["train"])
    records = list(read_jsonl(train))
    out: dict[str, Any] = {}
    for size in config["sweep"]["train_size"]:
        if size == "full" or int(size) >= len(records):
            continue
        path = Path(_subset_path(config, train, int(size)))
        write_jsonl(path, subsample(records, int(size), seed=0))
        out[str(path)] = {"records": int(size), "sha256": sha256_file(path)}
    return out


# ---------------------------------------------------------------------------- registry


class RegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    created_at: str
    kev_commit: str | None
    base: str | None
    base_revision: str | None
    init_from: str | None
    data: str | None
    data_sha256: str | None
    flags: dict[str, Any]
    seed: int | None
    weights_sha256: dict[str, str]
    grad_norm: list[dict[str, Any]] = Field(default_factory=list)
    wall_seconds: float | None = None
    device: str | None = None
    temperature: float | None = None
    scores: dict[str, Any] = Field(default_factory=dict)
    drive_path: str | None = None
    notes: str = ""


def entry_from_run(run_dir: Path, run_id: str, kev_commit: str | None = None) -> RegistryEntry:
    """Read what kev.train saved in `run_dir` (training_config.json, training_metrics.json,
    the adapter and the head) into a registry entry."""
    config = json.loads((run_dir / "training_config.json").read_text())
    args: dict[str, Any] = config.get("args", {})
    metrics_path = run_dir / "training_metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    data = args.get("data") or None
    data_path = Path(data) if data else None
    weights = {
        name: sha256_file(run_dir / name) for name in WEIGHT_FILES if (run_dir / name).exists()
    }
    if not weights:
        raise FileNotFoundError(f"{run_dir} holds none of {WEIGHT_FILES}")
    return RegistryEntry(
        run_id=run_id,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        kev_commit=kev_commit,
        base=args.get("base"),
        base_revision=config.get("base_revision") or args.get("base_revision"),
        init_from=args.get("init_from") or None,
        data=data,
        data_sha256=sha256_file(data_path) if data_path and data_path.exists() else None,
        flags={k: v for k, v in args.items() if k not in {"data", "out", "base", "init_from"}},
        seed=args.get("seed"),
        weights_sha256=weights,
        grad_norm=metrics.get("grad_norm", []),
        wall_seconds=metrics.get("wall_seconds"),
        device=metrics.get("device"),
    )


def load_registry(path: Path = REGISTRY) -> dict[str, RegistryEntry]:
    if not path.exists():
        return {}
    rows = json.loads(path.read_text())
    return {r["run_id"]: RegistryEntry.model_validate(r) for r in rows}


def save_registry(entries: dict[str, RegistryEntry], path: Path = REGISTRY) -> None:
    rows = [entries[k].model_dump() for k in sorted(entries)]
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def register(
    entry: RegistryEntry, scores: dict[str, Any] | None = None, path: Path = REGISTRY
) -> RegistryEntry:
    """Add or replace a run; scores from `decision_eval score` also set the temperature."""
    if scores is not None:
        entry = entry.model_copy(
            update={"scores": scores, "temperature": scores.get("fitted_temperature")}
        )
    entries = load_registry(path)
    entries[entry.run_id] = entry
    save_registry(entries, path)
    return entry


# ---------------------------------------------------------------------------- CLI


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    plan_cmd = sub.add_parser("plan")
    plan_cmd.add_argument("--data", type=Path)
    plan_cmd.add_argument("--out", type=Path)
    subsets_cmd = sub.add_parser("subsets")
    subsets_cmd.add_argument("--data", type=Path)
    reg = sub.add_parser("register")
    reg.add_argument("run_dir", type=Path)
    reg.add_argument("--run-id", required=True)
    reg.add_argument("--drive-path")
    reg.add_argument("--scores", type=Path)
    reg.add_argument("--notes", default="")
    args = parser.parse_args()
    config = load_config()
    if args.command == "plan":
        runs = plan(config, args.data)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            rows = [{**r.model_dump(), "command": r.command()} for r in runs]
            args.out.write_text(json.dumps(rows, indent=2) + "\n")
        for r in runs:
            print(f"# {r.run_id} ({r.factor})\n{r.command()}\n")
    elif args.command == "subsets":
        print(json.dumps(write_subsets(config, args.data), indent=2))
    else:
        entry = entry_from_run(args.run_dir, args.run_id, config.get("kev_commit"))
        entry = entry.model_copy(update={"drive_path": args.drive_path, "notes": args.notes})
        scores = json.loads(args.scores.read_text()) if args.scores else None
        print(register(entry, scores).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
