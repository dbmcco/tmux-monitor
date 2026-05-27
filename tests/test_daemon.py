from unittest.mock import patch

from tmux_monitor.config import TmuxMonitorConfig
from tmux_monitor.daemon import run_heartbeat
from tmux_monitor.detection import PaneClassification
from tmux_monitor.discovery import PaneInfo


def test_run_heartbeat_passes_pane_tails_to_resume_manifest(tmp_path):
    config = TmuxMonitorConfig()
    config.state_dir = tmp_path
    pane = PaneInfo(
        pane_id="%1",
        session="work",
        window=0,
        pane_index=0,
        tty="/dev/ttys001",
        cwd=str(tmp_path),
        title="codex",
        current_command="codex",
    )
    classification = PaneClassification(
        pane_type="codex",
        process_name="codex",
        pid=123,
        tty="/dev/ttys001",
        title="codex",
    )

    with patch("tmux_monitor.daemon.load_known_sessions", return_value={}), \
         patch("tmux_monitor.daemon.discover_all", return_value={"work": [pane]}), \
         patch("tmux_monitor.daemon.attach_pipe", return_value=True), \
         patch("tmux_monitor.daemon.capture_pane", return_value="visible pane text"), \
         patch("tmux_monitor.daemon.classify_pane", return_value=classification), \
         patch("tmux_monitor.daemon.trim_all_logs", return_value=0), \
         patch("tmux_monitor.daemon.prune_old_daily", return_value=0), \
         patch("tmux_monitor.daemon.save_known_sessions"), \
         patch("tmux_monitor.daemon.write_status"), \
         patch("tmux_monitor.daemon.write_resume_manifest") as write_resume:
        result = run_heartbeat(config)

    assert result["sessions"] == 1
    kwargs = write_resume.call_args.kwargs
    assert kwargs["pane_tails"] == {"work:0.0": "visible pane text"}
