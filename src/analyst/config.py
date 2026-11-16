from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any
import yaml
from analyst.agents.state import Limits, RunConfig

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_run_config(version: str = "v0", config_path: str = "configs/agent.yaml") -> RunConfig:
    """Load an immutable run configuration and retain hashes of its source files."""
    if version not in {f"v{i}" for i in range(7)}:
        raise ValueError(f"unsupported agent version: {version}")
    path = Path(config_path)
    raw: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        hashes[str(path)] = sha256_file(path)
    limits = Limits.model_validate(raw.get("limits", {}))
    return RunConfig(
        version=version,
        limits=limits,
        model_id=str(raw.get("model", {}).get("id", "unset")),
        model_version=str(raw.get("model", {}).get("version", "unset")),
        prompt_hashes=dict(raw.get("prompt_hashes", {})),
        config_hashes=hashes,
        catalogue_contract_version=str(raw.get("catalogue_contract_version", "unknown")),
    )
