#!/usr/bin/env python3
"""
Ableton Live Diagnostic Tool — Background Monitor Daemon

Runs persistently in the background, watching system health and
sending macOS notifications when thresholds are crossed.

Usage:
  python3 monitor.py            # run in foreground (Ctrl-C to stop)
  python3 monitor.py --quiet    # no console output, just notifications

To auto-start on login, run with --install-agent
"""

import sys
import os
import time
import subprocess
import argparse
import signal
from typing import Dict

# ── Bootstrap ──────────────────────────────────────────────────────────────────
def _bootstrap():
    missing = []
    try: import psutil  # noqa
    except ImportError: missing.append("psutil")
    try: from rich.console import Console  # noqa
    except ImportError: missing.append("rich")
    if missing:
        subprocess.run([sys.executable, "-m", "pip", "install", *missing, "-q",
                        "--disable-pip-version-check"], check=True)
_bootstrap()

import psutil
from rich.console import Console
from rich.text    import Text
from rich.panel   import Panel
from rich.live    import Live

console = Console()

# ── Config ────────────────────────────────────────────────────────────────────
THRESHOLDS: Dict[str, float] = {
    "cpu_pct":     85.0,   # % — alert if CPU exceeds this
    "ram_free_gb":  1.5,   # GB — alert if free RAM drops below this
    "swap_gb":      1.0,   # GB — alert if swap exceeds this
    "disk_free_gb": 5.0,   # GB — alert if free disk drops below this
}
POLL_INTERVAL = 30    # seconds between checks
COOLDOWN      = 300   # seconds before repeating an alert for the same issue

# ── Notification ──────────────────────────────────────────────────────────────
def notify(title: str, message: str, sound: bool = True):
    safe_t = title.replace('"', '\\"').replace("'", "\\'")
    safe_m = message.replace('"', '\\"').replace("'", "\\'")
    snd = ' sound name "default"' if sound else ""
    os.system(
        f"osascript -e 'display notification \"{safe_m}\" "
        f"with title \"{safe_t}\"{snd}' 2>/dev/null"
    )

# ── Single health check ───────────────────────────────────────────────────────
def check_health(last_alert: Dict[str, float], quiet: bool = False) -> Dict[str, float]:
    now = time.time()

    cpu  = psutil.cpu_percent(interval=3)
    mem  = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")

    free_ram  = mem.available / 1024**3
    swap_gb   = swap.used     / 1024**3
    free_disk = disk.free     / 1024**3
    abl       = any("Ableton Live" in (p.info.get("name") or "")
                    for p in psutil.process_iter(["name"]))

    alerts_fired = []

    def _alert(key: str, title: str, msg: str):
        if now - last_alert.get(key, 0) >= COOLDOWN:
            notify(title, msg)
            last_alert[key] = now
            alerts_fired.append(msg)

    if cpu > THRESHOLDS["cpu_pct"]:
        _alert("cpu", "DAW Doctor — CPU Alert",
               f"CPU at {cpu:.0f}% — raise buffer size or freeze tracks")

    if free_ram < THRESHOLDS["ram_free_gb"]:
        _alert("ram", "DAW Doctor — Low RAM",
               f"Only {free_ram:.1f} GB free — freeze tracks or close other apps")

    if swap_gb > THRESHOLDS["swap_gb"]:
        _alert("swap", "DAW Doctor — Swap Alert",
               f"Using {swap_gb:.1f} GB swap — audio dropouts likely")

    if free_disk < THRESHOLDS["disk_free_gb"]:
        _alert("disk", "DAW Doctor — Disk Space Critical",
               f"Only {free_disk:.1f} GB disk free — free space now")

    # Ableton-specific
    if abl:
        try:
            abl_proc = next(p for p in psutil.process_iter(["name", "cpu_percent"])
                            if "Ableton Live" in (p.info.get("name") or ""))
            abl_cpu = abl_proc.cpu_percent(interval=0.5)
            if abl_cpu > 85:
                _alert("abl_cpu", "DAW Doctor — Ableton CPU",
                       f"Ableton at {abl_cpu:.0f}% CPU — increase buffer or freeze tracks")
        except (StopIteration, psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if not quiet:
        ts  = time.strftime("%H:%M:%S")
        abl_status = "[green]ABLETON RUNNING[/green]" if abl else "[dim]ableton not open[/dim]"
        status = (f"  [dim]{ts}[/dim]  CPU [cyan]{cpu:.0f}%[/cyan]  "
                  f"RAM [cyan]{free_ram:.1f}GB free[/cyan]  "
                  f"DISK [cyan]{free_disk:.1f}GB[/cyan]  {abl_status}")
        if alerts_fired:
            status += f"  [red]⚠ Alert sent![/red]"
        console.print(Text.from_markup(status))

    return last_alert


# ── Install as launchd agent ──────────────────────────────────────────────────
PLIST_LABEL = "com.ableton-diagnostics.monitor"

def install_launch_agent():
    """Install monitor.py as a macOS Login Item (launchd agent)."""
    script_path = os.path.abspath(__file__)
    python_path = sys.executable
    plist_dir   = os.path.expanduser("~/Library/LaunchAgents")
    plist_path  = os.path.join(plist_dir, f"{PLIST_LABEL}.plist")

    os.makedirs(plist_dir, exist_ok=True)

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>             <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
        <string>--quiet</string>
    </array>
    <key>RunAtLoad</key>         <true/>
    <key>KeepAlive</key>         <true/>
    <key>StandardOutPath</key>   <string>/tmp/ableton-monitor.log</string>
    <key>StandardErrorPath</key> <string>/tmp/ableton-monitor-err.log</string>
</dict>
</plist>
"""
    with open(plist_path, "w") as f:
        f.write(plist_content)

    # Load it now
    subprocess.run(["launchctl", "load", plist_path], capture_output=True)

    console.print(f"\n  [green]✓ Launch Agent installed![/green]")
    console.print(f"  Monitor will start automatically at login.")
    console.print(f"  Plist: {plist_path}")
    console.print(f"  Log:   /tmp/ableton-monitor.log\n")
    console.print(f"  To remove:  launchctl unload {plist_path} && rm {plist_path}\n")


def uninstall_launch_agent():
    plist_path = os.path.expanduser(
        f"~/Library/LaunchAgents/{PLIST_LABEL}.plist")
    if os.path.exists(plist_path):
        subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
        os.remove(plist_path)
        console.print(f"\n  [yellow]✓ Launch Agent removed.[/yellow]\n")
    else:
        console.print(f"\n  [dim]No launch agent found at {plist_path}[/dim]\n")


# ── Main loop ─────────────────────────────────────────────────────────────────
def run_monitor(quiet: bool = False):
    if not quiet:
        console.print(
            "\n  [bold cyan]DAW Doctor — Background Monitor[/bold cyan]\n"
            f"  Polling every {POLL_INTERVAL}s  ·  Alerts fire when thresholds exceeded\n"
            f"  Thresholds:  CPU >{THRESHOLDS['cpu_pct']:.0f}%  ·  "
            f"RAM <{THRESHOLDS['ram_free_gb']:.1f}GB  ·  "
            f"Swap >{THRESHOLDS['swap_gb']:.1f}GB  ·  "
            f"Disk <{THRESHOLDS['disk_free_gb']:.1f}GB\n"
            "  [dim]Press Ctrl-C to stop[/dim]\n"
        )

    notify("DAW Doctor", "Background monitor started ✓")

    last_alert: Dict[str, float] = {}

    def _handle_sigterm(sig, frame):
        if not quiet:
            console.print("\n  [dim]Monitor stopped.[/dim]\n")
        sys.exit(0)
    signal.signal(signal.SIGTERM, _handle_sigterm)

    try:
        while True:
            last_alert = check_health(last_alert, quiet=quiet)
            time.sleep(POLL_INTERVAL - 3)   # 3s spent in cpu_percent above
    except KeyboardInterrupt:
        if not quiet:
            console.print("\n  [dim]Monitor stopped.[/dim]\n")


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(
        description="DAW Doctor — Background Monitor"
    )
    p.add_argument("--quiet",          action="store_true",
                   help="No console output — just send notifications")
    p.add_argument("--install-agent",  action="store_true",
                   help="Install as a macOS launchd Login Agent (auto-starts on login)")
    p.add_argument("--uninstall-agent",action="store_true",
                   help="Remove the macOS launchd Login Agent")
    p.add_argument("--cpu",            type=float,
                   help=f"CPU alert threshold %% (default: {THRESHOLDS['cpu_pct']})")
    p.add_argument("--ram",            type=float,
                   help=f"RAM free GB threshold (default: {THRESHOLDS['ram_free_gb']})")
    args = p.parse_args()

    if args.cpu:  THRESHOLDS["cpu_pct"]    = args.cpu
    if args.ram:  THRESHOLDS["ram_free_gb"] = args.ram

    if args.install_agent:
        install_launch_agent()
        return

    if args.uninstall_agent:
        uninstall_launch_agent()
        return

    run_monitor(quiet=args.quiet)


if __name__ == "__main__":
    main()
