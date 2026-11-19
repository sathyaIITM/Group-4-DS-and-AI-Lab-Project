"""Kev-0.8B training runs: the sweep plan, train-size subsets and the model registry.

    # the planned runs (one command per run) from configs/train.yaml, as JSON and shell lines;
    # --all lists the full sweep, --smoke <platform> the 32-record smoke run
    python -m analyst.models.kev_runs plan [--all] [--smoke kaggle] [--data <train>] [--out <json>]
    # compare the local data files with the hashes in configs/train.yaml
    python -m analyst.models.kev_runs check-data
    # train-size subsets (250, 500, 1000) of the training file, stratified by label
    python -m analyst.models.kev_runs subsets [--data <train file>]
    # after a run: add or update its entry in models/registry.json
    python -m analyst.models.kev_runs register <run dir> --run-id b0_s0 \
        [--drive-path Group4/checkpoints/b0_s0] [--scores <decision_eval score json>]

`register` also copies the run's small record files (training_config.json,
training_metrics.json, environment.json, train.log) to outputs/reports/kev_runs/<run id>/,
which is committed; the weights stay on Drive and are identified by their SHA-256.

The registry entry follows the T3 brief (Section 5, Artifacts): run id, base, `init_from`,
data hash, flags, seed, temperature, scores, SHA-256 of the adapter and head, Drive path,
and the gradient-norm summary that kev.train writes (clipped steps per epoch).
"""

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from analyst.decisions.phase1 import read_jsonl, subsample, write_jsonl

ROOT = Path(__file__).resolve().parents[3]
TRAIN_CONFIG = ROOT / "configs" / "train.yaml"
REGISTRY = ROOT / "models" / "registry.json"
RUN_RECORDS = ROOT / "outputs" / "reports" / "kev_runs"
RECORD_FILES = (
    "training_config.json",
    "training_metrics.json",
    "environment.json",
    "train.log",
    "pip_freeze.txt",
)
WEIGHT_FILES = ("adapter_model.safetensors", "head.pt")
REQUIRED_RUN_FILES = (*WEIGHT_FILES, "adapter_config.json", "training_metrics.json")
# Kaggle mounts a dataset under its owner's user name; committed records show a placeholder.
KAGGLE_USER = re.compile(r"(/kaggle/input/datasets/)[^/\s\"']+/")


def redact(text: str) -> str:
    """Replace the Kaggle user name in dataset paths with `<kaggle-user>`."""
    return KAGGLE_USER.sub(r"\1<kaggle-user>/", text)


def load_config(path: Path = TRAIN_CONFIG) -> dict[str, Any]:
    """Load the training configuration."""
    config: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return config


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------- plan


class RunSpec(BaseModel):
    """One planned training run: data, hyperparameters and the factor it varies."""

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
    init_from: str | None  # Hub id pinned with `@revision`, as kev.checkpoint.resolve_run reads it
    base: str
    base_revision: str
    # kev.train augmentation (kev/data.py `augment`); the option order is always shuffled
    p_none: float
    p_none_distract: float
    p_distract: float
    platform: str | None = None

    def command(self) -> str:
        """Return the training command for the run."""
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
            f"--p_none {self.p_none:g}",
            f"--p_none_distract {self.p_none_distract:g}",
            f"--p_distract {self.p_distract:g}",
            f"--seed {self.seed}",
            f"--device {self.device}",
            f"--out runs/{self.run_id}",
        ]
        return " ".join(parts)


def _subset_path(config: dict[str, Any], train: Path, size: int) -> str:
    """Return the path of a training subset of a given size."""
    return str(Path(config["data"]["subsets_dir"]) / f"{train.stem}.n{size}.jsonl")


def plan(
    config: dict[str, Any], train: Path | None = None, include_all: bool = False
) -> list[RunSpec]:
    """The planned runs (`planned` in the config), each with its platform's device; with
    `include_all`, the full one-factor-at-a-time sweep from B0, in which the deferred runs
    keep the B0 device and no platform."""
    runs = full_sweep(config, train)
    if include_all or "planned" not in config:
        return runs
    planned: dict[str, str] = config["planned"]
    by_id = {r.run_id: r for r in runs}
    unknown = set(planned) - set(by_id)
    if unknown:
        raise ValueError(f"planned runs not in the sweep: {sorted(unknown)}")
    devices: dict[str, str] = config["platforms"]
    return [
        by_id[run_id].model_copy(update={"platform": platform, "device": devices[platform]})
        for run_id, platform in planned.items()
    ]


def pinned_init(config: dict[str, Any]) -> str:
    """The warm start as `repo@revision`: kev.train has no revision flag, and a bare Hub id
    resolves to the repository's current `main` (kev/checkpoint.py, `resolve_run`)."""
    return f"{config['init_from']['model']}@{config['init_from']['revision']}"


def smoke_run(config: dict[str, Any], platform: str, suffix: str = "") -> RunSpec:
    """One epoch of B0 on the 32-record smoke file with accumulation 2 (16 optimizer steps,
    so kev.train prints at least one loss line): checks set-up, memory and speed."""
    b0 = dict(config["b0"])
    b0.update(epochs=1, accum=2, device=config["platforms"][platform])
    return RunSpec(
        run_id=f"smoke_{platform}{suffix}",
        factor="smoke",
        data=config["data"]["smoke"],
        init_from=pinned_init(config),
        base=config["base"]["model"],
        base_revision=config["base"]["revision"],
        platform=platform,
        **b0,
    )


def smoke_runs(config: dict[str, Any], platform: str) -> list[RunSpec]:
    """The smoke runs of a platform: one per GPU it trains on at once (two on Kaggle), so the
    two-process launch path is tested too."""
    gpus = int(config.get("gpus", {}).get(platform, 1))
    if gpus == 1:
        return [smoke_run(config, platform)]
    return [smoke_run(config, platform, f"_g{i}") for i in range(gpus)]


def check_data(config: dict[str, Any], root: Path = ROOT) -> dict[str, str]:
    """Compare each data file with the hash in the config; a missing file is a failure too."""
    data = config["data"]
    status: dict[str, str] = {}
    for key in ("train", "calibration", "dev_synthetic", "smoke"):
        expected = data.get(f"{key}_sha256")
        path = root / data[key]
        if not path.exists():
            status[key] = "missing"
        elif expected is None:
            status[key] = "no hash in config"
        else:
            status[key] = "ok" if sha256_file(path) == expected else "HASH MISMATCH"
    return status


def _data_hash(config: dict[str, Any], data: str) -> str | None:
    """The file's hash when it is present locally, else the hash recorded in the config."""
    path = ROOT / data
    if path.exists():
        return sha256_file(path)
    recorded = {config["data"][k]: config["data"].get(f"{k}_sha256") for k in ("train", "smoke")}
    return recorded.get(data)


def plan_meta(config: dict[str, Any], config_path: Path = TRAIN_CONFIG) -> dict[str, Any]:
    """What a plan file was made from: the config hash, the repository commit and whether the
    working tree was clean, the Kev commit, the pinned warm start, the evaluation-file hashes
    and the Kaggle session layout."""
    import subprocess

    def git(*args: str) -> str:
        """Run a fixed git command in the repository and return its output."""
        out = subprocess.run(  # noqa: S603  # fixed git arguments
            ["git", "-C", str(ROOT), *args],  # noqa: S607
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()

    data = config["data"]
    return {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "train_yaml_sha256": sha256_file(config_path),
        "repo_commit": git("rev-parse", "HEAD"),
        "repo_dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "kev_commit": config["kev_commit"],
        "init_from": pinned_init(config),
        "data_sha256": {k: data.get(f"{k}_sha256") for k in ("calibration", "dev_synthetic")},
        "sessions": config.get("sessions", {}),
    }


def full_sweep(config: dict[str, Any], train: Path | None = None) -> list[RunSpec]:
    """B0, then one factor at a time. Runs that only differ in seed share a factor name."""
    train = train or Path(config["data"]["train"])
    b0 = dict(config["b0"])
    common = {
        "base": config["base"]["model"],
        "base_revision": config["base"]["revision"],
        "data": str(train),
    }
    init_from = pinned_init(config)
    runs: list[RunSpec] = []

    def add(run_id: str, factor: str, from_base: bool = False, **changes: Any) -> None:
        """Add a run that changes the given settings from the baseline."""
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
    from_base = sweep["from_base"]
    for rank in from_base["lora"]:
        # A fresh adapter and a fresh head: the library's from-base learning rate, not B0's
        # warm-start rate (decided 2026-11-17).
        add(f"base_r{rank}", "from_base_lora", from_base=True, lora=rank, lr=from_base["lr"])
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
    """A registered training run and its results."""

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
    # Added for the Milestone 4 records (training environment and progress).
    platform: str | None = None
    environment: dict[str, Any] = Field(default_factory=dict)
    records_seen: int | None = None
    truncated_records: int | None = None
    optimizer_steps: int | None = None
    peak_device_bytes: int | None = None
    peak_rss_bytes: int | None = None
    trainable_params_m: float | None = None
    final_train_loss: float | None = None
    log_sha256: str | None = None
    dropped_records: int | None = None
    init_source: dict[str, Any] = Field(default_factory=dict)  # kev.train's resolved warm start


LOSS_LINE = re.compile(
    r"^ep(?P<epoch>\d+) step (?P<step>\d+)/(?P<steps>\d+) loss (?P<loss>[-+\w.]+)"
)
PARAMS_LINE = re.compile(r"trainable params=(?P<m>[\d.]+)M")
DROPPED_LINE = re.compile(r"dropped (?P<n>\d+) of (?P<of>\d+) records")


def parse_train_log(path: Path) -> dict[str, Any]:
    """The loss lines (`ep<e> step <s>/<n> loss <x> ...`) and the trainable-parameter count
    that kev.train prints; each loss is the mean cross-entropy of the 10 optimizer steps since the
    previous line (kev.train prints every 10 steps; steps after the last multiple of 10 are not
    printed). `dropped_records` counts records kev.train left out for exceeding the training
    context (its metrics file does not report them)."""
    points: list[dict[str, float]] = []
    params: float | None = None
    dropped: int = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        match = LOSS_LINE.match(line)
        if match:
            points.append(
                {
                    "epoch": int(match["epoch"]),
                    "step": int(match["step"]),
                    "steps": int(match["steps"]),
                    "loss": float(match["loss"]),
                }
            )
            continue
        found = PARAMS_LINE.search(line)
        if found:
            params = float(found["m"])
        gone = DROPPED_LINE.search(line)
        if gone:
            dropped += int(gone["n"])
    return {"points": points, "trainable_params_m": params, "dropped_records": dropped}


def entry_from_run(run_dir: Path, run_id: str, kev_commit: str | None = None) -> RegistryEntry:
    """Read what kev.train saved in `run_dir` (training_config.json, training_metrics.json,
    the adapter and the head), plus what the notebook adds (`environment.json`, the platform
    and package versions, and `train.log`), into a registry entry. A run trained from a
    copied data path is matched to the repository file by its hash."""
    config = json.loads((run_dir / "training_config.json").read_text())
    args: dict[str, Any] = config.get("args", {})
    metrics_path = run_dir / "training_metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    env_path = run_dir / "environment.json"
    environment = json.loads(env_path.read_text()) if env_path.exists() else {}
    log_path = run_dir / "train.log"
    log = parse_train_log(log_path) if log_path.exists() else {"points": []}
    log_text = (
        redact(log_path.read_text(encoding="utf-8", errors="replace"))
        if log_path.exists()
        else None
    )
    data = environment.get("data_repo_path") or args.get("data") or None
    data_path = ROOT / data if data and not Path(data).is_absolute() else None
    missing = [name for name in REQUIRED_RUN_FILES if not (run_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"{run_dir} is not a complete run: missing {missing}")
    weights = {name: sha256_file(run_dir / name) for name in (*WEIGHT_FILES, "adapter_config.json")}
    entry = RegistryEntry(
        run_id=run_id,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        kev_commit=kev_commit,
        base=args.get("base"),
        base_revision=config.get("base_revision") or args.get("base_revision"),
        init_from=args.get("init_from") or None,
        data=data,
        data_sha256=environment.get("data_sha256")
        or (sha256_file(data_path) if data_path and data_path.exists() else None),
        flags={k: v for k, v in args.items() if k not in {"data", "out", "base", "init_from"}},
        seed=args.get("seed"),
        weights_sha256=weights,
        grad_norm=metrics.get("grad_norm", []),
        wall_seconds=metrics.get("wall_seconds"),
        device=metrics.get("device"),
        platform=environment.get("platform"),
        environment=environment,
        records_seen=metrics.get("records_seen"),
        truncated_records=metrics.get("truncated_records"),
        optimizer_steps=metrics.get("optimizer_steps"),
        peak_device_bytes=metrics.get("peak_device_bytes"),
        peak_rss_bytes=metrics.get("peak_rss_bytes"),
        trainable_params_m=log.get("trainable_params_m"),
        final_train_loss=log["points"][-1]["loss"] if log["points"] else None,
        # hash of the archived (redacted) log, so the committed file can be checked against it
        log_sha256=hashlib.sha256(log_text.encode("utf-8")).hexdigest() if log_text else None,
        dropped_records=log.get("dropped_records"),
        init_source=config.get("init_source") or {},
    )
    return RegistryEntry.model_validate_json(redact(entry.model_dump_json()))


def archive_records(run_dir: Path, run_id: str, target: Path = RUN_RECORDS) -> list[str]:
    """Copy the run's small record files next to the registry's evidence; returns them."""
    out = target / run_id
    out.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in RECORD_FILES:
        if (run_dir / name).exists():
            text = (run_dir / name).read_text(encoding="utf-8", errors="replace")
            (out / name).write_text(redact(text), encoding="utf-8")
            copied.append(str((out / name).relative_to(ROOT) if out.is_relative_to(ROOT) else out))
    return copied


def load_registry(path: Path = REGISTRY) -> dict[str, RegistryEntry]:
    """Load the run registry."""
    if not path.exists():
        return {}
    rows = json.loads(path.read_text())
    return {r["run_id"]: RegistryEntry.model_validate(r) for r in rows}


def save_registry(entries: dict[str, RegistryEntry], path: Path = REGISTRY) -> None:
    """Save the run registry sorted by run id."""
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
    """Command-line entry point for planning and registering Kev runs."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    plan_cmd = sub.add_parser("plan")
    plan_cmd.add_argument("--data", type=Path)
    plan_cmd.add_argument("--out", type=Path)
    plan_cmd.add_argument("--all", action="store_true", help="the full sweep, deferred runs too")
    plan_cmd.add_argument("--smoke", metavar="PLATFORM", help="only the smoke run of a platform")
    sub.add_parser("check-data")
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
    if args.command == "check-data":
        status = check_data(config)
        print(json.dumps(status, indent=2))
        if any(v != "ok" for v in status.values()):
            raise SystemExit(1)
    elif args.command == "plan":
        if args.smoke:
            runs = smoke_runs(config, args.smoke)
        else:
            runs = plan(config, args.data, include_all=args.all)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            rows = [
                {
                    **run.model_dump(),
                    "data_sha256": _data_hash(config, run.data),
                    "command": run.command(),
                }
                for run in runs
            ]
            plan_file = {"meta": plan_meta(config), "runs": rows}
            args.out.write_text(json.dumps(plan_file, indent=2) + "\n")
        for run in runs:
            print(f"# {run.run_id} ({run.factor}, {run.platform or 'deferred'})\n{run.command()}\n")
    elif args.command == "subsets":
        print(json.dumps(write_subsets(config, args.data), indent=2))
    else:
        entry = entry_from_run(args.run_dir, args.run_id, config.get("kev_commit"))
        entry = entry.model_copy(update={"drive_path": args.drive_path, "notes": args.notes})
        scores = json.loads(args.scores.read_text()) if args.scores else None
        print(register(entry, scores).model_dump_json(indent=2))
        print("records copied:", ", ".join(archive_records(args.run_dir, args.run_id)))


if __name__ == "__main__":
    main()
