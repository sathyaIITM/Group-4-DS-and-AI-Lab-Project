"""Run configuration: `RunConfig.from_files` loads and hashes the configuration files."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from analyst.agents.state import Limits, RagPaths, RunConfig

CONFIG_FILES = ("configs/model.yaml", "configs/inference.yaml")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prompt_hashes() -> dict[str, str]:
    from analyst.inference.prompts import PromptRegistry

    return PromptRegistry().hashes()


def _hosted_model(path: Path = Path("configs/model.yaml")) -> tuple[str, str]:
    """The default hosted model id and tier from `model.yaml` (the only place it is set)."""
    if not path.exists():
        return "unset", "unset"
    config = yaml.safe_load(path.read_text(encoding="utf-8")).get("hosted_llm", {})
    tier = config.get("default_tier", "unset")
    return str(config.get("tiers", {}).get(tier, "unset")), str(tier)


def load_run_config(
    version: str = "v0", config_path: str = "configs/agent.yaml", variant: str | None = None
) -> RunConfig:
    """An immutable run configuration with the hash of every file it was built from.

    Hashed: `agent.yaml`, `model.yaml`, `inference.yaml`, the guidance-card and example files in
    use, and every prompt (`prompt_hashes`, from the prompt registry).
    """
    if version not in {f"v{i}" for i in range(7)}:
        msg = f"unsupported agent version: {version}"
        raise ValueError(msg)
    if variant is not None:
        inference = Path("configs/inference.yaml")
        variants = (yaml.safe_load(inference.read_text(encoding="utf-8")) or {}).get("variants")
        if variant not in (variants or {}):
            raise ValueError(f"unknown variant {variant!r} in {inference}")
    path = Path(config_path)
    raw: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        hashes[str(path)] = sha256_file(path)
    for name in CONFIG_FILES:
        if Path(name).exists():
            hashes[name] = sha256_file(Path(name))
    limits = Limits.model_validate(raw.get("limits", {}))
    rag = RagPaths.model_validate(raw.get("rag", {}))
    for name in (rag.cards, rag.examples, rag.cards_fallback, rag.examples_fallback):
        if Path(name).exists():
            hashes[name] = sha256_file(Path(name))
    hosted = _hosted_model()
    return RunConfig(
        version=version,
        variant=variant,
        limits=limits,
        rag=rag,
        model_id=hosted[0],
        model_version=hosted[1],
        prompt_hashes=_prompt_hashes(),
        config_hashes=hashes,
        catalogue_contract_version=str(raw.get("catalogue_contract_version", "unknown")),
    )
