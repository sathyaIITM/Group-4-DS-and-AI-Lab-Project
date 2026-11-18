"""Prompt registry for the hosted-LLM nodes.

Each prompt is one file, `configs/prompts/<id>.v<N>.md`, with a header and two sections:

    ---
    id: intent
    version: 1
    purpose: intent
    inputs: [question, context, prior_plan]
    output_schema: QueryIntent
    ---
    ## System
    ...
    ## User
    ... {{question}} ...

`PromptRegistry.get("intent")` returns the highest version; `get("intent.v1")` a fixed one. The
SHA-256 of the file bytes identifies the prompt in `RunConfig` and in every `LlmCallRecord`
(agent design Section 7). Placeholders are `{{name}}`; rendering fails on a missing or an
unexpected variable, so a template and its caller cannot drift apart silently.

User text is placed inside `<user_question>` and retrieved content inside `<context>`; the
renderer removes any copy of those tags from the values, so text in a question or a catalogue
entry cannot close a delimiter and pose as an instruction.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PROMPT_DIR = ROOT / "configs" / "prompts"

_HEADER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_FILE = re.compile(r"^(?P<id>[a-z][a-z0-9_]*)\.v(?P<version>\d+)\.md$")
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
_DELIMITERS = re.compile(r"</?\s*(user_question|context)\s*>", re.IGNORECASE)
_SECTION = re.compile(r"^## (System|User)\s*$", re.MULTILINE)
REQUIRED_KEYS = ("id", "version", "purpose", "inputs", "output_schema")


class PromptError(ValueError):
    """A prompt file is malformed, missing, or rendered with the wrong variables."""


@dataclass(frozen=True)
class RenderedPrompt:
    system: str
    user: str


@dataclass(frozen=True)
class Prompt:
    id: str
    version: int
    purpose: str
    inputs: tuple[str, ...]
    output_schema: str
    system: str
    user: str
    text: str
    sha256: str

    @property
    def prompt_id(self) -> str:
        return f"{self.id}.v{self.version}"

    def render(self, variables: dict[str, Any]) -> RenderedPrompt:
        """Fill the placeholders; non-string values are written as compact JSON."""
        given, declared = set(variables), set(self.inputs)
        if given != declared:
            missing, extra = sorted(declared - given), sorted(given - declared)
            raise PromptError(f"{self.prompt_id}: missing {missing}, unexpected {extra}")
        values = {name: _as_text(value) for name, value in variables.items()}

        def fill(template: str) -> str:
            return _PLACEHOLDER.sub(lambda m: values[m.group(1)], template)

        return RenderedPrompt(system=fill(self.system).strip(), user=fill(self.user).strip())


def _as_text(value: Any) -> str:
    if value is None:
        text = "none"
    elif isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return _DELIMITERS.sub("", text)


def _parse_header(block: str, path: Path) -> dict[str, Any]:
    """A deliberately small subset of YAML: `key: value` and `key: [a, b]` lines."""
    header: dict[str, Any] = {}
    for line in block.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise PromptError(f"{path.name}: header line without a colon: {line!r}")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            header[key.strip()] = tuple(v.strip() for v in value[1:-1].split(",") if v.strip())
        else:
            header[key.strip()] = value
    return header


def load_prompt(path: Path) -> Prompt:
    raw = path.read_bytes()
    # Git may check these templates out with CRLF on Windows; parse a canonical newline view
    # while hashing the original bytes so run provenance still reflects the exact file.
    text = raw.decode("utf-8").replace("\r\n", "\n")
    match = _HEADER.match(text)
    if match is None:
        raise PromptError(f"{path.name}: no '---' header")
    header = _parse_header(match.group(1), path)
    missing = [k for k in REQUIRED_KEYS if k not in header]
    if missing:
        raise PromptError(f"{path.name}: header lacks {missing}")
    name = _FILE.match(path.name)
    if name is None or name["id"] != header["id"] or int(name["version"]) != int(header["version"]):
        raise PromptError(f"{path.name}: file name does not match id {header['id']!r} and version")
    body = text[match.end() :]
    parts = _SECTION.split(body)
    # parts: [preamble, "System", system_text, "User", user_text]
    if len(parts) != 5 or parts[1] != "System" or parts[3] != "User":
        raise PromptError(f"{path.name}: needs a '## System' section followed by '## User'")
    system, user = parts[2], parts[4]
    used = set(_PLACEHOLDER.findall(system + user))
    declared = set(header["inputs"])
    if used != declared:
        raise PromptError(
            f"{path.name}: inputs {sorted(declared)} differ from placeholders {sorted(used)}"
        )
    return Prompt(
        id=header["id"],
        version=int(header["version"]),
        purpose=header["purpose"],
        inputs=tuple(header["inputs"]),
        output_schema=header["output_schema"],
        system=system,
        user=user,
        text=text,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


class PromptRegistry:
    """Loads every prompt file once; lookups are by `id` (latest) or `id.vN` (pinned)."""

    def __init__(self, directory: Path = PROMPT_DIR) -> None:
        self._prompts: dict[str, Prompt] = {}
        for path in sorted(directory.glob("*.v*.md")):
            prompt = load_prompt(path)
            self._prompts[prompt.prompt_id] = prompt
        if not self._prompts:
            raise PromptError(f"no prompt files in {directory}")

    def get(self, prompt_id: str) -> Prompt:
        if prompt_id in self._prompts:
            return self._prompts[prompt_id]
        versions = [p for p in self._prompts.values() if p.id == prompt_id]
        if not versions:
            raise PromptError(f"unknown prompt {prompt_id!r}")
        return max(versions, key=lambda p: p.version)

    def hashes(self) -> dict[str, str]:
        """`prompt_id -> sha256` for every loaded prompt, for `RunConfig`."""
        return {pid: p.sha256 for pid, p in sorted(self._prompts.items())}

    def __iter__(self) -> Any:
        return iter(sorted(self._prompts.values(), key=lambda p: p.prompt_id))
