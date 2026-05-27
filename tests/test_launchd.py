import plistlib
from pathlib import Path
from unittest.mock import patch

from tmux_monitor.launchd import (
    LAUNCHD_LABEL,
    LAUNCHD_RECOVERY_LABEL,
    LAUNCHD_WEB_LABEL,
    build_plist,
    install_launch_agent,
    write_plist,
)
from tmux_monitor.cli import main


def test_build_plist_starts_tmux_monitor_at_login(tmp_path):
    plist = build_plist(
        python_executable="/opt/example/bin/python3",
        home=tmp_path,
    )

    assert plist["Label"] == LAUNCHD_LABEL
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is True
    assert plist["ProgramArguments"] == [
        "/opt/example/bin/python3",
        "-m",
        "tmux_monitor.cli",
        "start",
    ]
    assert plist["StandardOutPath"] == str(tmp_path / ".local" / "log" / "tmux-monitor.out.log")
    assert plist["StandardErrorPath"] == str(tmp_path / ".local" / "log" / "tmux-monitor.err.log")
    assert plist["EnvironmentVariables"]["PYTHONUNBUFFERED"] == "1"


def test_build_plist_includes_state_dir_before_subcommand(tmp_path):
    state_dir = tmp_path / "state"

    plist = build_plist(
        python_executable="/opt/example/bin/python3",
        home=tmp_path,
        state_dir=state_dir,
    )

    assert plist["ProgramArguments"] == [
        "/opt/example/bin/python3",
        "-m",
        "tmux_monitor.cli",
        "--state-dir",
        str(state_dir),
        "start",
    ]


def test_build_plist_starts_web_ui_at_login(tmp_path):
    plist = build_plist(
        service="web",
        python_executable="/opt/example/bin/python3",
        home=tmp_path,
        port=8901,
    )

    assert plist["Label"] == LAUNCHD_WEB_LABEL
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is True
    assert plist["ProgramArguments"] == [
        "/opt/example/bin/python3",
        "-m",
        "streamlit",
        "run",
        str(Path(__file__).parents[1] / "src" / "tmux_monitor" / "web.py"),
        "--server.port",
        "8901",
        "--server.headless",
        "true",
        "--server.address",
        "0.0.0.0",
    ]
    assert plist["StandardOutPath"] == str(tmp_path / ".local" / "log" / "tmux-monitor-web.out.log")
    assert plist["StandardErrorPath"] == str(tmp_path / ".local" / "log" / "tmux-monitor-web.err.log")


def test_build_plist_runs_recovery_boot_check_once_at_login(tmp_path):
    plist = build_plist(
        service="recovery",
        python_executable="/opt/example/bin/python3",
        home=tmp_path,
    )

    assert plist["Label"] == LAUNCHD_RECOVERY_LABEL
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is False
    assert plist["ProgramArguments"] == [
        "/opt/example/bin/python3",
        "-m",
        "tmux_monitor.cli",
        "recovery",
        "boot-check",
    ]
    assert plist["StandardOutPath"] == str(tmp_path / ".local" / "log" / "tmux-monitor-recovery.out.log")
    assert plist["StandardErrorPath"] == str(tmp_path / ".local" / "log" / "tmux-monitor-recovery.err.log")


def test_write_plist_round_trips(tmp_path):
    path = tmp_path / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
    plist = build_plist(python_executable="/opt/example/bin/python3", home=tmp_path)

    write_plist(path, plist)

    assert plistlib.loads(path.read_bytes()) == plist


def test_install_launch_agent_writes_plist_and_bootstraps(tmp_path):
    launch_agents_dir = tmp_path / "Library" / "LaunchAgents"

    with patch("tmux_monitor.launchd.os.getuid", return_value=501), \
         patch("tmux_monitor.launchd.subprocess.run") as run:
        path = install_launch_agent(
            python_executable="/opt/example/bin/python3",
            home=tmp_path,
            launch_agents_dir=launch_agents_dir,
        )

    assert path == launch_agents_dir / f"{LAUNCHD_LABEL}.plist"
    loaded = plistlib.loads(path.read_bytes())
    assert loaded["ProgramArguments"][0] == "/opt/example/bin/python3"
    assert run.call_args_list[0].args[0] == ["launchctl", "bootout", "gui/501", str(path)]
    assert run.call_args_list[1].args[0] == ["launchctl", "bootstrap", "gui/501", str(path)]
    assert run.call_args_list[2].args[0] == ["launchctl", "enable", f"gui/501/{LAUNCHD_LABEL}"]
    assert run.call_args_list[3].args[0] == ["launchctl", "kickstart", "-k", f"gui/501/{LAUNCHD_LABEL}"]


def test_install_web_launch_agent_writes_web_plist_and_bootstraps(tmp_path):
    launch_agents_dir = tmp_path / "Library" / "LaunchAgents"

    with patch("tmux_monitor.launchd.os.getuid", return_value=501), \
         patch("tmux_monitor.launchd.subprocess.run") as run:
        path = install_launch_agent(
            service="web",
            python_executable="/opt/example/bin/python3",
            home=tmp_path,
            launch_agents_dir=launch_agents_dir,
            port=8901,
        )

    assert path == launch_agents_dir / f"{LAUNCHD_WEB_LABEL}.plist"
    loaded = plistlib.loads(path.read_bytes())
    assert loaded["Label"] == LAUNCHD_WEB_LABEL
    assert "streamlit" in loaded["ProgramArguments"]
    assert loaded["ProgramArguments"][-6:] == [
        "--server.port",
        "8901",
        "--server.headless",
        "true",
        "--server.address",
        "0.0.0.0",
    ]
    assert run.call_args_list[0].args[0] == ["launchctl", "bootout", "gui/501", str(path)]
    assert run.call_args_list[1].args[0] == ["launchctl", "bootstrap", "gui/501", str(path)]
    assert run.call_args_list[2].args[0] == ["launchctl", "enable", f"gui/501/{LAUNCHD_WEB_LABEL}"]
    assert run.call_args_list[3].args[0] == ["launchctl", "kickstart", "-k", f"gui/501/{LAUNCHD_WEB_LABEL}"]


def test_launchd_install_cli_can_write_without_loading(tmp_path, capsys):
    plist_path = tmp_path / f"{LAUNCHD_LABEL}.plist"

    with patch(
        "sys.argv",
        [
            "tmux-monitor",
            "launchd",
            "install",
            "--no-load",
            "--plist-path",
            str(plist_path),
            "--python",
            "/opt/example/bin/python3",
        ],
    ):
        rc = main()

    assert rc == 0
    assert plist_path.exists()
    loaded = plistlib.loads(plist_path.read_bytes())
    assert loaded["ProgramArguments"][0] == "/opt/example/bin/python3"
    captured = capsys.readouterr()
    assert str(plist_path) in captured.out


def test_launchd_install_cli_can_write_web_without_loading(tmp_path, capsys):
    plist_path = tmp_path / f"{LAUNCHD_WEB_LABEL}.plist"

    with patch(
        "sys.argv",
        [
            "tmux-monitor",
            "launchd",
            "install",
            "--service",
            "web",
            "--no-load",
            "--plist-path",
            str(plist_path),
            "--python",
            "/opt/example/bin/python3",
            "--port",
            "8901",
        ],
    ):
        rc = main()

    assert rc == 0
    assert plist_path.exists()
    loaded = plistlib.loads(plist_path.read_bytes())
    assert loaded["Label"] == LAUNCHD_WEB_LABEL
    assert "streamlit" in loaded["ProgramArguments"]
    assert loaded["ProgramArguments"][-6:] == [
        "--server.port",
        "8901",
        "--server.headless",
        "true",
        "--server.address",
        "0.0.0.0",
    ]
    captured = capsys.readouterr()
    assert str(plist_path) in captured.out
