"""Tests for the Kev run plan, subsets and registry."""

import hashlib
import json
from pathlib import Path

import pytest

from analyst.models import kev_runs


def test_plan_follows_the_flag_constraints() -> None:
    config = kev_runs.load_config()
    runs = kev_runs.plan(config, include_all=True)
    ids = [r.run_id for r in runs]
    assert ids[0] == "b0_s0"
    assert len(ids) == 13
    assert {"lr1e-05", "lr4e-05", "ep1", "ep3", "n250", "n500", "n1000", "b0_s1", "b0_s2"} <= set(
        ids
    )
    for run in runs:
        command = run.command()
        assert "fp16" not in command  # kev.train has fp32 and bf16 only
        if run.init_from:
            assert run.lora == 16  # --init_from requires the released rank
            assert "--init_from jaredpalmer/kev-0.8b@" in command
        else:
            assert "--init_from" not in command
    assert {r.lora for r in runs if r.factor == "from_base_lora"} == {8, 16, 32}
    assert next(r for r in runs if r.run_id == "n250").data.endswith(".n250.jsonl")


def test_subsets_are_written_and_hashed(tmp_path: Path) -> None:
    train = tmp_path / "train.v2.jsonl"
    rows = [
        {
            "state": {},
            "questions": {"domain": {"label": ["labour", "health"][i % 2]}},
            "_meta": {"id": str(i)},
        }
        for i in range(600)
    ]
    train.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    config = kev_runs.load_config()
    config["data"]["subsets_dir"] = str(tmp_path / "subsets")
    out = kev_runs.write_subsets(config, train)
    assert sorted(v["records"] for v in out.values()) == [250, 500]
    for path in out:
        assert len(Path(path).read_text().splitlines()) in {250, 500}


def test_register_reads_a_run_directory(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "training_config.json").write_text(
        json.dumps(
            {"args": {"base": "b", "lr": 2e-5, "seed": 0, "init_from": "x"}, "base_revision": "r"}
        )
    )
    (run / "training_metrics.json").write_text(
        json.dumps({"grad_norm": [{"epoch": 0, "clipped_steps": 3}], "wall_seconds": 5.0})
    )
    (run / "adapter_model.safetensors").write_bytes(b"weights")
    (run / "adapter_config.json").write_text("{}")
    (run / "head.pt").write_bytes(b"head")
    entry = kev_runs.entry_from_run(run, "b0_s0", "abc")
    assert entry.init_from == "x"
    assert entry.grad_norm[0]["clipped_steps"] == 3
    assert set(entry.weights_sha256) == {
        "adapter_model.safetensors",
        "head.pt",
        "adapter_config.json",
    }
    registry = tmp_path / "registry.json"
    kev_runs.register(entry, {"fitted_temperature": 2.5}, registry)
    again = kev_runs.load_registry(registry)["b0_s0"]
    assert again.temperature == 2.5
    assert again.flags == {"lr": 2e-5, "seed": 0}


def test_planned_runs_carry_platform_and_device() -> None:
    config = kev_runs.load_config()
    runs = kev_runs.plan(config)
    assert [r.run_id for r in runs] == list(config["planned"])
    assert len(runs) == 8
    by_id = {r.run_id: r for r in runs}
    assert all(r.device == "cuda" for r in runs)  # every Kev run on a CUDA T4
    assert by_id["base_r16"].init_from is None and by_id["base_r16"].platform == "colab"
    assert by_id["base_r16"].lr == config["sweep"]["from_base"]["lr"]
    for run in runs:
        command = run.command()
        assert "--p_none 0 " in command
        if run.init_from:
            assert f"@{config['init_from']['revision']}" in command  # pinned warm start
    sessions = [i for s in config["sessions"].values() for gpu in s for i in gpu]
    assert sorted(sessions) == sorted(by_id)  # every planned run sits in exactly one session
    deferred = {r.run_id for r in kev_runs.plan(config, include_all=True)} - set(by_id)
    assert deferred == {"n250", "n500", "n1000", "base_r8", "base_r32"}


def test_smoke_run_is_one_epoch_on_the_smoke_file() -> None:
    config = kev_runs.load_config()
    smoke = kev_runs.smoke_run(config, "kaggle")
    assert smoke.epochs == 1 and smoke.data == config["data"]["smoke"]
    assert smoke.accum == 2  # 16 steps on 32 records: at least one printed loss line
    assert "--init_from jaredpalmer/kev-0.8b@" in smoke.command()
    assert [r.run_id for r in kev_runs.smoke_runs(config, "kaggle")] == [
        "smoke_kaggle_g0",
        "smoke_kaggle_g1",
    ]
    assert [r.run_id for r in kev_runs.smoke_runs(config, "colab")] == ["smoke_colab"]


def test_check_data_reports_mismatch(tmp_path: Path) -> None:
    config = kev_runs.load_config()
    for key in ("train", "calibration", "dev_synthetic", "smoke"):
        path = tmp_path / config["data"][key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")
    status = kev_runs.check_data(config, root=tmp_path)
    assert set(status.values()) == {"HASH MISMATCH"}
    assert set(kev_runs.check_data(config, root=tmp_path / "empty").values()) == {"missing"}


LOG = """dropped 2 of 1876 records that exceed the training context (384 state / 1024 branch)
device=cuda world=1 trainable params=12.3M
ep0 step 10/470 loss 1.250 kl 0.000 anchor 0.000 0.512s/rec
ep1 step 470/470 loss 0.310 kl 0.000 anchor 0.000 0.509s/rec
"""


def test_parse_train_log() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "train.log"
        path.write_text(LOG)
        parsed = kev_runs.parse_train_log(path)
    assert parsed["trainable_params_m"] == 12.3
    assert [p["loss"] for p in parsed["points"]] == [1.25, 0.31]
    assert parsed["points"][-1]["epoch"] == 1


def test_register_reads_environment_and_log(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "training_config.json").write_text(json.dumps({"args": {"seed": 1}}))
    (run / "training_metrics.json").write_text(
        json.dumps({"peak_device_bytes": 5_000_000_000, "truncated_records": 0})
    )
    (run / "environment.json").write_text(
        json.dumps({"platform": "kaggle", "data_sha256": "abc", "torch": "2.8.0"})
    )
    (run / "train.log").write_text(LOG)
    (run / "head.pt").write_bytes(b"head")
    with pytest.raises(FileNotFoundError, match="not a complete run"):
        kev_runs.entry_from_run(run, "b0_s1")
    (run / "adapter_model.safetensors").write_bytes(b"weights")
    (run / "adapter_config.json").write_text("{}")
    (run / "pip_freeze.txt").write_text("torch==2.8.0\n")
    entry = kev_runs.entry_from_run(run, "b0_s1")
    assert entry.platform == "kaggle" and entry.data_sha256 == "abc"
    assert entry.final_train_loss == 0.31 and entry.trainable_params_m == 12.3
    assert entry.peak_device_bytes == 5_000_000_000 and entry.log_sha256
    assert entry.dropped_records == 2
    copied = kev_runs.archive_records(run, "b0_s1", tmp_path / "records")
    assert len(copied) == 5
    assert (tmp_path / "records" / "b0_s1" / "train.log").exists()


def test_kaggle_user_name_is_redacted(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    path = "/kaggle/input/datasets/someone123/group4-kev-data/train.v2.jsonl"
    (run / "training_config.json").write_text(json.dumps({"args": {"data": path, "seed": 0}}))
    (run / "training_metrics.json").write_text("{}")
    (run / "environment.json").write_text(json.dumps({"platform": "kaggle", "command": path}))
    (run / "train.log").write_text(f"loading {path}\n")
    for name in ("adapter_model.safetensors", "adapter_config.json", "head.pt"):
        (run / name).write_text("x")
    entry = kev_runs.entry_from_run(run, "b0_s0")
    assert "someone123" not in entry.model_dump_json()
    assert "<kaggle-user>" in entry.environment["command"]
    kev_runs.archive_records(run, "b0_s0", tmp_path / "records")
    archived = tmp_path / "records" / "b0_s0"
    for name in ("train.log", "environment.json", "training_config.json"):
        assert "someone123" not in (archived / name).read_text()
    log_digest = hashlib.sha256((archived / "train.log").read_bytes()).hexdigest()
    assert entry.log_sha256 == log_digest  # the committed log matches the registry hash
