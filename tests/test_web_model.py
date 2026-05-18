from datetime import datetime, timedelta, timezone

from tmux_monitor.web_model import build_dashboard_rows, filter_dashboard_rows, find_row_by_key


def test_activity_filter_and_sort_uses_recent_output():
    now = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    status = {
        "sessions": {
            "work": {
                "created_at": "2026-05-18T11:00:00+00:00",
                "panes": {
                    "work:1.1": {
                        "type": "codex",
                        "pane_id": "%1",
                        "title": "repo",
                        "cwd": "/tmp/repo",
                        "last_output_at": (now - timedelta(seconds=20)).isoformat(),
                    },
                    "work:1.2": {
                        "type": "codex",
                        "pane_id": "%2",
                        "title": "repo",
                        "cwd": "/tmp/repo",
                        "last_output_at": (now - timedelta(minutes=10)).isoformat(),
                    },
                    "work:1.3": {
                        "type": "shell",
                        "pane_id": "%3",
                        "title": "zsh",
                        "cwd": "/tmp/repo",
                    },
                },
            }
        }
    }

    rows = build_dashboard_rows(status, now=now)

    assert [r["activity"] for r in rows] == ["active", "idle", "idle"]
    assert [r["pane_id"] for r in filter_dashboard_rows(rows, "agents only", "active first")] == ["%1", "%2"]
    assert [r["pane_id"] for r in filter_dashboard_rows(rows, "agents only", "active only")] == ["%1"]
    assert [r["pane_id"] for r in filter_dashboard_rows(rows, "agents only", "idle only")] == ["%2"]


def test_activity_falls_back_to_busy_title_for_existing_status_files():
    now = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    status = {
        "sessions": {
            "work": {
                "created_at": "2026-05-18T11:00:00+00:00",
                "panes": {
                    "work:1.1": {
                        "type": "codex",
                        "pane_id": "%1",
                        "title": "⠹ repo",
                        "cwd": "/tmp/repo",
                    }
                },
            }
        }
    }

    rows = build_dashboard_rows(status, now=now)

    assert rows[0]["activity"] == "active"
    assert rows[0]["activity_reason"] == "busy title"


def test_dashboard_rows_parse_window_index_from_legacy_pane_key():
    status = {
        "sessions": {
            "work": {
                "created_at": "2026-05-18T11:00:00+00:00",
                "panes": {
                    "work:7.1": {
                        "type": "codex",
                        "pane_id": "%1",
                        "title": "repo",
                        "cwd": "/tmp/repo",
                    }
                },
            }
        }
    }

    rows = build_dashboard_rows(status)

    assert rows[0]["window"] == 7


def test_dashboard_rows_have_stable_keys_for_persisted_selection():
    status = {
        "sessions": {
            "work": {
                "created_at": "2026-05-18T11:00:00+00:00",
                "panes": {
                    "work:7.1": {
                        "type": "codex",
                        "pane_id": "%1",
                        "window": 7,
                        "window_name": "repo",
                        "title": "repo",
                        "cwd": "/tmp/repo",
                    }
                },
            }
        }
    }

    rows = build_dashboard_rows(status)

    assert rows[0]["row_key"] == "work:7"
    assert find_row_by_key(rows, "work:7") == rows[0]
