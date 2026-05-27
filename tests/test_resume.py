import json
from pathlib import Path

from tmux_monitor.resume import (
    build_resume_manifest,
    format_recovery_report,
    format_snapshot_text,
    generate_recovery_script,
    generate_resume_script,
    read_resume_manifest,
    write_resume_manifest,
)
from tmux_monitor.config import TmuxMonitorConfig
from tmux_monitor.detection import PaneClassification


def test_manifest_round_trip(tmp_path):
    config = TmuxMonitorConfig()
    config.state_dir = tmp_path
    
    manifest = {
        "last_heartbeat_at": "2026-05-15T14:32:00+00:00",
        "tmux_version": "3.4",
        "sessions": {},
    }
    
    write_resume_manifest(config, manifest)
    assert config.resume_manifest_path.exists()
    
    loaded = read_resume_manifest(config)
    assert loaded == manifest


def test_build_resume_manifest_filters_shells():
    """Only agent panes appear in the resume manifest."""
    from tmux_monitor.discovery import PaneInfo
    
    panes = [
        PaneInfo(
            session="sess1", window=0, pane_index=0,
            pane_id="%1", tty="/dev/ttys001",
            cwd="/tmp/foo", title="codex",
            current_command="codex",
        ),
        PaneInfo(
            session="sess1", window=0, pane_index=1,
            pane_id="%2", tty="/dev/ttys002",
            cwd="/tmp/bar", title="bash",
            current_command="bash",
        ),
    ]
    sessions = {"sess1": panes}
    classifications = {
        "%1": PaneClassification(pane_type="codex", process_name="codex", pid=123, tty="/dev/ttys001", title="codex"),
        "%2": PaneClassification(pane_type="shell", process_name="bash", pid=0, tty="/dev/ttys002", title="bash"),
    }
    
    manifest = build_resume_manifest(sessions, classifications, {}, {}, {})
    assert "sess1" in manifest["sessions"]
    panes_data = manifest["sessions"]["sess1"]["panes"]
    assert "sess1:0.0" in panes_data
    assert "sess1:0.1" not in panes_data


def test_build_resume_manifest_includes_pane_tail_log_path_and_git_state(tmp_path):
    """Recovery manifest captures enough local state to orient post-reboot agents."""
    from tmux_monitor.discovery import PaneInfo

    repo = tmp_path / "repo"
    repo.mkdir()
    import subprocess

    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_text("hello\nchanged\n", encoding="utf-8")

    pane = PaneInfo(
        session="work",
        window=2,
        pane_index=1,
        pane_id="%9",
        tty="/dev/ttys009",
        cwd=str(repo),
        title="codex",
        current_command="codex",
        window_name="recover",
    )

    manifest = build_resume_manifest(
        {"work": [pane]},
        {"%9": PaneClassification(pane_type="codex", process_name="codex", pid=123, tty="/dev/ttys009", title="codex")},
        {"work:2.1": {"current_task": "building recovery", "summary": "Implementing restart recovery."}},
        {"work:2.1": "2026-05-27T10:00:00+00:00"},
        {"work": "2026-05-27T09:00:00+00:00"},
        pane_tails={"work:2.1": "last visible pane text"},
        pane_log_paths={"work:2.1": tmp_path / "panes" / "work_2.1.log"},
    )

    entry = manifest["sessions"]["work"]["panes"]["work:2.1"]
    assert entry["window_name"] == "recover"
    assert entry["pane_tail"] == "last visible pane text"
    assert entry["pane_log_path"].endswith("work_2.1.log")
    assert entry["git"]["is_repo"] is True
    assert entry["git"]["dirty"] is True
    assert entry["auto_resume"]["safe"] is False
    assert "dirty git worktree" in entry["auto_resume"]["reasons"]


def test_format_recovery_report_surfaces_boot_context_and_next_actions():
    manifest = {
        "last_heartbeat_at": "2026-05-27T14:32:00+00:00",
        "host": "bmbp",
        "boot_id": "boot-a",
        "sessions": {
            "work": {
                "created_at": "",
                "windows": 1,
                "panes": {
                    "work:2.1": {
                        "type": "codex",
                        "cwd": "/tmp/repo",
                        "last_task": "building recovery",
                        "summary": "Implementing restart recovery.",
                        "pane_log_path": "/tmp/panes/work_2.1.log",
                        "auto_resume": {"safe": False, "reasons": ["dirty git worktree"]},
                    }
                },
            }
        },
    }

    report = format_recovery_report(manifest)

    assert "Last heartbeat: 2026-05-27T14:32:00+00:00" in report
    assert "Host: bmbp" in report
    assert "work:2.1 [codex]" in report
    assert "building recovery" in report
    assert "dirty git worktree" in report
    assert "tmux-monitor recovery script" in report


def test_generate_recovery_script_recreates_windows_without_starting_agents():
    manifest = {
        "last_heartbeat_at": "2026-05-27T14:32:00+00:00",
        "sessions": {
            "work": {
                "created_at": "",
                "windows": 2,
                "panes": {
                    "work:2.1": {
                        "type": "codex",
                        "cwd": "/tmp/repo",
                        "window": 2,
                        "pane": 1,
                        "window_name": "recover",
                        "resume_command": "cd /tmp/repo && codex --resume",
                    }
                },
            }
        },
    }

    script = generate_recovery_script(manifest)

    assert "tmux new-session -d -s 'work' -n 'recover' -c '/tmp/repo'" in script
    assert "codex --resume" not in script
    assert "Post-restart recovery" in script


def test_format_snapshot_text():
    manifest = {
        "last_heartbeat_at": "2026-05-15T14:32:00+00:00",
        "tmux_version": "3.4",
        "sessions": {
            "test": {
                "created_at": "2026-05-10T09:00:00+00:00",
                "windows": 1,
                "panes": {
                    "test:0.0": {
                        "type": "codex",
                        "cwd": "/home/user/projects/foo",
                        "title": "codex",
                        "current_command": "codex",
                        "pane_id": "%123",
                        "window": 0,
                        "pane": 0,
                        "last_task": "implementing tests",
                        "summary": "Writing unit tests for the new feature.",
                        "resume_command": "cd ~/projects/foo && codex --resume",
                    }
                }
            }
        }
    }
    text = format_snapshot_text(manifest)
    assert "Session: test" in text
    assert "codex" in text
    assert "implementing tests" in text
    assert "cd ~/projects/foo" in text
    assert "resume: cd ~/projects/foo && codex --resume" in text


def test_generate_resume_script():
    from pathlib import Path
    home = str(Path.home())
    manifest = {
        "last_heartbeat_at": "2026-05-15T14:32:00+00:00",
        "tmux_version": "3.4",
        "sessions": {
            "sess-a": {
                "created_at": "",
                "windows": 1,
                "panes": {
                    "sess-a:0.0": {
                        "type": "opencode",
                        "cwd": f"{home}/bar",
                        "title": "opencode",
                        "pane_id": "%456",
                        "window": 0,
                        "pane": 0,
                        "resume_command": "cd ~/bar && opencode --resume",
                    }
                }
            }
        }
    }
    script = generate_resume_script(manifest)
    assert "#!/usr/bin/env bash" in script
    assert "tmux new-session -d -s 'sess-a'" in script
    assert "cd ~/bar" in script
    assert "Manually start agents" in script
