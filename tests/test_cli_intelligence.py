import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

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


def test_web_cli_uses_streamlit_without_importing_web_module(tmp_path):
    """web command locates web.py without executing Streamlit app imports."""
    web_path = tmp_path / "web.py"
    web_path.write_text("# test app\n", encoding="utf-8")
    spec = SimpleNamespace(origin=str(web_path))

    with patch("tmux_monitor.cli.importlib.util.find_spec", return_value=spec) as find_spec, \
         patch("tmux_monitor.cli.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run, \
         patch("sys.argv", ["tmux-monitor", "web", "--port", "8901"]):
        rc = main()

    assert rc == 0
    find_spec.assert_called_once_with("tmux_monitor.web")
    assert run.call_args.args[0] == [
        "streamlit",
        "run",
        str(web_path),
        "--server.port",
        "8901",
        "--server.headless",
        "true",
        "--server.address",
        "0.0.0.0",
    ]
