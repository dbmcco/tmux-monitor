# ABOUTME: launchd LaunchAgent installation helpers for tmux-monitor.
from __future__ import annotations

import importlib.util
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal


LAUNCHD_LABEL = "com.braydon.driftdriver-tmux-monitor"
LAUNCHD_WEB_LABEL = "com.braydon.driftdriver-tmux-monitor-web"
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LaunchdService = Literal["monitor", "web"]


def label_for_service(service: LaunchdService = "monitor") -> str:
    if service == "monitor":
        return LAUNCHD_LABEL
    if service == "web":
        return LAUNCHD_WEB_LABEL
    raise ValueError(f"unknown launchd service: {service}")


def default_launch_agents_dir(home: Path | None = None) -> Path:
    base = Path.home() if home is None else Path(home).expanduser()
    return base / "Library" / "LaunchAgents"


def default_plist_path(home: Path | None = None, service: LaunchdService = "monitor") -> Path:
    return default_launch_agents_dir(home) / f"{label_for_service(service)}.plist"


def default_log_dir(home: Path | None = None) -> Path:
    base = Path.home() if home is None else Path(home).expanduser()
    return base / ".local" / "log"


def _program_arguments(
    python_executable: str | None = None,
    state_dir: Path | None = None,
    service: LaunchdService = "monitor",
    port: int = 8901,
) -> list[str]:
    if service == "monitor":
        args = [python_executable or sys.executable, "-m", "tmux_monitor.cli"]
        if state_dir is not None:
            args.extend(["--state-dir", str(Path(state_dir).expanduser())])
        args.append("start")
        return args
    return [
        python_executable or sys.executable,
        "-m",
        "streamlit",
        "run",
        str(_web_module_path()),
        "--server.port",
        str(port),
        "--server.headless",
        "true",
        "--server.address",
        "0.0.0.0",
    ]


def _web_module_path() -> Path:
    spec = importlib.util.find_spec("tmux_monitor.web")
    if spec is None or spec.origin is None:
        raise RuntimeError("Could not find tmux_monitor.web")
    return Path(spec.origin)


def _log_basename(service: LaunchdService) -> str:
    if service == "monitor":
        return "tmux-monitor"
    return "tmux-monitor-web"


def build_plist(
    *,
    service: LaunchdService = "monitor",
    python_executable: str | None = None,
    home: Path | None = None,
    state_dir: Path | None = None,
    port: int = 8901,
) -> dict[str, Any]:
    log_dir = default_log_dir(home)
    log_basename = _log_basename(service)
    return {
        "Label": label_for_service(service),
        "ProgramArguments": _program_arguments(python_executable, state_dir, service, port),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(log_dir / f"{log_basename}.out.log"),
        "StandardErrorPath": str(log_dir / f"{log_basename}.err.log"),
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
    service: LaunchdService = "monitor",
    python_executable: str | None = None,
    home: Path | None = None,
    state_dir: Path | None = None,
    plist_path: Path | None = None,
    launch_agents_dir: Path | None = None,
    port: int = 8901,
    load: bool = True,
) -> Path:
    if plist_path is None:
        if launch_agents_dir is not None:
            plist_path = Path(launch_agents_dir).expanduser() / f"{label_for_service(service)}.plist"
        else:
            plist_path = default_plist_path(home, service)
    plist_path = Path(plist_path).expanduser()

    default_log_dir(home).mkdir(parents=True, exist_ok=True)
    write_plist(
        plist_path,
        build_plist(
            service=service,
            python_executable=python_executable,
            home=home,
            state_dir=state_dir,
            port=port,
        ),
    )

    if load:
        domain = _launchd_domain()
        label = label_for_service(service)
        subprocess.run(
            ["launchctl", "bootout", domain, str(plist_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(["launchctl", "bootstrap", domain, str(plist_path)], check=True)
        subprocess.run(["launchctl", "enable", f"{domain}/{label}"], check=True)
        subprocess.run(["launchctl", "kickstart", "-k", f"{domain}/{label}"], check=True)

    return plist_path


def uninstall_launch_agent(
    *,
    service: LaunchdService = "monitor",
    home: Path | None = None,
    plist_path: Path | None = None,
    unload: bool = True,
) -> Path:
    path = Path(plist_path).expanduser() if plist_path is not None else default_plist_path(home, service)
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


def launch_agent_status(service: LaunchdService = "monitor") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", "print", f"{_launchd_domain()}/{label_for_service(service)}"],
        capture_output=True,
        text=True,
        check=False,
    )
