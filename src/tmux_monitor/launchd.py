# ABOUTME: launchd LaunchAgent installation helpers for tmux-monitor.
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any


LAUNCHD_LABEL = "com.braydon.driftdriver-tmux-monitor"
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def default_launch_agents_dir(home: Path | None = None) -> Path:
    base = Path.home() if home is None else Path(home).expanduser()
    return base / "Library" / "LaunchAgents"


def default_plist_path(home: Path | None = None) -> Path:
    return default_launch_agents_dir(home) / f"{LAUNCHD_LABEL}.plist"


def default_log_dir(home: Path | None = None) -> Path:
    base = Path.home() if home is None else Path(home).expanduser()
    return base / ".local" / "log"


def _program_arguments(
    python_executable: str | None = None,
    state_dir: Path | None = None,
) -> list[str]:
    args = [python_executable or sys.executable, "-m", "tmux_monitor.cli"]
    if state_dir is not None:
        args.extend(["--state-dir", str(Path(state_dir).expanduser())])
    args.append("start")
    return args


def build_plist(
    *,
    python_executable: str | None = None,
    home: Path | None = None,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    log_dir = default_log_dir(home)
    return {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": _program_arguments(python_executable, state_dir),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(log_dir / "tmux-monitor.out.log"),
        "StandardErrorPath": str(log_dir / "tmux-monitor.err.log"),
        "EnvironmentVariables": {
            "PATH": DEFAULT_PATH,
            "PYTHONUNBUFFERED": "1",
        },
    }


def write_plist(path: Path, plist: dict[str, Any]) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(plist, sort_keys=True))


def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def install_launch_agent(
    *,
    python_executable: str | None = None,
    home: Path | None = None,
    state_dir: Path | None = None,
    plist_path: Path | None = None,
    launch_agents_dir: Path | None = None,
    load: bool = True,
) -> Path:
    if plist_path is None:
        if launch_agents_dir is not None:
            plist_path = Path(launch_agents_dir).expanduser() / f"{LAUNCHD_LABEL}.plist"
        else:
            plist_path = default_plist_path(home)
    plist_path = Path(plist_path).expanduser()

    default_log_dir(home).mkdir(parents=True, exist_ok=True)
    write_plist(
        plist_path,
        build_plist(
            python_executable=python_executable,
            home=home,
            state_dir=state_dir,
        ),
    )

    if load:
        domain = _launchd_domain()
        subprocess.run(
            ["launchctl", "bootout", domain, str(plist_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(["launchctl", "bootstrap", domain, str(plist_path)], check=True)
        subprocess.run(["launchctl", "enable", f"{domain}/{LAUNCHD_LABEL}"], check=True)
        subprocess.run(["launchctl", "kickstart", "-k", f"{domain}/{LAUNCHD_LABEL}"], check=True)

    return plist_path


def uninstall_launch_agent(
    *,
    home: Path | None = None,
    plist_path: Path | None = None,
    unload: bool = True,
) -> Path:
    path = Path(plist_path).expanduser() if plist_path is not None else default_plist_path(home)
    if unload:
        subprocess.run(
            ["launchctl", "bootout", _launchd_domain(), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    if path.exists():
        path.unlink()
    return path


def launch_agent_status() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", "print", f"{_launchd_domain()}/{LAUNCHD_LABEL}"],
        capture_output=True,
        text=True,
        check=False,
    )
