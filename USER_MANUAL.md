# retro-git — User Manual

This guide is for anyone who wants to turn a **finished project folder** into a **new folder with a believable Git history**—without writing dozens of commits by hand.

You do **not** need to be a Git expert. You do need to be comfortable copying and pasting a few commands into a terminal.

---

## What does this tool do?

Imagine you built an app (or downloaded one) and all the code lives in a single folder. It works, but there is no story in Git—no “first I added the database,” then “then the login page,” and so on.

**retro-git** reads that finished folder and creates a **second folder** that contains:

- The **same files** as the original (when it finishes, nothing important should be missing or changed).
- A **series of Git commits** that look like the project was built step by step over time.
- **Dates on those commits** spread across the number of days you choose (for example, the last 14 days).

You keep your original folder untouched. The new folder is what you can open in GitHub Desktop, push to GitHub, or share with others.

---

## Words you might see

| Word | Plain meaning |
|------|----------------|
| **Source** | The folder with your finished project (the original). |
| **Target** | A new, empty folder where retro-git will build the history. |
| **Commit** | One saved snapshot in Git, with a short message like “add login page.” |
| **Repository (repo)** | A project folder that Git is tracking (you’ll see a hidden `.git` folder inside the target). |
| **Terminal** | The text window where you type commands (Terminal on Mac, Command Prompt or PowerShell on Windows). |

---

## What you need before you start

1. **Python** installed on your computer (version 3.10 or newer).  
   If you’re not sure, ask a technical friend to check, or try `python3 --version` in a terminal.

2. **This retro-git project** on your machine (the folder where you downloaded or cloned it).

3. **Your finished project** in its own folder—for example `~/Projects/my-app`.

4. **An empty folder** for the output—for example `~/Projects/my-app-with-history`.  
   Create it ahead of time, or let retro-git create it; it must not already contain other files (unless you use `--force`—see below).

5. **Optional but recommended:** [Ollama](https://ollama.com) installed.  
   Ollama runs a free AI on your own computer and helps retro-git decide a realistic order for commits.  
   If you skip Ollama, the tool still works using a simpler built-in ordering (less “human,” but fine for trying it out).

---

## One-time setup

### Use the project root folder (important)

Your project folder should look like this:

```text
CodeArchaeologist/          ← run all setup commands HERE
  pyproject.toml            ← this file must be present
  README.md
  retro_git/                ← Python package (do not install from inside this folder)
    cli.py
    ...
```

If you `cd` into `retro_git` and run `pip install`, you will see:

`does not appear to be a Python project: neither 'setup.py' nor 'pyproject.toml' found`

That is normal—you are one folder too deep. Go back up: `cd ..`

### Setup steps

Open a terminal and go to the **top-level** project folder (the one that contains `pyproject.toml` and the `retro_git` folder). Then run these lines **one at a time**:

```bash
cd /path/to/CodeArchaeologist
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

**Mac/Linux:** use `source .venv/bin/activate` as shown.

**Windows:** you may need:

```text
.venv\Scripts\activate
```

You only repeat this setup when you open a **new** terminal window later—then run `source .venv/bin/activate` again (or the Windows equivalent) before using retro-git.

### Optional: better commit ordering with Ollama

1. Install Ollama from [ollama.com](https://ollama.com).
2. In the terminal (with your virtual environment active):

```bash
ollama pull llama3.2
```

That downloads a language model retro-git can talk to. It’s free and stays on your machine.

---

## The main command (most people only need this)

Replace the paths with your real folders:

```bash
retro-git generate \
  --source /path/to/your-finished-project \
  --target /path/to/new-empty-output-folder \
  --history-days 14
```

**What each part means:**

- `--source` — where your finished code already lives.
- `--target` — where the new Git history will be created (must be empty, or use `--force`).
- `--history-days 14` — spread commit dates across the last 14 days. Use `30` for a month, `7` for a week, and so on.

### What you’ll see while it runs

1. **Scanning** — it lists how many files it found.
2. **Planning** — it decides the order of commits (using Ollama if available).
3. **Executing** — it copies files in batches and creates one commit per step.
4. **Verifying** — it checks that the output folder matches your source.

If verification fails, retro-git usually adds one last commit automatically to fix small gaps. You’ll see a message either way.

When it says **Done**, open the **target** folder—that’s your new repo.

---

## Try it without risk first (`--dry-run`)

Not sure you’re ready? Preview the plan without changing anything:

```bash
retro-git generate \
  --source /path/to/your-finished-project \
  --target /path/to/new-empty-output-folder \
  --dry-run
```

You’ll see a table of planned commit messages and how many files each step includes. No Git repo is created.

---

## After it finishes

- Open the **target** folder in your Git app (GitHub Desktop, VS Code, etc.).
- You should see a **timeline of commits** with messages like `feat: add user model`.
- Compare mentally: the **files inside target** should match your **source** folder (same code, same structure).

To double-check with retro-git:

```bash
retro-git verify \
  --source /path/to/your-finished-project \
  --target /path/to/output-folder
```

If it says **Trees match**, you’re good.

---

## Useful options (in plain language)

| Option | When to use it |
|--------|----------------|
| `--history-days 30` | Make the history look like it happened over a month instead of two weeks. |
| `--force` | The target folder has old junk in it and you want retro-git to clear it and start over. **Deletes contents of target** (not source). |
| `--dry-run` | See the plan only; don’t create commits. |
| `--provider heuristic` | Don’t use AI; use simple file-ordering rules (good for offline tests). |
| `--strict` | If something doesn’t match the source, **stop** instead of auto-fixing. |
| `--min-commits 5` / `--max-commits 25` | Ask for fewer or more commits in the plan. |

---

## Common problems

### “target directory is not empty”

Create a new empty folder for `--target`, or add `--force` if you’re sure nothing in target needs to be kept.

### “Ollama not reachable; using heuristic planner”

Ollama isn’t running or isn’t installed. Either:

- Start the Ollama app and try again, or  
- Continue with the built-in planner (works, but commit grouping may feel less natural), or  
- Install Ollama and run `ollama pull llama3.2`.

### “Planning failed” / invalid plan

The AI occasionally returns a bad plan. Try running **generate** again. For important projects, use `--dry-run` first.

### “command not found: retro-git”

Your virtual environment isn’t active. Run:

```bash
cd /path/to/CodeArchaeologist
source .venv/bin/activate
```

from the **project root** (not inside `retro_git/`), then try again.

### “does not appear to be a Python project”

You ran `pip install` inside the `retro_git` folder. Move up one level:

```bash
cd ..
pip install -e .
```

Create `.venv` in the project root too, not inside `retro_git`:

```bash
cd /path/to/CodeArchaeologist
rm -rf retro_git/.venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Secret files (`.env`)

By default, retro-git **ignores** `.env` files so passwords don’t end up in Git history. If you truly need them included (usually you don’t), ask someone technical before using `--include-secrets`.

---

## What retro-git does *not* do (yet)

- It does **not** change your original source folder.
- It does **not** push to GitHub for you—you still upload the target repo yourself.
- It adds **whole files** per commit, not half a file in one step and the rest later (that may come in a future version).
- It does **not** write commit messages for you after the fact in an existing repo—it builds a **new** repo from scratch.

---

## Typical workflow (checklist)

1. Put your finished app in a folder → that’s **source**.
2. Create an empty folder → that’s **target**.
3. Set up retro-git once (venv + `pip install -e .`).
4. Optional: install Ollama + `ollama pull llama3.2`.
5. Run `retro-git generate` with your paths and `--history-days`.
6. Run `retro-git verify` if you want peace of mind.
7. Open **target** in GitHub Desktop or push to GitHub.

---

## Getting more technical detail

Developers and power users can read [README.md](README.md) for install details, environment variables, and how the tool is structured internally.

---

## Need help?

- Read the **Common problems** section above.
- Run with `--dry-run` to see what would happen without writing Git history.
- Share the terminal output with someone technical if a step fails—the messages are meant to explain what went wrong.
