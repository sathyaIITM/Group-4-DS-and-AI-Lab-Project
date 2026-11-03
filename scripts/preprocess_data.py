"""Kept so that the Milestone 2 command still works; the work is done by the pipeline.

    python scripts/preprocess_data.py

now runs ``scripts/run_pipeline.py`` (configuration-driven, all five tables). Table-specific
choices live in ``configs/sources/*.toml``; see ``scripts/README.md``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
