"""Optional tkinter UI. macOS system Tk is often broken; prefer the default browser UI."""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from retro_git.cli import ProviderChoice
from retro_git.gui_common import resolve_paths, run_generate_job

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

_BG = "#f5f5f7"
_FG = "#1d1d1f"
_MUTED = "#6e6e73"


def _configure_style(root: tk.Tk) -> ttk.Style:
    style = ttk.Style(root)
    if sys.platform == "darwin":
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
    style.configure(".", background=_BG, foreground=_FG)
    style.configure("TFrame", background=_BG)
    style.configure("TLabel", background=_BG, foreground=_FG)
    style.configure("Muted.TLabel", background=_BG, foreground=_MUTED, font=("", 11))
    style.configure("TEntry", fieldbackground="white", foreground=_FG)
    style.configure("TCheckbutton", background=_BG, foreground=_FG)
    style.configure("Header.TLabel", background=_BG, foreground=_FG, font=("", 13, "bold"))
    root.configure(bg=_BG)
    return style


def _browse(entry: tk.Entry, parent: tk.Tk) -> None:
    path = filedialog.askdirectory(parent=parent)
    if path:
        entry.delete(0, tk.END)
        entry.insert(0, path)


def _path_row(parent: ttk.Frame, label: str, hint: str, browse_parent: tk.Tk) -> tk.Entry:
    row = ttk.Frame(parent)
    row.pack(fill=tk.X, pady=(0, 10))
    ttk.Label(row, text=label, width=14).pack(side=tk.LEFT, anchor=tk.N)
    right = ttk.Frame(row)
    right.pack(side=tk.LEFT, fill=tk.X, expand=True)
    entry = ttk.Entry(right)
    entry.pack(fill=tk.X, expand=True, pady=(0, 4))
    ttk.Button(right, text="Browse…", command=lambda: _browse(entry, browse_parent)).pack(
        anchor=tk.W
    )
    if hint:
        ttk.Label(right, text=hint, style="Muted.TLabel", wraplength=360).pack(anchor=tk.W)
    return entry


def launch_tk_gui() -> None:
    root = tk.Tk()
    root.title("CodeArchaeologist — retro-git")
    root.minsize(520, 520)
    _configure_style(root)

    outer = ttk.Frame(root, padding=16)
    outer.pack(fill=tk.BOTH, expand=True)

    ttk.Label(outer, text="Generate Git history", style="Header.TLabel").pack(anchor=tk.W)
    source_entry = _path_row(outer, "Source", "Finished project directory (required)", root)
    target_entry = _path_row(
        outer,
        "Target",
        "Leave blank: backup goes to software-engineering/.old/<name>.old",
        root,
    )

    opts = ttk.Frame(outer)
    opts.pack(fill=tk.X, pady=(4, 8))
    provider_var = tk.StringVar(value=ProviderChoice.ollama.value)
    ttk.Label(opts, text="Provider", width=14).grid(row=0, column=0, sticky=tk.W, pady=6)
    provider_combo = ttk.Combobox(
        opts,
        textvariable=provider_var,
        values=[p.value for p in ProviderChoice],
        state="readonly",
        width=24,
    )
    provider_combo.grid(row=0, column=1, sticky=tk.W, pady=6)

    history_entry = ttk.Entry(opts, width=10)
    history_entry.insert(0, "14")
    ttk.Label(opts, text="History days", width=14).grid(row=1, column=0, sticky=tk.W, pady=6)
    history_entry.grid(row=1, column=1, sticky=tk.W, pady=6)

    commits_row = ttk.Frame(opts)
    ttk.Label(opts, text="Commits (min–max)", width=14).grid(row=2, column=0, sticky=tk.W, pady=6)
    commits_row.grid(row=2, column=1, sticky=tk.W, pady=6)
    min_entry = ttk.Entry(commits_row, width=6)
    min_entry.insert(0, "3")
    min_entry.pack(side=tk.LEFT)
    max_entry = ttk.Entry(commits_row, width=6)
    max_entry.insert(0, "50")
    max_entry.pack(side=tk.LEFT)

    dry_run_var = tk.BooleanVar(value=False)
    strict_var = tk.BooleanVar(value=False)
    secrets_var = tk.BooleanVar(value=False)
    flags = ttk.Frame(outer)
    flags.pack(fill=tk.X, pady=8)
    ttk.Checkbutton(flags, text="Dry run", variable=dry_run_var).pack(anchor=tk.W)
    ttk.Checkbutton(flags, text="Strict", variable=strict_var).pack(anchor=tk.W)
    ttk.Checkbutton(flags, text="Include .env", variable=secrets_var).pack(anchor=tk.W)

    status_var = tk.StringVar(value="Fill in Source, then click Generate.")
    ttk.Label(outer, textvariable=status_var, wraplength=480).pack(anchor=tk.W, pady=(12, 8))
    run_btn = ttk.Button(outer, text="Generate history")

    def on_generate() -> None:
        source, target, force, relocate, err = resolve_paths(
            source_entry.get(), target_entry.get()
        )
        if err:
            messagebox.showwarning("Input", err)
            return
        try:
            history_days = max(1, int(history_entry.get()))
            min_commits = max(1, int(min_entry.get()))
            max_commits = max(min_commits, int(max_entry.get()))
            provider = ProviderChoice(provider_var.get())
        except (ValueError, KeyError) as exc:
            messagebox.showwarning("Input", str(exc))
            return

        run_btn.config(state=tk.DISABLED)
        status_var.set("Running…")

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
                dry_run=dry_run_var.get(),
                strict=strict_var.get(),
                include_secrets=secrets_var.get(),
                publish_github=True,
                github_private=False,
            )

            def finish() -> None:
                run_btn.config(state=tk.NORMAL)
                status_var.set(msg)
                if code == 0:
                    messagebox.showinfo("Done", msg)
                else:
                    messagebox.showerror("Error", msg)

            root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    run_btn.config(command=on_generate)
    run_btn.pack(anchor=tk.W)
    root.update_idletasks()
    root.mainloop()
