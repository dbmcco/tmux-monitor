import json
from pathlib import Path

from tmux_monitor.resume import build_resume_manifest, write_resume_manifest, read_resume_manifest, format_snapshot_text, generate_resume_script
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
