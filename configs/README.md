# Configuration

One file per concern, loaded through `pydantic-settings`. Values that are
secrets come from the environment, never from these files; `.env.example` lists
the variable names.

Expected files, added as the corresponding component lands:

| File | Purpose |
| --- | --- |
| `catalogue.toml` | The table list, with source, version and licence per table, plus the metadata the Kev data generator samples from (draft; frozen in Milestone 2). TOML because the standard library reads it. |
| `model.yaml` | Hosted LLM and decision-model identifiers (Kev, Jev), by operating mode |
| `train.yaml` | Kev fine-tuning runs: base checkpoint, LoRA rank, epochs, learning rate, data file |
| `inference.yaml` | Decision-layer backend chain, confidence bands and per-decision gate margins |
| `evaluation.yaml` | Experiment definitions E1–E7 and the objective targets O1–O8 |
| `prompts/` | Prompt templates, including the versions produced by DSPy and GEPA |

Record the provider, model identifier and access date with every reported
result. A backend or version change requires recalibration and a re-run of the
affected rows.
