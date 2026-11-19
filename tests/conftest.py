"""Shared test setup: the pipeline reads configs and reference tables relative to the repo root."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test from the repository root."""
    monkeypatch.chdir(ROOT)


@pytest.fixture
def agent_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory whose `outputs/` is empty; configs and data are the repository's."""
    for name in ("configs", "data"):
        (tmp_path / name).symlink_to(ROOT / name)
    monkeypatch.chdir(tmp_path)
    return tmp_path
