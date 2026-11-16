"""Tests for the Kev run plan, subsets and registry."""

import json
from pathlib import Path

from analyst.models import kev_runs


def test_plan_follows_the_flag_constraints() -> None:
    config = kev_runs.load_config()
    runs = kev_runs.plan(config)
    ids = [r.run_id for r in runs]
    assert ids[0] == "b0_s0"
    assert {"lr1e-05", "lr4e-05", "ep1", "ep3", "n250", "n500", "n1000", "b0_s1", "b0_s2"} <= set(
        ids
    )
    for run in runs:
        command = run.command()
        assert "fp16" not in command  # kev.train has fp32 and bf16 only
        if run.init_from:
            assert run.lora == 16  # --init_from requires the released rank
            assert "--init_from jaredpalmer/kev-0.8b" in command
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
    (run / "head.pt").write_bytes(b"head")
    entry = kev_runs.entry_from_run(run, "b0_s0", "abc")
    assert entry.init_from == "x"
    assert entry.grad_norm[0]["clipped_steps"] == 3
    assert set(entry.weights_sha256) == {"adapter_model.safetensors", "head.pt"}
    registry = tmp_path / "registry.json"
    kev_runs.register(entry, {"fitted_temperature": 2.5}, registry)
    again = kev_runs.load_registry(registry)["b0_s0"]
    assert again.temperature == 2.5
    assert again.flags == {"lr": 2e-5, "seed": 0}
