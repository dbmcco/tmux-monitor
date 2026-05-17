# ABOUTME: CLI subcommand for tmux-monitor — start/stop/status/sessions/logs.
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

from tmux_monitor.config import TmuxMonitorConfig
from tmux_monitor.daemon import run_daemon, run_heartbeat
from tmux_monitor.relevance import (
    format_relevant_json,
    format_relevant_text,
)
from tmux_monitor.resume import read_resume_manifest, format_snapshot_text, generate_resume_script
from tmux_monitor.hygiene import find_stale_panes, format_stale_report, kill_panes
from tmux_monitor.discovery import discover_all, capture_pane
from tmux_monitor.detection import classify_pane
from tmux_monitor.launchd import install_launch_agent, launch_agent_status, uninstall_launch_agent


def _load_config(args: argparse.Namespace) -> TmuxMonitorConfig:
    state_dir = getattr(args, "state_dir", None)
    if state_dir:
        cfg_path = Path(state_dir) / "config.json"
        cfg = TmuxMonitorConfig.load(cfg_path)
        cfg.state_dir = Path(state_dir)
        return cfg
    default_path = TmuxMonitorConfig().state_dir / "config.json"
    return TmuxMonitorConfig.load(default_path)


def _load_status(config: TmuxMonitorConfig) -> dict | None:
    path = config.status_path
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def cmd_start(args: argparse.Namespace) -> int:
    config = _load_config(args)
    run_daemon(config)
    return 0


def cmd_heartbeat(args: argparse.Namespace) -> int:
    config = _load_config(args)
    result = run_heartbeat(config)
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
    else:
        print(f"Sessions: {result['sessions']}")
        print(f"Panes: {result['panes']}")
        if result["events"]:
            print(f"Events: {', '.join(result['events'])}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = _load_config(args)
    data = _load_status(config)
    if data is None:
        print("No status file found. Run `driftdriver tmux-monitor heartbeat` first.", file=sys.stderr)
        return 1

    target_path = getattr(args, "cwd", None) or ""
    target_repo = getattr(args, "repo", None) or ""
    if not target_path and not target_repo:
        target_path = str(Path.cwd())

    use_json = getattr(args, "json", False)
    include_all = getattr(args, "all", False)

    if use_json:
        out = format_relevant_json(data, target_repo=target_repo, target_path=target_path, include_unrelated=include_all)
        print(json.dumps(out, indent=2))
    else:
        text = format_relevant_text(data, target_repo=target_repo, target_path=target_path, include_unrelated=include_all)
        print(text)
    return 0


def cmd_sessions(args: argparse.Namespace) -> int:
    config = _load_config(args)
    data = _load_status(config)
    if data is None:
        print("No status file found.", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        sessions = {}
        for s, sd in data.get("sessions", {}).items():
            agent_types = set()
            for pd in sd.get("panes", {}).values():
                t = pd.get("type", "unknown")
                if t not in ("shell", "idle"):
                    agent_types.add(t)
            sessions[s] = {"windows": sd["windows"], "agents": sorted(agent_types)}
        print(json.dumps(sessions, indent=2))
        return 0

    for sess_name, sess_data in data.get("sessions", {}).items():
        agent_types = set()
        pane_count = len(sess_data.get("panes", {}))
        for pd in sess_data.get("panes", {}).values():
            t = pd.get("type", "unknown")
            if t not in ("shell", "idle"):
                agent_types.add(t)
        agents = ", ".join(sorted(agent_types)) if agent_types else "-"
        print(f"{sess_name:30s}  {sess_data['windows']}w {pane_count}p  agents: {agents}")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    config = _load_config(args)
    panes_dir = config.panes_dir
    if not panes_dir.exists():
        print("No pane logs found.", file=sys.stderr)
        return 1

    target = getattr(args, "pane", None)
    if target:
        log_file = panes_dir / f"{target}.log"
        if not log_file.exists():
            candidates = list(panes_dir.glob("*.log"))
            matches = [c for c in candidates if target in c.name]
            if len(matches) == 1:
                log_file = matches[0]
            elif len(matches) > 1:
                print(f"Ambiguous match: {[c.name for c in matches]}", file=sys.stderr)
                return 1
            else:
                print(f"No log found for '{target}'", file=sys.stderr)
                return 1
        lines = int(getattr(args, "lines", 50))
        content = log_file.read_text(encoding="utf-8", errors="replace")
        all_lines = content.splitlines()
        for line in all_lines[-lines:]:
            print(line)
        return 0

    for f in sorted(panes_dir.glob("*.log")):
        size = f.stat().st_size
        print(f"{f.name:40s}  {size:>8d} bytes")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"tmux-monitor.*start"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = result.stdout.strip().splitlines()
        if not pids:
            print("No tmux-monitor daemon found.")
            return 0
        for pid in pids:
            pid = pid.strip()
            if pid:
                subprocess.run(["kill", pid], timeout=5)
                print(f"Sent SIGTERM to pid {pid}")
        return 0
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"Error stopping daemon: {exc}", file=sys.stderr)
        return 1


def cmd_web(args: argparse.Namespace) -> int:
    import tmux_monitor.web as web_module
    web_path = Path(web_module.__file__)
    port = getattr(args, "port", 8501)
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(web_path),
         "--server.port", str(port),
         "--server.headless", "true"],
    )
    return 0


def cmd_resume_snapshot(args: argparse.Namespace) -> int:
    config = _load_config(args)
    manifest = read_resume_manifest(config)
    if manifest is None:
        print("No resume manifest found. Has the daemon ever run a heartbeat?", file=sys.stderr)
        return 1
    
    if getattr(args, "generate_script", False):
        script = generate_resume_script(manifest)
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = Path.cwd() / f"tmux-resume-{timestamp}.sh"
        out_path.write_text(script + "\n", encoding="utf-8")
        out_path.chmod(0o755)
        print(f"Resume script written to: {out_path}")
        print("Review it before running. It recreates sessions but does NOT start agents.")
        return 0
    
    text = format_snapshot_text(manifest)
    print(text)
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    config = _load_config(args)
    days = getattr(args, "days", 2)
    dry_run = not getattr(args, "approve", False)
    
    current = discover_all()
    classifications: dict[str, Any] = {}
    for sess_name, panes in current.items():
        for pane in panes:
            content = capture_pane(pane.pane_id, lines=200)
            cls = classify_pane(
                content, pane.tty,
                current_command=pane.current_command,
                pane_title=pane.title,
            )
            classifications[pane.pane_id] = cls
    
    # Load summaries from status file
    summaries: dict[str, dict[str, Any]] = {}
    data = _load_status(config)
    if data:
        for sess_data in data.get("sessions", {}).values():
            for qid, pd in sess_data.get("panes", {}).items():
                if "summary" in pd or "current_task" in pd:
                    summaries[qid] = {
                        "summary": pd.get("summary", ""),
                        "current_task": pd.get("current_task", ""),
                    }
    
    stale = find_stale_panes(
        current, classifications, config.panes_dir, days=days, summaries=summaries
    )
    
    if not stale:
        print(f"No stale panes found (threshold: {days} days).")
        return 0
    
    report = format_stale_report(stale, dry_run=dry_run)
    print(report)
    
    if not dry_run:
        results = kill_panes(stale)
        print(f"Killed {len(results['killed'])} panes.")
        if results["failed"]:
            print(f"Failed to kill {len(results['failed'])} panes:")
            for item in results["failed"]:
                print(f"  {item['pane']}: {item['error']}")
    else:
        print(f"Run with --approve to kill these {len(stale)} panes.")
    
    return 0


def cmd_launchd_install(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir).expanduser() if getattr(args, "state_dir", None) else None
    plist_path = Path(args.plist_path).expanduser() if getattr(args, "plist_path", None) else None
    path = install_launch_agent(
        python_executable=getattr(args, "python", None),
        state_dir=state_dir,
        plist_path=plist_path,
        load=not getattr(args, "no_load", False),
    )
    if getattr(args, "no_load", False):
        print(f"LaunchAgent plist written to: {path}")
    else:
        print(f"LaunchAgent installed and started: {path}")
    return 0


def cmd_launchd_uninstall(args: argparse.Namespace) -> int:
    plist_path = Path(args.plist_path).expanduser() if getattr(args, "plist_path", None) else None
    path = uninstall_launch_agent(
        plist_path=plist_path,
        unload=not getattr(args, "no_unload", False),
    )
    print(f"LaunchAgent removed: {path}")
    return 0


def cmd_launchd_status(args: argparse.Namespace) -> int:
    result = launch_agent_status()
    stream = sys.stdout if result.returncode == 0 else sys.stderr
    output = result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
    if output:
        print(output, file=stream)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tmux-monitor", description="tmux session monitoring daemon")
    p.add_argument("--state-dir", help="Override state directory")

    sub = p.add_subparsers(dest="action", required=True)

    start = sub.add_parser("start", help="Start the monitoring daemon")
    start.set_defaults(func=cmd_start)

    stop = sub.add_parser("stop", help="Stop the monitoring daemon")
    stop.set_defaults(func=cmd_stop)

    status = sub.add_parser("status", help="Show agents relevant to a repo (default: cwd)")
    status.add_argument("--cwd", help="Target directory to find relevant agents for (default: cwd)")
    status.add_argument("--repo", help="Target repo name to filter by")
    status.add_argument("--all", action="store_true", help="Include unrelated agents")
    status.add_argument("--json", action="store_true", help="JSON output")
    status.set_defaults(func=cmd_status)

    hb = sub.add_parser("heartbeat", help="Run a single heartbeat cycle")
    hb.add_argument("--json", action="store_true", help="JSON output")
    hb.set_defaults(func=cmd_heartbeat)

    sessions = sub.add_parser("sessions", help="List sessions with agent types")
    sessions.add_argument("--json", action="store_true", help="JSON output")
    sessions.set_defaults(func=cmd_sessions)

    logs = sub.add_parser("logs", help="Show pane logs")
    logs.add_argument("pane", nargs="?", help="Pane identifier to tail")
    logs.add_argument("-n", "--lines", type=int, default=50, help="Number of lines")
    logs.set_defaults(func=cmd_logs)

    web = sub.add_parser("web", help="Launch Streamlit web dashboard")
    web.add_argument("--port", type=int, default=8501, help="Port (default: 8501)")
    web.set_defaults(func=cmd_web)

    resume = sub.add_parser("resume-snapshot", help="Show last-known agent pane state for recovery")
    resume.add_argument("--generate-script", action="store_true", help="Generate a shell script to recreate tmux sessions")
    resume.set_defaults(func=cmd_resume_snapshot)

    cleanup = sub.add_parser("cleanup", help="Detect and optionally kill stale agent panes")
    cleanup.add_argument("--days", type=int, default=2, help="Idle threshold in days (default: 2)")
    cleanup.add_argument("--approve", action="store_true", help="Actually kill stale panes (default: dry-run)")
    cleanup.set_defaults(func=cmd_cleanup)

    launchd = sub.add_parser("launchd", help="Install or inspect the macOS LaunchAgent")
    launchd_sub = launchd.add_subparsers(dest="launchd_action", required=True)

    launchd_install = launchd_sub.add_parser("install", help="Install and start the LaunchAgent")
    launchd_install.add_argument("--python", help="Python executable for launchd (default: current interpreter)")
    launchd_install.add_argument("--plist-path", help="Override plist output path")
    launchd_install.add_argument("--no-load", action="store_true", help="Write plist without loading it")
    launchd_install.set_defaults(func=cmd_launchd_install)

    launchd_uninstall = launchd_sub.add_parser("uninstall", help="Unload and remove the LaunchAgent")
    launchd_uninstall.add_argument("--plist-path", help="Override plist path")
    launchd_uninstall.add_argument("--no-unload", action="store_true", help="Remove plist without calling launchctl")
    launchd_uninstall.set_defaults(func=cmd_launchd_uninstall)

    launchd_status_parser = launchd_sub.add_parser("status", help="Print launchd status for the LaunchAgent")
    launchd_status_parser.set_defaults(func=cmd_launchd_status)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
