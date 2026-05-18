from unittest.mock import patch

from tmux_monitor.discovery import list_panes


def test_list_panes_queries_all_windows_in_session():
    with patch(
        "tmux_monitor.discovery._tmux_out",
        return_value=(
            "%1\ts\t1\t1\t/dev/ttys001\t/tmp\tpane one\tcodex\twindow one\t1\n"
            "%2\ts\t2\t1\t/dev/ttys002\t/tmp\tpane two\tcodex\twindow two\t0"
        ),
    ) as tmux_out:
        panes = list_panes("s")

    assert [pane.qualified_id for pane in panes] == ["s:1.1", "s:2.1"]
    assert [pane.title for pane in panes] == ["pane one", "pane two"]
    assert [pane.window_name for pane in panes] == ["window one", "window two"]
    assert [pane.window_active for pane in panes] == [True, False]
    assert tmux_out.call_args.args[:3] == ("list-panes", "-s", "-t")
    assert tmux_out.call_args.args[3] == "s"
