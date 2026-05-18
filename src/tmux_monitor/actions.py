# ABOUTME: Safe tmux action helpers used by the web UI and tests.
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TmuxActionResult:
    ok: bool
    message: str


def _run_tmux(args: list[str], timeout: int = 10) -> TmuxActionResult:
    try:
        result = subprocess.run(
            ["tmux", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return TmuxActionResult(False, str(exc))

    if result.returncode == 0:
        return TmuxActionResult(True, result.stdout.strip() or "ok")
    return TmuxActionResult(False, result.stderr.strip() or f"tmux exited {result.returncode}")


def kill_window(session: str, window_index: int) -> TmuxActionResult:
    return _run_tmux(["kill-window", "-t", f"{session}:{window_index}"], timeout=5)


def new_window(
    session: str,
    window_name: str,
    cwd: Path,
    *,
    start_codex: bool = False,
) -> TmuxActionResult:
    args = ["new-window", "-t", session]
    if window_name:
        args.extend(["-n", window_name])
    args.extend(["-c", str(cwd)])
    if start_codex:
        args.append("codex")
    return _run_tmux(args)


def new_session(session_name: str, cwd: Path) -> TmuxActionResult:
    return _run_tmux(["new-session", "-d", "-s", session_name, "-c", str(cwd)])


def start_codex_window(session: str, cwd: Path) -> TmuxActionResult:
    name = cwd.name or "codex"
    return new_window(session, name, cwd, start_codex=True)
