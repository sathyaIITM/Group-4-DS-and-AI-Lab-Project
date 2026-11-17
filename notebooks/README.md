# Notebooks

Exploration and profiling only. Anything the pipeline depends on moves into
`src/analyst` with tests. Clear outputs before committing, and keep data
paths relative to `data/`.

| Notebook | Purpose |
| --- | --- |
| `eda.ipynb` | Exploratory analysis of the catalogue tables |
| `kev_train_t4.ipynb` | Kev-0.8B domain fine-tuning on a Colab or Kaggle T4 (smoke and planned runs) |

Fine-tuning uses fp32 on the T4: the T4 has no bf16, and `kev.train` offers fp32 or bf16 only
(no fp16). The runs, the procedure and the records are fixed in
`docs/specs/kev_training_protocol.md`. Commit the training notebook with its outputs cleared;
each run's configuration and records are kept in `outputs/reports/kev_runs/<run id>/`.
