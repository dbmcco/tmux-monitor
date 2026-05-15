import os
import time
from pathlib import Path
from unittest.mock import MagicMock

from tmux_monitor.hygiene import is_stale, KNOWN_AGENT_COMMANDS, find_stale_panes, format_stale_report
from tmux_monitor.detection import PaneClassification


def test_is_stale_when_no_log_and_process_gone():
    """Pane with no log file and non-agent current_command is stale."""
    pane = MagicMock()
    pane.current_command = "bash"
    cls = PaneClassification(pane_type="codex", process_name="codex", pid=12345, tty="/dev/ttys001", title="codex")
    
    log_path = Path("/nonexistent/log")
    assert is_stale(pane, cls, log_path, days=2) is True


def test_is_stale_when_log_recent_and_process_alive():
    """Pane with recent log and matching agent command is NOT stale."""
    pane = MagicMock()
    pane.current_command = "codex"
    cls = PaneClassification(pane_type="codex", process_name="codex", pid=12345, tty="/dev/ttys001", title="codex")
    
    log_path = Path("/tmp/test_hygiene_recent.log")
    log_path.write_text("recent output")
    try:
        assert is_stale(pane, cls, log_path, days=2) is False
    finally:
        log_path.unlink()


def test_is_stale_shell_pane_never_stale():
    """Shell/idle panes are never stale."""
    pane = MagicMock()
    pane.current_command = "bash"
    cls = PaneClassification(pane_type="shell", process_name="bash", pid=0, tty="/dev/ttys002", title="bash")
    
    log_path = Path("/nonexistent")
    assert is_stale(pane, cls, log_path, days=2) is False


def test_is_stale_old_log_and_process_gone():
    """Pane with old log and process changed is stale."""
    pane = MagicMock()
    pane.current_command = "bash"
    cls = PaneClassification(pane_type="opencode", process_name="opencode", pid=0, tty="/dev/ttys003", title="opencode")
    
    log_path = Path("/tmp/test_hygiene_old.log")
    log_path.write_text("old output")
    # Set mtime to 3 days ago
    old_mtime = time.time() - (3 * 24 * 3600)
    os.utime(log_path, (old_mtime, old_mtime))
    try:
        assert is_stale(pane, cls, log_path, days=2) is True
    finally:
        log_path.unlink()


def test_find_stale_panes_with_mocked_sessions():
    """find_stale_panes returns correct StalePane entries."""
    from tmux_monitor.discovery import PaneInfo
    
    panes = [
        PaneInfo(
            session="sess1", window=0, pane_index=0,
            pane_id="%1", tty="/dev/ttys001",
            cwd="/tmp/foo", title="codex",
            current_command="bash",
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
    
    stale = find_stale_panes(sessions, classifications, Path("/nonexistent"), days=2)
    assert len(stale) == 1
    assert stale[0].qualified_id == "sess1:0.0"
    assert stale[0].agent_type == "codex"


def test_format_stale_report():
    from tmux_monitor.hygiene import StalePane
    panes = [
        StalePane(
            session="sess1", qualified_id="sess1:0.0", pane_id="%1",
            agent_type="codex", cwd="/tmp/foo",
            last_task="testing", summary="summary text",
            idle_hours=72.0, recommendation="kill",
        )
    ]
    report = format_stale_report(panes, dry_run=True)
    assert "Stale pane report" in report
    assert "sess1:0.0" in report
    assert "(dry-run) would kill" in report
