import subprocess
from pathlib import Path
from unittest.mock import patch

from tmux_monitor.actions import kill_window, new_session, new_window, start_codex_window


def _completed() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout="", stderr="")


def test_kill_window_targets_session_and_window_index():
    with patch("tmux_monitor.actions.subprocess.run", return_value=_completed()) as run:
        result = kill_window("work", 3)

    assert result.ok is True
    assert run.call_args.args[0] == ["tmux", "kill-window", "-t", "work:3"]


def test_new_window_can_start_codex_in_directory():
    cwd = Path("/tmp/repo")
    with patch("tmux_monitor.actions.subprocess.run", return_value=_completed()) as run:
        result = new_window("work", "repo", cwd, start_codex=True)

    assert result.ok is True
    assert run.call_args.args[0] == [
        "tmux",
        "new-window",
        "-t",
        "work",
        "-n",
        "repo",
        "-c",
        str(cwd),
        "codex",
    ]


def test_new_session_starts_detached_in_directory():
    cwd = Path("/tmp/repo")
    with patch("tmux_monitor.actions.subprocess.run", return_value=_completed()) as run:
        result = new_session("new-work", cwd)

    assert result.ok is True
    assert run.call_args.args[0] == ["tmux", "new-session", "-d", "-s", "new-work", "-c", str(cwd)]


def test_start_codex_creates_new_window_in_existing_session():
    with patch("tmux_monitor.actions.subprocess.run", return_value=_completed()) as run:
        result = start_codex_window("work", Path("/tmp/repo"))

    assert result.ok is True
    assert run.call_args.args[0] == [
        "tmux",
        "new-window",
        "-t",
        "work",
        "-n",
        "repo",
        "-c",
        "/tmp/repo",
        "codex",
    ]
