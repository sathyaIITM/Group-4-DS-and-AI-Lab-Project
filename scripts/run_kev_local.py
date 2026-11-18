"""Run one planned Kev training run on the local machine (Apple MPS) and keep its records.

    caffeinate -i .venv/bin/python scripts/run_kev_local.py smoke   # 32 records, 1 epoch
    caffeinate -i .venv/bin/python scripts/run_kev_local.py <run>   # a run planned for "local"

No Kev run is planned for the local machine at present (all train on CUDA T4s); the script
serves the local smoke test and any run later assigned to the local platform.

The run spec comes from configs/train.yaml (`kev_runs plan`); the run must be planned for the
`local` platform. Kev runs from its own clone and environment (KEV_DIR, default ~/kev-src, at
the commit in configs/train.yaml). Output: models/checkpoints/<run id>/ with the kev.train files
plus train.log, environment.json and pip_freeze.txt, the same layout as the notebook writes, so
`kev_runs register` treats local and cloud runs alike. `caffeinate -i` keeps the machine awake.
"""

import argparse
import json
import os
import platform
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst.models.kev_runs import (  # noqa: E402
    REQUIRED_RUN_FILES,
    load_config,
    plan,
    plan_meta,
    sha256_file,
    smoke_run,
)

VERSIONS = (
    "import json, sys, torch, transformers, peft; print(json.dumps({'python': "
    "sys.version.split()[0], 'torch': torch.__version__, 'transformers': "
    "transformers.__version__, 'peft': peft.__version__, "
    "'mps': torch.backends.mps.is_available()}))"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_id", help="a run planned for the local platform, or 'smoke'")
    args = parser.parse_args()
    config = load_config()
    if args.run_id == "smoke":
        run = smoke_run(config, "local")
    else:
        runs = {r.run_id: r for r in plan(config)}
        run = runs[args.run_id]
        if run.platform != "local":
            raise SystemExit(f"{run.run_id} is planned for {run.platform}, not local")
    kev_dir = Path(os.environ.get("KEV_DIR", Path.home() / "kev-src"))
    python = kev_dir / ".venv" / "bin" / "python"
    if not python.exists():
        raise SystemExit(f"no Kev environment at {python}: run `uv sync --frozen` in {kev_dir}")
    git = ["git", "-C", str(kev_dir), "rev-parse", "HEAD"]
    commit = subprocess.run(git, capture_output=True, text=True, check=True).stdout.strip()  # noqa: S603
    if commit != config["kev_commit"]:
        raise SystemExit(f"Kev clone at {commit}, configs/train.yaml pins {config['kev_commit']}")
    status = ["git", "-C", str(kev_dir), "status", "--porcelain", "--untracked-files=no"]
    if subprocess.run(status, capture_output=True, text=True).stdout.strip():  # noqa: S603
        raise SystemExit(f"the Kev clone at {kev_dir} has local changes")
    data = ROOT / run.data
    digest = sha256_file(data)
    expected = {config["data"][k]: config["data"][f"{k}_sha256"] for k in ("train", "smoke")}
    if digest != expected.get(run.data):
        raise SystemExit(f"hash mismatch for {run.data}")
    out = ROOT / "models" / "checkpoints" / run.run_id
    if out.exists():  # kev.train refuses an existing --out; so does this script
        raise SystemExit(f"{out.relative_to(ROOT)} exists; move it away to rerun {run.run_id}")
    out.parent.mkdir(parents=True, exist_ok=True)
    log_path = out.parent / f"{run.run_id}.train.log"  # moved into the run folder afterwards
    command = run.command()
    command = command.replace(f"--data {run.data}", f"--data {shlex.quote(str(data))}")
    command = command.replace(f"--out runs/{run.run_id}", f"--out {shlex.quote(str(out))}")
    command = command.replace("python -m kev.train", f"{python} -m kev.train")
    probe = [str(python), "-c", VERSIONS]
    versions = json.loads(
        subprocess.run(probe, capture_output=True, text=True, check=True).stdout  # noqa: S603
    )
    if run.device == "mps" and not versions["mps"]:
        raise SystemExit("PyTorch in the Kev environment cannot use MPS")
    record = {
        "run_id": run.run_id,
        "platform": "local",
        "gpu": platform.processor() or platform.machine(),
        "machine": platform.platform(),
        "parallel_runs": 1,
        "kev_commit": commit,
        **versions,
        "data_repo_path": run.data,
        "data_sha256": digest,
        "init_from": run.init_from,
        "uv_lock_sha256": sha256_file(kev_dir / "uv.lock"),
        "plan_meta": plan_meta(config),
        "command": command,
        "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    print(command, flush=True)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(  # noqa: S603  # command built from configs/train.yaml
            shlex.split(command),
            cwd=kev_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.stdout is None:
            raise SystemExit("no output pipe")
        for line in proc.stdout:
            sys.stdout.write(line)
            log.write(line)
        proc.wait()
    missing = [name for name in REQUIRED_RUN_FILES if not (out / name).exists()]
    if proc.returncode != 0 or missing:  # keep the evidence, never as a finished run
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        failed = out.parent / f"{run.run_id}.failed-{stamp}"
        if out.exists():
            out.rename(failed)
        out = failed
        print(f"run failed (exit {proc.returncode}, missing {missing})")
    out.mkdir(parents=True, exist_ok=True)
    log_path.replace(out / "train.log")
    record["ended_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    record["exit_code"] = proc.returncode
    (out / "environment.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    uv = ["uv", "pip", "freeze", "--python", str(python)]
    freeze = subprocess.run(uv, capture_output=True, text=True).stdout  # noqa: S603
    (out / "pip_freeze.txt").write_text(freeze, encoding="utf-8")
    print(f"exit code {proc.returncode}; records in {out.relative_to(ROOT)}")
    raise SystemExit(proc.returncode or (1 if missing else 0))


if __name__ == "__main__":
    main()
