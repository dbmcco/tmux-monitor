import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from tmux_monitor.cli import main
from tmux_monitor.config import TmuxMonitorConfig


def test_resume_snapshot_no_manifest(tmp_path, capsys):
    """resume-snapshot without manifest prints error."""
    with patch("sys.argv", ["tmux-monitor", "--state-dir", str(tmp_path), "resume-snapshot"]):
        rc = main()
    assert rc == 1
    captured = capsys.readouterr()
    assert "No resume manifest found" in captured.err


def test_resume_snapshot_with_manifest(tmp_path, capsys):
    """resume-snapshot prints formatted output from manifest."""
    config = TmuxMonitorConfig()
    config.state_dir = tmp_path
    manifest = {
        "last_heartbeat_at": "2026-05-15T14:32:00+00:00",
        "tmux_version": "3.4",
        "sessions": {
            "test": {
                "created_at": "",
                "windows": 1,
                "panes": {
                    "test:0.0": {
                        "type": "codex",
                        "cwd": "/tmp",
                        "title": "codex",
                        "current_command": "codex",
                        "pane_id": "%999",
                        "window": 0,
                        "pane": 0,
                        "last_task": "testing",
                        "summary": "summary text",
                        "resume_command": "cd /tmp && codex --resume",
                    }
                }
            }
        }
    }
    config.resume_manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    
    with patch("sys.argv", ["tmux-monitor", "--state-dir", str(tmp_path), "resume-snapshot"]):
        rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "Session: test" in captured.out
    assert "codex" in captured.out
    assert "testing" in captured.out


def test_resume_snapshot_generate_script(tmp_path, capsys):
    """resume-snapshot --generate-script writes a .sh file."""
    config = TmuxMonitorConfig()
    config.state_dir = tmp_path
    from pathlib import Path
    home = str(Path.home())
    manifest = {
        "last_heartbeat_at": "2026-05-15T14:32:00+00:00",
        "tmux_version": "3.4",
        "sessions": {
            "s": {
                "created_at": "",
                "windows": 1,
                "panes": {
                    "s:0.0": {
                        "type": "opencode",
                        "cwd": f"{home}/bar",
                        "title": "opencode",
                        "pane_id": "%1",
                        "window": 0,
                        "pane": 0,
                        "resume_command": "cd ~/bar && opencode --resume",
                    }
                }
            }
        }
    }
    config.resume_manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    
    with patch("sys.argv", ["tmux-monitor", "--state-dir", str(tmp_path), "resume-snapshot", "--generate-script"]):
        rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "Resume script written to:" in captured.out
    
    # Find the generated script
    scripts = list(Path.cwd().glob("tmux-resume-*.sh"))
    assert len(scripts) >= 1
    script = scripts[-1]
    assert "tmux new-session" in script.read_text()
    script.unlink()


def test_cleanup_no_stale_panes(capsys):
    """cleanup with no stale panes prints 'No stale panes found'."""
    with patch("tmux_monitor.cli.discover_all", return_value={}), \
         patch("sys.argv", ["tmux-monitor", "cleanup"]):
        rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "No stale panes found" in captured.out
