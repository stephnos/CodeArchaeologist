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
from retro_git.gui_common import (
    resolve_paths,
    run_generate_job,
    run_undo_job,
    undo_status_message,
)

DEFAULT_PROJECTS_DIR = Path.home() / "projects" / "software-engineering"


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
    :root { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: #1d1d1f; background: #f5f5f7; }
    body { max-width: 640px; margin: 0 auto; padding: 24px 20px 48px; }
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
  </style>
</head>
<body>
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
    <p class="hint">Leave blank: project stays same name; backup goes to software-engineering/.old/&lt;name&gt;.old</p>

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
      if (!confirm('Undo the last run? This restores your .old backup and reverts GitHub if published.')) {
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
