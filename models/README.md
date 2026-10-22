# Models

Local model artefacts. Not tracked by git except this file and the
`.gitkeep` placeholders: checkpoints are large, reproducible from the training
runs in `src/analyst/models` and `notebooks/`, and are pushed to the
Hugging Face Hub or Google Drive per run instead.

| Directory | Contents |
| --- | --- |
| `checkpoints/` | Local copies of fine-tuned Kev checkpoints (LoRA adapters) and fitted calibration temperatures, pulled from the Hugging Face Hub or Google Drive for local evaluation |

Record, for each checkpoint kept here: the base model and `--init_from`
checkpoint, the training data file and size, the epoch and learning rate, the
fitted temperature, and the commit of the training script that produced it.
This project does not fine-tune a query-writing model; only Kev (and, as a
stretch comparison, Kev-4B) is trained.
