# CodeArchaeologist (retro-git)

CLI that turns a **finished project directory** into a new Git repository with a **realistic, chronological commit history**. The final tree matches the source exactly (with an automatic fix commit if the plan missed anything).

**New here?** Read the plain-language guide: **[USER_MANUAL.md](USER_MANUAL.md)**.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) (recommended, free, local) — default provider  
  Or `GROQ_API_KEY` for Groq’s free tier, or `--provider heuristic` with no API

## Install

```bash
cd /path/to/this/repo
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Pull a model for Ollama (example):

```bash
ollama pull llama3.2
```

## Usage

Run **`retro-git`** (no arguments) to open a **browser form** (local page on your Mac — avoids broken macOS Tk popups).

| Field | Notes |
|-------|--------|
| **Source** | Finished project directory (required) |
| **Target** | Leave blank to replace in place (backup in `software-engineering/old/&lt;name&gt;.old`) |
| **Publish GitHub** | Renames `owner/repo` → `owner/repo.old` (**private**), creates fresh `owner/repo` (**public**), pushes |
| **Undo last run** | Restores `<name>.old` locally; deletes new GitHub repo and renames `.old` back |
| **Provider / history days / commits** | Same as CLI flags below |
| **Dry run / strict / include .env** | Checkboxes |

CLI (optional):

```bash
retro-git generate \
  --source /path/to/finished-app \
  --target /path/to/output-repo \
  --history-days 14
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--provider` | `ollama` | `ollama`, `groq`, or `heuristic` |
| `--history-days` | `14` | Spread commit dates over N days |
| `--min-commits` / `--max-commits` | `3` / `20` | Enforced commit count range |
| `--dry-run` | off | Print plan only |
| `--strict` | off | Fail instead of auto fix commit on mismatch |
| `--force` | off | Clear target directory before run |
| `--include-secrets` | off | Include `.env` in manifest |

### Verify only

```bash
retro-git verify --source ./app --target ./history-repo
```

### Environment

| Variable | Purpose |
|----------|---------|
| `OLLAMA_BASE_URL` | Default `http://localhost:11434` |
| `OLLAMA_MODEL` | Default `llama3.2` |
| `GROQ_API_KEY` | Groq free tier fallback |
| `RETRO_GIT_AUTHOR_NAME` / `RETRO_GIT_AUTHOR_EMAIL` | Commit author (defaults to `git config` global name/email) |

## How it works

1. **Scan** — Walk the source tree (respecting ignore rules).
2. **Plan** — LLM (or heuristic) returns JSON: ordered commits, each with whole files.
3. **Execute** — Copy files step-by-step; `git add` + `git commit` with backdated timestamps.
4. **Verify** — SHA-256 tree compare; optional `chore: sync generated history with source tree` commit.

v1 uses **whole files per commit**; partial hunks are planned for a later release.

## Project layout

```
retro_git/
  scanner/     # manifest & stack detection
  llm/         # Ollama / Groq prompts & providers
  planner/     # validate & normalize plans
  executor/    # stage files & GitPython commits
  verify/      # tree diff & fix commit
  cli.py       # Typer entrypoint
```

## License

MIT
