from unittest.mock import patch

from tmux_monitor.discovery import list_panes


def test_list_panes_queries_all_windows_in_session():
    with patch(
        "tmux_monitor.discovery._tmux_out",
        return_value="%1:s:1:1:/dev/ttys001:/tmp:one:codex\n%2:s:2:1:/dev/ttys002:/tmp:two:codex",
    ) as tmux_out:
        panes = list_panes("s")

    assert [pane.qualified_id for pane in panes] == ["s:1.1", "s:2.1"]
    assert tmux_out.call_args.args[:3] == ("list-panes", "-s", "-t")
    assert tmux_out.call_args.args[3] == "s"
