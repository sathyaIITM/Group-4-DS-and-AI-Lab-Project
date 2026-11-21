# Setting up and running the agent on Windows

This guide installs the project on Windows 10 or 11 and runs the demonstration app in two modes:

| Mode | What it does | Needs | Cost |
| --- | --- | --- | --- |
| `stub` | Runs every node of the graph with scripted model replies; the answer is a placeholder | Python and the data | None |
| `live` | Calls Gemini on Vertex AI for intent, SQL and narration | Stub setup, the Google Cloud CLI and access to the team's GCP project | About USD 0.02-0.03 per question (estimate from the Milestone 4 ladder) |

All commands are for **PowerShell** and are run from the repository root unless stated
otherwise. The agent reads `configs\` and `data\processed\` relative to the current directory,
so a command run from another folder fails with a missing-file error.

The steps were checked on a clean clone of `main` on macOS (stub mode: health check, page,
`/ask`, `/stream`; full test suite 550 passed, 19 skipped). The Windows-specific parts
(PowerShell syntax, UTF-8 setting, `gcloud.cmd` lookup) follow from the differences listed in
Section 8 and still need a run on a Windows machine; report any step that fails.

## 1. Install the prerequisites

1. **Python 3.13** (3.12 also works) from https://www.python.org/downloads/windows/. In the
   installer, tick "Add python.exe to PATH" and keep the "py launcher" option. Python 3.14 is
   not supported (`pyproject.toml` requires `>=3.12,<3.14`).
2. **Git for Windows** from https://git-scm.com/download/win (default options).
3. About **3 GB of free disk** for the virtual environment (PyTorch, CPU build) and the
   embedding model.

Check the versions in a new PowerShell window:

```powershell
py -3.13 --version     # Python 3.13.x
git --version
```

## 2. Make Python read files as UTF-8

About 60 places in the code read or write text files without naming an encoding. On Windows
Python then uses the system code page (usually cp1252), and any character outside it (an en
dash in a specification, `₹` in a model reply written to a file) raises `UnicodeDecodeError` or
`UnicodeEncodeError`. Python's UTF-8 mode removes the problem for every command:

```powershell
setx PYTHONUTF8 1
```

Close the PowerShell window and open a new one; `setx` affects new windows only. Check with
`$env:PYTHONUTF8` (prints `1`).

## 3. Clone the repository and create the environment

```powershell
cd $HOME\Documents
git clone https://github.com/sathyaIITM/Group-4-DS-and-AI-Lab-Project.git
cd Group-4-DS-and-AI-Lab-Project

py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,retrieval,eval]"
```

If `Activate.ps1` is blocked ("running scripts is disabled on this system"), allow local
scripts for the current user once, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

The prompt starts with `(.venv)` when the environment is active. Activate it in every new
window before running the commands below. The install takes several minutes; PyTorch is
pulled in by `sentence-transformers`.

Line endings need no setting: `.gitattributes` checks every file out with LF endings, so file
hashes match the other members' machines.

## 4. Get the data

Raw and processed data are not in git. Use one of the two routes.

### Route A (recommended): the frozen Milestone 4 build

Ask T3 for `data_processed_m4_frozen.zip` (about 7 MB; the 14 tables used for the
Milestone 4 results). Extract it at the repository root so that the files land in
`data\processed\`:

```powershell
Expand-Archive -Path $HOME\Downloads\data_processed_m4_frozen.zip -DestinationPath . -Force
(Get-ChildItem data\processed\obs_*.parquet).Count     # 14
Test-Path data\processed\catalogue.json                # True
```

The hashes of the 14 `obs_*.parquet` files equal those in `data\MANIFEST.md`. To check one:

```powershell
(Get-FileHash data\processed\obs_msp_crops.parquet -Algorithm SHA256).Hash.ToLower()
```

### Route B: rebuild from the sources

1. Get a free API key from https://data.gov.in (sign in, then "My Account", "Generate API key")
   and set it for the current window:

   ```powershell
   $env:DATA_GOV_IN_API_KEY = "<your key>"
   python scripts\download_raw.py
   ```

2. Three raw files are not fetched by the script. Put them in `data\raw\` with these names
   (ask T1 for copies, or download them from data.gov.in):

   | File | Source |
   | --- | --- |
   | `datafile3.csv` | NCRB, Crime in India 2024, Table 1.1(ii): https://www.data.gov.in/catalog/crime-india-cii-2024 |
   | `imd_subdivision_monthly_rainfall.csv` | data.gov.in resource `8e0bd482-4aba-4d99-9cb9-ff124f6f1c2f` |
   | `plfs_state_ur_usual_status_2017_22.csv` | data.gov.in resource `d038e512-231e-4adb-bbb7-a3f95102d18a` |

   Compare each file's SHA256 with `data\MANIFEST.md` (Section "Raw downloads").

3. Build the tables:

   ```powershell
   python scripts\run_pipeline.py
   python scripts\run_pipeline.py --verify
   ```

   A blocked table exits with code 2 and writes its findings to `outputs\review\<dataset>.csv`;
   see `scripts\README.md`. The Mandi resource is a rolling daily snapshot, so a new download
   does not reproduce the Milestone 4 hashes; use Route A to reproduce reported figures.

## 5. Download the embedding model once

Retrieval uses `BAAI/bge-small-en-v1.5` at a pinned revision. The code works offline by default
(`HF_HUB_OFFLINE=1`), so the model must be downloaded once, explicitly:

```powershell
$env:HF_HUB_OFFLINE = "0"
python -c "from sentence_transformers import SentenceTransformer as S; S('BAAI/bge-small-en-v1.5', revision='5c38ec7c405ec4b44b94cc5a9bb96e735b38267a', device='cpu'); print('model ok')"
Remove-Item Env:HF_HUB_OFFLINE
```

A warning about unauthenticated requests to the Hugging Face Hub is expected and harmless. The
model is cached under `%USERPROFILE%\.cache\huggingface`.

## 6. Run the tests

```powershell
python -m pytest
```

Expected on a clean clone with the Route A data: 550 passed, 19 skipped. The skipped tests need
the raw files or the Milestone 2 golden outputs and are skipped when those are absent.

## 7. Run the app

### 7.1 Stub mode (no cost)

```powershell
$env:AGENT_LLM = "stub"
uvicorn app.api.main:app --port 8000
```

Open http://localhost:8000/ and ask, for example, "Show monthly rainfall in Kerala". The page
streams each stage of the graph and then shows a placeholder answer ("The value is 1."): stub
mode proves the graph, data, retrieval and SQL layers work, not the answer text. Stop the
server with `Ctrl+C`.

Quick checks from a second PowerShell window:

```powershell
Invoke-RestMethod http://localhost:8000/healthz
Invoke-RestMethod http://localhost:8000/ask -Method Post -ContentType "application/json" `
    -Body '{"question": "Show monthly rainfall in Kerala"}'
```

The same agent from the command line:

```powershell
python scripts\run_agent.py --question "Show monthly rainfall in Kerala"
```

### 7.2 Live mode (spends cloud credit)

Live mode authenticates to Vertex AI with Google Application Default Credentials, obtained by
running `gcloud`. It needs two things from the team before the first run:

- access to the team's GCP project (T3 grants it; the project ID is shared privately, not in
  the repository);
- agreement on spending: each question costs about USD 0.02-0.03 (estimate), charged to the
  team's USD 300 credit. Ask before running more than a few questions.

Steps:

1. Install the Google Cloud CLI: https://cloud.google.com/sdk/docs/install#windows (keep the
   option that adds `gcloud` to PATH). In a **new** window, check `gcloud --version`.
2. Log in for application credentials, as agreed with T3 (directly, or through the project's
   service account with `--impersonate-service-account=<account>`):

   ```powershell
   gcloud auth application-default login
   ```

3. Start the app in live mode:

   ```powershell
   $env:GOOGLE_CLOUD_PROJECT = "<project id>"
   $env:AGENT_LLM = "live"
   $env:AGENT_VERSION = "v2"      # v0, v1 or v2; default v0
   uvicorn app.api.main:app --port 8000
   ```

   Or one question from the command line (`--yes` confirms the spend):

   ```powershell
   python scripts\run_agent.py --llm live --yes --version v2 `
       --question "What was the unemployment rate in Gujarat in 2021-22?" --save-chart
   ```

The routing variant with Jev (`$env:AGENT_VARIANT = "jev_routing"`) also needs
`$env:TYPESAFE_API_KEY`. Environment variables are read from the shell; the `.env` file is used
only by Docker Compose.

Live mode on Windows needs the `gcloud` lookup fix in `src\analyst\inference\llm.py` (branch
`fix/windows-setup`, until it is merged into `main`). Without it, every live call fails with
"no Vertex AI token" even after a successful login, because Windows installs `gcloud` as
`gcloud.cmd`, which a direct process launch does not find.

## 8. Windows differences handled by this guide

| Difference | Effect | Handled by |
| --- | --- | --- |
| Default text encoding is cp1252, not UTF-8 | `UnicodeDecodeError` when reading configs, prompts and data | `PYTHONUTF8=1` (Section 2) |
| `gcloud` is a `.cmd` script | Live calls report "no Vertex AI token" | Lookup fix on `fix/windows-setup` (Section 7.2) |
| PowerShell blocks unsigned scripts | `Activate.ps1` does not run | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Environment variables are set with `$env:NAME = "value"` | `NAME=value command` (bash syntax in the README) fails | PowerShell syntax throughout this guide |
| Paths use `\` | None in the code (it uses `pathlib`); only in typed commands | Either separator works in Python arguments |

## 9. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `UnicodeDecodeError: 'charmap' codec can't decode` | UTF-8 mode is off | Section 2; open a new window |
| `FileNotFoundError: data/processed/catalogue.json` or `configs/...` | Command run outside the repository root, or data missing | `cd` to the repository root; Section 4 |
| `LocalEntryNotFoundError` or "offline mode is enabled" | Embedding model not downloaded | Section 5 |
| "no Vertex AI token" | Not logged in, or the `gcloud` lookup fix is missing | `gcloud auth application-default login`; use `fix/windows-setup` |
| `403 PERMISSION_DENIED` from Vertex AI | The account has no access to the project | Ask T3 for access |
| Port 8000 already in use | Another server is running | `uvicorn app.api.main:app --port 8010` and open that port |
| `pip` fails to build a package | Python 3.14 or a 32-bit Python | Install 64-bit Python 3.13 |

## 10. Not covered

- **Docker Compose stack.** The API image does not yet copy `configs/` or the UI page, and the
  agent reads `data/processed` relative to the working directory rather than the mounted
  `/data/processed`, so the stack is not a working route to run the agent at present. Use the
  steps above.
- **Serving and training Kev.** `scripts\serve_kev.sh` and `scripts\score_kev_run.sh` are bash
  scripts; run them in WSL 2 (Ubuntu) or on macOS. Training runs on a Colab or Kaggle T4
  (`notebooks\kev_train_t4.ipynb`). The demonstration app does not need Kev.
- **WSL 2 as an alternative.** Inside WSL 2 (Ubuntu) the README's macOS and Linux commands apply
  unchanged, and neither the UTF-8 setting nor the `gcloud` fix is needed. The repository should
  then be cloned inside the Linux file system (`~/...`), not under `/mnt/c`, for speed.
