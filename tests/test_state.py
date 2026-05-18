import json

from tmux_monitor.config import TmuxMonitorConfig
from tmux_monitor.detection import PaneClassification
from tmux_monitor.discovery import PaneInfo
from tmux_monitor.state import write_status


def test_write_status_includes_last_output_timestamp(tmp_path):
    config = TmuxMonitorConfig()
    config.state_dir = tmp_path
    config.panes_dir.mkdir(parents=True)

    pane = PaneInfo(
        pane_id="%1",
        session="work",
        window=1,
        pane_index=1,
        tty="/dev/ttys001",
        cwd="/tmp/repo",
        title="repo",
        current_command="codex",
    )
    log_path = config.panes_dir / pane.log_filename
    log_path.write_text("working\n", encoding="utf-8")

    write_status(
        config,
        {"work": [pane]},
        {"%1": PaneClassification("codex", "codex", 123, pane.tty, pane.title)},
        {},
        {},
        session_created_at={"work": "2026-05-18T12:00:00+00:00"},
    )

    data = json.loads(config.status_path.read_text(encoding="utf-8"))
    entry = data["sessions"]["work"]["panes"]["work:1.1"]

    assert entry["last_output_at"]
    assert entry["last_output_at"].endswith("+00:00")
