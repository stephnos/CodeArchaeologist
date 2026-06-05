from __future__ import annotations

import cgi
import html
import json
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


def _parse_form_body(raw: bytes, content_type: str) -> dict[str, str]:
    """Parse POST body from browser forms (urlencoded or multipart)."""
    if content_type.startswith("multipart/form-data"):
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(len(raw)),
        }
        fs = cgi.FieldStorage(fp=BytesIO(raw), environ=environ, keep_blank_values=True)
        fields: dict[str, str] = {}
        for key in fs.keys():
            item = fs[key]
            if item is None:
                continue
            if isinstance(item, list):
                for sub in item:
                    if sub.filename:
                        continue
                    fields[key] = sub.value
            elif not item.filename:
                fields[key] = item.value
        return fields

    text = raw.decode("utf-8", errors="replace")
    return {k: v[0] for k, v in parse_qs(text, keep_blank_values=True).items()}

from retro_git.cli import ProviderChoice
from retro_git.github_history import (
    GitHubHistoryError,
    fetch_commit_history,
    last_published_github_url,
    parse_github_repo_url,
)
from retro_git.gui_common import (
    resolve_paths,
    run_generate_job,
    run_undo_job,
    undo_status_message,
)
from retro_git.layout import old_workspaces_root
from retro_git.old_repos import delete_old_backup, discover_old_backups

DEFAULT_PROJECTS_DIR = Path.home() / "projects" / "software-engineering"
DEFAULT_OLD_DIR = old_workspaces_root()
BACKGROUND_IMAGE = Path(__file__).resolve().parent / "static" / "background.png"


def _discover_repos(projects_dir_raw: str) -> tuple[list[dict[str, str]], str]:
    projects_dir = Path(projects_dir_raw).expanduser().resolve()
    if not projects_dir.is_dir():
        raise ValueError(f"Projects folder not found: {projects_dir}")
    repos: list[dict[str, str]] = []
    for entry in sorted(projects_dir.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        if (entry / ".git").is_dir():
            repos.append({"name": entry.name, "path": str(entry.resolve())})
    return repos, str(projects_dir)


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CodeArchaeologist — retro-git</title>
  <style>
    :root { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body {
      margin: 0;
      min-height: 100vh;
      background: #0d1117 url("/static/background.png") center / cover no-repeat fixed;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      background: rgba(13, 17, 23, 0.45);
      pointer-events: none;
      z-index: 0;
    }
    .wrap {
      position: relative;
      z-index: 1;
      max-width: 680px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }
    .panel {
      background: rgba(255, 255, 255, 0.94);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border-radius: 16px;
      padding: 28px 24px 32px;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
      color: #1d1d1f;
    }
    h1 { font-size: 1.5rem; margin: 0 0 6px; }
    .sub { color: #6e6e73; margin: 0 0 24px; font-size: 0.95rem; line-height: 1.4; }
    label { display: block; font-weight: 600; margin: 16px 0 6px; font-size: 0.9rem; }
    input[type=text], input[type=number], select {
      width: 100%; box-sizing: border-box; padding: 10px 12px;
      border: 1px solid #c7c7cc; border-radius: 8px; font-size: 1rem;
    }
    .hint { color: #6e6e73; font-size: 0.8rem; margin-top: 4px; }
    .row { display: flex; gap: 12px; align-items: center; }
    .row input[type=number] { width: 80px; }
    .checks { margin-top: 12px; }
    .checks label { font-weight: 400; display: flex; align-items: center; gap: 8px; margin: 8px 0; }
    button {
      margin-top: 24px; background: #0071e3; color: #fff; border: none;
      padding: 12px 24px; font-size: 1rem; border-radius: 8px; cursor: pointer;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    button.secondary {
      background: #fff; color: #0071e3; border: 1px solid #0071e3;
      margin-top: 12px; margin-left: 0;
    }
    .actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-top: 24px; }
    #status {
      margin-top: 20px; padding: 12px 14px; border-radius: 8px;
      background: #fff; border: 1px solid #e5e5ea; min-height: 1.2em;
    }
    #status.running { border-color: #0071e3; }
    #status.error { border-color: #ff3b30; color: #c41e16; }
    #status.ok { border-color: #34c759; }
    .nav { display: flex; gap: 16px; margin-bottom: 20px; font-size: 0.9rem; }
    .nav a { color: #0071e3; text-decoration: none; font-weight: 600; }
    .nav a.active { color: #1d1d1f; text-decoration: underline; }
    table.commits { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 0.9rem; }
    table.commits th, table.commits td {
      text-align: left; padding: 10px 8px; border-bottom: 1px solid #e5e5ea;
    }
    table.commits th { font-size: 0.8rem; color: #6e6e73; }
    table.commits td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
    table.commits td.add { color: #248a3d; }
    table.commits td.del { color: #d1242f; }
    table.commits td.msg { word-break: break-word; }
    table.commits td.sha { font-family: ui-monospace, monospace; color: #6e6e73; }
  </style>
</head>
<body>
  <div class="wrap">
  <div class="panel">
  <nav class="nav">
    <a href="/" class="active">Generate</a>
    <a href="/history">Commit history</a>
    <a href="/delete-old">Delete old repo</a>
  </nav>
  <h1>Generate Git history</h1>
  <p class="sub">Point at a finished project. retro-git builds a realistic, backdated commit timeline in the target folder.</p>

  <form id="form">
    <label for="projects_dir">Projects directory</label>
    <div class="row">
      <input id="projects_dir" name="projects_dir" type="text" value="__DEFAULT_PROJECTS_DIR__" />
      <button type="button" id="load_repos" class="secondary">Load repos</button>
    </div>
    <p class="hint">Pick a folder that contains your local repos.</p>

    <label for="repo_select">Repository</label>
    <select id="repo_select" name="repo_select">
      <option value="">-- Select a repo --</option>
    </select>
    <p class="hint">Selecting a repo auto-fills Source.</p>

    <label for="source">Source</label>
    <input id="source" name="source" type="text" placeholder="/path/to/finished-project" required />
    <p class="hint">Finished project directory (required)</p>

    <label for="target">Target</label>
    <input id="target" name="target" type="text" placeholder="/path/to/output-repo (optional)" />
    <p class="hint">Leave blank: project stays same name; backup goes to software-engineering/old/&lt;name&gt;.old</p>

    <label for="provider">Provider</label>
    <select id="provider" name="provider">
      <option value="ollama">ollama (local AI)</option>
      <option value="groq">groq (needs GROQ_API_KEY)</option>
      <option value="heuristic">heuristic (no AI)</option>
    </select>

    <label>History days</label>
    <input name="history_days" type="number" min="1" value="14" />

    <label>Commits (min – max)</label>
    <div class="row">
      <input name="min_commits" type="number" min="1" value="3" />
      <span>to</span>
      <input name="max_commits" type="number" min="1" value="20" />
    </div>

    <div class="checks">
      <label><input type="checkbox" name="publish_github" checked /> Create GitHub repo and push (renames old repo to .old)</label>
      <label><input type="checkbox" name="github_private" /> Private new GitHub repo</label>
      <label><input type="checkbox" name="dry_run" /> Dry run (plan only)</label>
      <label><input type="checkbox" name="strict" /> Strict (no auto fix commit)</label>
      <label><input type="checkbox" name="include_secrets" /> Include .env files</label>
    </div>

    <div class="actions">
      <button type="submit" id="submit">Generate history</button>
      <button type="button" id="undo" class="secondary" disabled>Undo last run</button>
    </div>
  </form>

  <div id="status">Fill in Source, then click Generate history. Progress also appears in the terminal.</div>
  </div>
  </div>

  <script>
    const form = document.getElementById('form');
    const statusEl = document.getElementById('status');
    const submitBtn = document.getElementById('submit');
    const undoBtn = document.getElementById('undo');
    const projectsDirInput = document.getElementById('projects_dir');
    const loadReposBtn = document.getElementById('load_repos');
    const repoSelect = document.getElementById('repo_select');
    const sourceInput = document.getElementById('source');
    let pollTimer = null;

    async function refreshUndo() {
      const r = await fetch('/api/undo-status');
      const data = await r.json();
      undoBtn.disabled = !data.available;
      undoBtn.title = data.message || '';
    }
    refreshUndo();

    async function refreshRepos() {
      const dir = projectsDirInput.value.trim();
      const query = new URLSearchParams({ projects_dir: dir });
      const r = await fetch('/api/repos?' + query.toString());
      const data = await r.json();
      repoSelect.innerHTML = '<option value="">-- Select a repo --</option>';
      if (!r.ok) {
        setStatus(data.message || 'Could not load repos', 'error');
        return;
      }
      for (const repo of data.repos || []) {
        const option = document.createElement('option');
        option.value = repo.path;
        option.textContent = repo.name;
        repoSelect.appendChild(option);
      }
      setStatus(`Loaded ${data.repos.length} repos from ${data.projects_dir}`, 'ok');
    }
    loadReposBtn.addEventListener('click', refreshRepos);
    repoSelect.addEventListener('change', () => {
      if (repoSelect.value) {
        sourceInput.value = repoSelect.value;
      }
    });
    refreshRepos();

    function setStatus(text, kind) {
      statusEl.textContent = text;
      statusEl.className = kind || '';
    }

    async function poll() {
      const r = await fetch('/api/status');
      const data = await r.json();
      if (data.running) {
        setStatus(data.message || 'Running…', 'running');
        return;
      }
      clearInterval(pollTimer);
      pollTimer = null;
      submitBtn.disabled = false;
      if (data.error) {
        setStatus(data.message, 'error');
      } else {
        setStatus(data.message, 'ok');
      }
      refreshUndo();
    }

    undoBtn.addEventListener('click', async () => {
      if (!confirm('Undo the last run? This restores your old/<name>.old backup and reverts GitHub if published.')) {
        return;
      }
      submitBtn.disabled = true;
      undoBtn.disabled = true;
      setStatus('Undoing…', 'running');
      const r = await fetch('/api/undo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
        body: 'undo_github=1',
      });
      const data = await r.json();
      if (!r.ok) {
        setStatus(data.message || 'Undo failed', 'error');
        submitBtn.disabled = false;
        refreshUndo();
        return;
      }
      setStatus(data.message || 'Undoing…', 'running');
      pollTimer = setInterval(poll, 800);
      poll();
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      submitBtn.disabled = true;
      setStatus('Starting…', 'running');
      const params = new URLSearchParams();
      for (const [key, value] of new FormData(form)) {
        if (String(value).trim() !== '') {
          params.append(key, value);
        }
      }
      const r = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
        body: params.toString(),
      });
      const data = await r.json();
      if (!r.ok) {
        setStatus(data.message || 'Request failed', 'error');
        submitBtn.disabled = false;
        return;
      }
      setStatus(data.message || 'Running…', 'running');
      pollTimer = setInterval(poll, 800);
      poll();
    });
  </script>
</body>
</html>
"""

_HISTORY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Commit history — retro-git</title>
  <style>
    :root { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body {
      margin: 0;
      min-height: 100vh;
      background: #0d1117 url("/static/background.png") center / cover no-repeat fixed;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      background: rgba(13, 17, 23, 0.45);
      pointer-events: none;
      z-index: 0;
    }
    .wrap {
      position: relative;
      z-index: 1;
      max-width: 900px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }
    .panel {
      background: rgba(255, 255, 255, 0.94);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border-radius: 16px;
      padding: 28px 24px 32px;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
      color: #1d1d1f;
    }
    h1 { font-size: 1.5rem; margin: 0 0 6px; }
    .sub { color: #6e6e73; margin: 0 0 24px; font-size: 0.95rem; line-height: 1.4; }
    label { display: block; font-weight: 600; margin: 16px 0 6px; font-size: 0.9rem; }
    input[type=text] {
      width: 100%; box-sizing: border-box; padding: 10px 12px;
      border: 1px solid #c7c7cc; border-radius: 8px; font-size: 1rem;
    }
    .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    button {
      margin-top: 16px; background: #0071e3; color: #fff; border: none;
      padding: 12px 24px; font-size: 1rem; border-radius: 8px; cursor: pointer;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    button.secondary {
      background: #fff; color: #0071e3; border: 1px solid #0071e3;
      margin-top: 16px;
    }
    .nav { display: flex; gap: 16px; margin-bottom: 20px; font-size: 0.9rem; }
    .nav a { color: #0071e3; text-decoration: none; font-weight: 600; }
    .nav a.active { color: #1d1d1f; text-decoration: underline; }
    #status {
      margin-top: 20px; padding: 12px 14px; border-radius: 8px;
      background: #fff; border: 1px solid #e5e5ea; min-height: 1.2em;
    }
    #status.error { border-color: #ff3b30; color: #c41e16; }
    #status.ok { border-color: #34c759; }
    table.commits { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 0.9rem; }
    table.commits th, table.commits td {
      text-align: left; padding: 10px 8px; border-bottom: 1px solid #e5e5ea;
    }
    table.commits th { font-size: 0.8rem; color: #6e6e73; }
    table.commits td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
    table.commits td.add { color: #248a3d; }
    table.commits td.del { color: #d1242f; }
    table.commits td.msg { word-break: break-word; }
    table.commits td.sha { font-family: ui-monospace, monospace; color: #6e6e73; }
  </style>
</head>
<body>
  <div class="wrap">
  <div class="panel">
  <nav class="nav">
    <a href="/">Generate</a>
    <a href="/history" class="active">Commit history</a>
    <a href="/delete-old">Delete old repo</a>
  </nav>
  <h1>Commit history</h1>
  <p class="sub">Paste a GitHub repo link to list commits in chronological order with line diff stats.</p>

  <form id="form">
    <label for="repo_url">GitHub repository URL</label>
    <input id="repo_url" name="repo_url" type="text" placeholder="https://github.com/owner/repo" required />
    <div class="row">
      <button type="submit" id="submit">Load commits</button>
      <button type="button" id="last_published" class="secondary">Use last published</button>
    </div>
  </form>

  <div id="status">Paste a GitHub URL or use the last published repo.</div>
  <div id="results"></div>
  </div>
  </div>

  <script>
    const form = document.getElementById('form');
    const statusEl = document.getElementById('status');
    const resultsEl = document.getElementById('results');
    const urlInput = document.getElementById('repo_url');
    const lastBtn = document.getElementById('last_published');

    function setStatus(text, kind) {
      statusEl.textContent = text;
      statusEl.className = kind || '';
    }

    function renderCommits(commits, repo) {
      if (!commits.length) {
        resultsEl.innerHTML = '';
        return;
      }
      const rows = commits.map(c => `
        <tr>
          <td class="num">${c.order}</td>
          <td class="msg">${escapeHtml(c.message)}</td>
          <td class="num add">+${c.additions}</td>
          <td class="num del">-${c.deletions}</td>
          <td class="sha">${escapeHtml(c.sha)}</td>
        </tr>`).join('');
      resultsEl.innerHTML = `
        <table class="commits">
          <thead>
            <tr><th>#</th><th>Commit</th><th>+</th><th>-</th><th>SHA</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>`;
      setStatus(`Loaded ${commits.length} commits from ${repo}`, 'ok');
    }

    function escapeHtml(s) {
      return String(s)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;');
    }

    async function refreshLastPublishedHint() {
      const r = await fetch('/api/last-github-url');
      const data = await r.json();
      lastBtn.disabled = !data.url;
      lastBtn.title = data.url || 'No published repo from the last generate run';
    }
    refreshLastPublishedHint();

    lastBtn.addEventListener('click', async () => {
      const r = await fetch('/api/last-github-url');
      const data = await r.json();
      if (!data.url) {
        setStatus('No GitHub URL from the last publish. Run generate with Publish GitHub enabled.', 'error');
        return;
      }
      urlInput.value = data.url;
      form.requestSubmit();
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const url = urlInput.value.trim();
      if (!url) return;
      setStatus('Loading commits…', '');
      resultsEl.innerHTML = '';
      const r = await fetch('/api/github-history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
        body: new URLSearchParams({ repo_url: url }).toString(),
      });
      const data = await r.json();
      if (!r.ok) {
        setStatus(data.message || 'Request failed', 'error');
        return;
      }
      renderCommits(data.commits || [], data.repo || url);
    });
  </script>
</body>
</html>
"""

_DELETE_OLD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Delete old repo — retro-git</title>
  <style>
    :root { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body {
      margin: 0;
      min-height: 100vh;
      background: #0d1117 url("/static/background.png") center / cover no-repeat fixed;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      background: rgba(13, 17, 23, 0.45);
      pointer-events: none;
      z-index: 0;
    }
    .wrap {
      position: relative;
      z-index: 1;
      max-width: 900px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }
    .panel {
      background: rgba(255, 255, 255, 0.94);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border-radius: 16px;
      padding: 28px 24px 32px;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
      color: #1d1d1f;
    }
    h1 { font-size: 1.5rem; margin: 0 0 6px; }
    .sub { color: #6e6e73; margin: 0 0 24px; font-size: 0.95rem; line-height: 1.4; }
    label { display: block; font-weight: 600; margin: 16px 0 6px; font-size: 0.9rem; }
    input[type=text] {
      width: 100%; box-sizing: border-box; padding: 10px 12px;
      border: 1px solid #c7c7cc; border-radius: 8px; font-size: 1rem;
    }
    .hint { color: #6e6e73; font-size: 0.8rem; margin-top: 4px; }
    .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    button {
      margin-top: 16px; background: #0071e3; color: #fff; border: none;
      padding: 12px 24px; font-size: 1rem; border-radius: 8px; cursor: pointer;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    button.secondary {
      background: #fff; color: #0071e3; border: 1px solid #0071e3;
      margin-top: 16px;
    }
    button.danger {
      background: #ff3b30; border: none;
    }
    .nav { display: flex; gap: 16px; margin-bottom: 20px; font-size: 0.9rem; flex-wrap: wrap; }
    .nav a { color: #0071e3; text-decoration: none; font-weight: 600; }
    .nav a.active { color: #1d1d1f; text-decoration: underline; }
    #status {
      margin-top: 20px; padding: 12px 14px; border-radius: 8px;
      background: #fff; border: 1px solid #e5e5ea; min-height: 1.2em;
    }
    #status.error { border-color: #ff3b30; color: #c41e16; }
    #status.ok { border-color: #34c759; }
    table.backups { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 0.9rem; }
    table.backups th, table.backups td {
      text-align: left; padding: 10px 8px; border-bottom: 1px solid #e5e5ea;
    }
    table.backups th { font-size: 0.8rem; color: #6e6e73; }
    table.backups td.path { font-family: ui-monospace, monospace; font-size: 0.82rem; color: #6e6e73; word-break: break-all; }
    .empty { color: #6e6e73; margin-top: 16px; }
  </style>
</head>
<body>
  <div class="wrap">
  <div class="panel">
  <nav class="nav">
    <a href="/">Generate</a>
    <a href="/history">Commit history</a>
    <a href="/delete-old" class="active">Delete old repo</a>
  </nav>
  <h1>Delete old repo</h1>
  <p class="sub">Browse backup folders (usually <code>software-engineering/old/&lt;name&gt;.old</code>) and permanently remove ones you no longer need.</p>

  <label for="old_dir">Old backups folder</label>
  <div class="row">
    <input id="old_dir" name="old_dir" type="text" value="__DEFAULT_OLD_DIR__" />
    <button type="button" id="load_backups" class="secondary">Load backups</button>
  </div>
  <p class="hint">Folders named <code>*.old</code> or <code>*.old.2</code> are listed.</p>

  <div class="row">
    <button type="button" id="delete_selected" class="danger" disabled>Delete selected</button>
  </div>

  <div id="status">Choose a folder, then click Load backups.</div>
  <div id="results"></div>
  </div>
  </div>

  <script>
    const oldDirInput = document.getElementById('old_dir');
    const loadBtn = document.getElementById('load_backups');
    const deleteBtn = document.getElementById('delete_selected');
    const statusEl = document.getElementById('status');
    const resultsEl = document.getElementById('results');
    let backups = [];

    function setStatus(text, kind) {
      statusEl.textContent = text;
      statusEl.className = kind || '';
    }

    function escapeHtml(s) {
      return String(s)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;');
    }

    function selectedPaths() {
      return [...document.querySelectorAll('input[name="pick"]:checked')].map(el => el.value);
    }

    function updateDeleteButton() {
      deleteBtn.disabled = selectedPaths().length === 0;
    }

    function renderBackups(items, oldDir) {
      backups = items || [];
      if (!backups.length) {
        resultsEl.innerHTML = '<p class="empty">No old backups found in this folder.</p>';
        setStatus(`No backups in ${oldDir}`, 'ok');
        updateDeleteButton();
        return;
      }
      const rows = backups.map(b => `
        <tr>
          <td><input type="checkbox" name="pick" value="${escapeHtml(b.path)}" /></td>
          <td>${escapeHtml(b.name)}</td>
          <td class="path">${escapeHtml(b.path)}</td>
          <td>${escapeHtml(b.modified)}</td>
        </tr>`).join('');
      resultsEl.innerHTML = `
        <table class="backups">
          <thead>
            <tr>
              <th><input type="checkbox" id="pick_all" title="Select all" /></th>
              <th>Name</th>
              <th>Path</th>
              <th>Modified (UTC)</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>`;
      document.getElementById('pick_all').addEventListener('change', (e) => {
        const checked = e.target.checked;
        for (const box of document.querySelectorAll('input[name="pick"]')) {
          box.checked = checked;
        }
        updateDeleteButton();
      });
      for (const box of document.querySelectorAll('input[name="pick"]')) {
        box.addEventListener('change', updateDeleteButton);
      }
      setStatus(`Found ${backups.length} backup(s) in ${oldDir}`, 'ok');
      updateDeleteButton();
    }

    async function refreshBackups() {
      const dir = oldDirInput.value.trim();
      const query = new URLSearchParams({ old_dir: dir });
      const r = await fetch('/api/old-repos?' + query.toString());
      const data = await r.json();
      if (!r.ok) {
        resultsEl.innerHTML = '';
        setStatus(data.message || 'Could not load backups', 'error');
        updateDeleteButton();
        return;
      }
      oldDirInput.value = data.old_dir;
      renderBackups(data.backups, data.old_dir);
    }

    loadBtn.addEventListener('click', refreshBackups);
    refreshBackups();

    deleteBtn.addEventListener('click', async () => {
      const paths = selectedPaths();
      if (!paths.length) return;
      const names = paths.map(p => p.split('/').pop()).join(', ');
      if (!confirm(`Permanently delete ${paths.length} backup(s)?\\n\\n${names}\\n\\nThis cannot be undone.`)) {
        return;
      }
      deleteBtn.disabled = true;
      setStatus('Deleting…', '');
      const r = await fetch('/api/delete-old-repos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_dir: oldDirInput.value.trim(), paths }),
      });
      const data = await r.json();
      if (!r.ok) {
        setStatus(data.message || 'Delete failed', 'error');
        updateDeleteButton();
        return;
      }
      const deleted = (data.deleted || []).length;
      const failed = (data.failed || []).length;
      let msg = `Deleted ${deleted} backup(s).`;
      if (failed) {
        msg += ` ${failed} failed.`;
      }
      setStatus(msg, failed ? 'error' : 'ok');
      await refreshBackups();
    });
  </script>
</body>
</html>
"""


class _JobState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.message = "Idle"
        self.error = False

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "running": self.running,
                "message": self.message,
                "error": self.error,
            }

    def set_running(self, msg: str) -> None:
        with self.lock:
            self.running = True
            self.message = msg
            self.error = False

    def set_done(self, code: int, msg: str) -> None:
        with self.lock:
            self.running = False
            self.message = msg
            self.error = code != 0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def launch_web_gui() -> None:
    state = _JobState()
    port = _free_port()
    url = f"http://127.0.0.1:{port}/"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/status":
                self._send_json(200, state.snapshot())
                return
            if path == "/api/repos":
                query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                requested = query.get("projects_dir", [str(DEFAULT_PROJECTS_DIR)])[0]
                try:
                    repos, resolved = _discover_repos(requested)
                except ValueError as exc:
                    self._send_json(400, {"message": str(exc)})
                    return
                self._send_json(200, {"projects_dir": resolved, "repos": repos})
                return
            if path == "/api/undo-status":
                available, message = undo_status_message()
                self._send_json(200, {"available": available, "message": message})
                return
            if path == "/api/last-github-url":
                self._send_json(200, {"url": last_published_github_url()})
                return
            if path in ("/history", "/history.html"):
                body = _HISTORY_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path in ("/delete-old", "/delete-old.html"):
                body = _DELETE_OLD_HTML.replace(
                    "__DEFAULT_OLD_DIR__",
                    html.escape(str(DEFAULT_OLD_DIR)),
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/old-repos":
                query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                requested = query.get("old_dir", [str(DEFAULT_OLD_DIR)])[0]
                try:
                    backups, resolved = discover_old_backups(requested)
                except ValueError as exc:
                    self._send_json(400, {"message": str(exc)})
                    return
                self._send_json(200, {"old_dir": resolved, "backups": backups})
                return
            if path in ("/", "/index.html"):
                body = _HTML.replace(
                    "__DEFAULT_PROJECTS_DIR__",
                    html.escape(str(DEFAULT_PROJECTS_DIR)),
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/static/background.png":
                if not BACKGROUND_IMAGE.is_file():
                    self.send_error(404)
                    return
                data = BACKGROUND_IMAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/undo":
                with state.lock:
                    if state.running:
                        self._send_json(409, {"message": "A job is already running."})
                        return
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b""
                fields = _parse_form_body(raw, self.headers.get("Content-Type", ""))
                undo_github = "undo_github" in fields

                state.set_running("Undoing last run…")

                def undo_worker() -> None:
                    code, msg = run_undo_job(undo_github=undo_github)
                    state.set_done(code, msg)

                threading.Thread(target=undo_worker, daemon=True).start()
                self._send_json(202, {"message": "Undo started.", "running": True})
                return

            if path == "/api/delete-old-repos":
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    self._send_json(400, {"message": "Invalid JSON body"})
                    return
                old_dir = str(payload.get("old_dir", "")).strip() or str(DEFAULT_OLD_DIR)
                paths = payload.get("paths") or []
                if not isinstance(paths, list) or not paths:
                    self._send_json(400, {"message": "paths must be a non-empty list"})
                    return

                deleted: list[str] = []
                failed: list[dict[str, str]] = []
                for item in paths:
                    path_str = str(item).strip()
                    if not path_str:
                        continue
                    try:
                        delete_old_backup(path_str, old_dir)
                        deleted.append(path_str)
                    except (ValueError, OSError) as exc:
                        failed.append({"path": path_str, "message": str(exc)})

                if not deleted and failed:
                    self._send_json(
                        400,
                        {
                            "message": failed[0]["message"],
                            "deleted": deleted,
                            "failed": failed,
                        },
                    )
                    return
                self._send_json(200, {"deleted": deleted, "failed": failed})
                return

            if path == "/api/github-history":
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b""
                fields = _parse_form_body(raw, self.headers.get("Content-Type", ""))
                repo_url = fields.get("repo_url", "").strip()
                if not repo_url:
                    self._send_json(400, {"message": "repo_url is required"})
                    return
                try:
                    owner, repo = parse_github_repo_url(repo_url)
                    commits = fetch_commit_history(owner, repo)
                except GitHubHistoryError as exc:
                    self._send_json(400, {"message": str(exc)})
                    return
                self._send_json(
                    200,
                    {
                        "repo": f"{owner}/{repo}",
                        "commits": [
                            {
                                "order": c.order,
                                "sha": c.sha,
                                "message": c.message,
                                "additions": c.additions,
                                "deletions": c.deletions,
                            }
                            for c in commits
                        ],
                    },
                )
                return

            if path != "/api/generate":
                self.send_error(404)
                return

            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            content_type = self.headers.get("Content-Type", "")
            fields = _parse_form_body(raw, content_type)

            with state.lock:
                if state.running:
                    self._send_json(409, {"message": "A job is already running."})
                    return

            source, target, force, relocate, err = resolve_paths(
                fields.get("source", ""),
                fields.get("target", ""),
            )
            if err:
                self._send_json(400, {"message": err})
                return

            try:
                history_days = max(1, int(fields.get("history_days", "14")))
                min_commits = max(1, int(fields.get("min_commits", "3")))
                max_commits = max(min_commits, int(fields.get("max_commits", "20")))
                provider = ProviderChoice(fields.get("provider", "ollama"))
            except (ValueError, KeyError) as exc:
                self._send_json(400, {"message": str(exc)})
                return

            dry_run = "dry_run" in fields
            strict = "strict" in fields
            include_secrets = "include_secrets" in fields
            publish_github = "publish_github" in fields
            github_private = "github_private" in fields

            state.set_running("Running… check the terminal for detailed progress.")

            def worker() -> None:
                code, msg = run_generate_job(
                    source,
                    target,
                    force=force,
                    relocate_to_old=relocate,
                    provider=provider,
                    history_days=history_days,
                    min_commits=min_commits,
                    max_commits=max_commits,
                    dry_run=dry_run,
                    strict=strict,
                    include_secrets=include_secrets,
                    publish_github=publish_github,
                    github_private=github_private,
                )
                state.set_done(code, msg)

            threading.Thread(target=worker, daemon=True).start()
            self._send_json(202, {"message": "Started.", "running": True})

    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"retro-git UI: {url}")
    print("Press Ctrl+C in this terminal to stop the server.")
    webbrowser.open(url)

    try:
        thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
