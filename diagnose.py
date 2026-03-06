#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║          ABLETON LIVE DIAGNOSTIC TOOL   v2.0                ║
║          "OBD for your DAW"  ·  macOS Edition               ║
╚══════════════════════════════════════════════════════════════╝

Scan for latency, dropouts, CPU spikes & performance issues.
Includes: Live Monitor · Background Alerts · .als Analyzer · Report Export
"""

import os, sys, time, glob, json, threading, subprocess, xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional

# ── Auto-install dependencies ──────────────────────────────────────────────────
def _bootstrap():
    missing = []
    try:    import psutil             # noqa
    except ImportError: missing.append("psutil")
    try:    from rich.console import Console  # noqa
    except ImportError: missing.append("rich")
    if missing:
        print(f"\n  Installing: {', '.join(missing)} …\n")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", *missing, "-q",
             "--disable-pip-version-check"], check=True
        )
_bootstrap()

import psutil
from rich.console import Console
from rich.panel    import Panel
from rich.table    import Table
from rich.live     import Live
from rich.text     import Text
from rich.prompt   import Prompt
from rich          import box
from rich.rule     import Rule
from rich.align    import Align
from rich.columns  import Columns

console = Console()

# ── Severity constants: (label, color, icon, rank) ────────────────────────────
SEV_OK   = ("OK",   "green",    "✓", 0)
SEV_INFO = ("INFO", "cyan",     "ℹ", 1)
SEV_WARN = ("WARN", "yellow",   "⚠", 2)
SEV_CRIT = ("CRIT", "bold red", "✖", 3)

@dataclass
class Code:
    code:     str
    sev:      tuple        # one of SEV_* constants
    title:    str
    cause:    str
    fix:      str
    value:    str = ""
    fix_cmd:  str = ""     # shell command the user can run to fix this

    @property
    def rank(self):  return self.sev[3]
    @property
    def color(self): return self.sev[1]
    @property
    def icon(self):  return self.sev[2]
    @property
    def label(self): return self.sev[0]

# ── Shell helper ───────────────────────────────────────────────────────────────
def sh(cmd: str, timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""

# ── macOS notification ─────────────────────────────────────────────────────────
def notify(title: str, message: str):
    safe_t = title.replace('"', '\\"')
    safe_m = message.replace('"', '\\"')
    os.system(
        f'osascript -e \'display notification "{safe_m}" with title "{safe_t}" '
        f'sound name "default"\' 2>/dev/null'
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  DIAGNOSTIC CHECK FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def check_ableton() -> List[Code]:
    out = []
    all_procs = list(psutil.process_iter(["name", "pid", "cpu_percent", "memory_info"]))
    abl = next((p for p in all_procs if "Ableton Live" in (p.info.get("name") or "")), None)

    if abl is None:
        out.append(Code("AB-ABL-001", SEV_INFO,
            "Ableton Live Not Running",
            "Ableton Live process not found",
            "Launch Ableton Live for full process diagnostics",
            "NOT RUNNING"))
    else:
        try:
            cpu = abl.cpu_percent(interval=0.3)
            mb  = abl.memory_info().rss / 1024**2
            out.append(Code("AB-ABL-000", SEV_OK,
                "Ableton Live Detected",
                f"PID {abl.pid}  ·  CPU: {cpu:.1f}%  ·  RAM: {mb:.0f} MB",
                "", f"{cpu:.0f}% CPU"))

            if cpu > 85:
                out.append(Code("AB-ABL-002", SEV_CRIT,
                    "Ableton: Critical CPU Usage",
                    f"Ableton alone at {cpu:.1f}% — expect dropouts",
                    "Increase buffer size · Freeze heavy tracks · Disable unused plugins",
                    f"{cpu:.0f}%"))
            elif cpu > 65:
                out.append(Code("AB-ABL-002", SEV_WARN,
                    "Ableton: High CPU Usage",
                    f"Ableton using {cpu:.1f}% — getting tight",
                    "Consider freezing tracks or bumping buffer size",
                    f"{cpu:.0f}%"))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # ── Read Ableton Preferences.cfg ──────────────────────────────────────────
    pref_globs = glob.glob(os.path.expanduser(
        "~/Library/Preferences/Ableton/Live */Preferences.cfg"))
    if pref_globs:
        pref_path = sorted(pref_globs)[-1]
        try:
            tree = ET.parse(pref_path)
            root = tree.getroot()

            def xval(tag_name: str) -> Optional[str]:
                for el in root.iter():
                    if el.tag == tag_name:
                        return el.get("Value")
                return None

            buf = xval("BufferSize")
            sr  = xval("SampleRate")

            if buf:
                buf_int = int(float(buf))
                if buf_int <= 64:
                    out.append(Code("AB-ABL-003", SEV_WARN,
                        "Buffer Size Very Low",
                        f"Set to {buf_int} samples — stresses CPU, causes glitches",
                        "Increase to 128–256 while producing. Only use ≤64 for live recording.",
                        f"{buf_int} samples"))
                elif buf_int >= 1024:
                    out.append(Code("AB-ABL-003", SEV_INFO,
                        "Buffer Size Large (High Latency)",
                        f"Set to {buf_int} samples — fine for mixing, high monitor latency",
                        "Reduce to 128–256 when recording live instruments.",
                        f"{buf_int} samples"))
                else:
                    out.append(Code("AB-ABL-003", SEV_OK,
                        "Buffer Size OK",
                        f"Set to {buf_int} samples — balanced for production",
                        "", f"{buf_int} samples"))

            if sr:
                sr_int = int(float(sr))
                if sr_int <= 48000:
                    out.append(Code("AB-ABL-004", SEV_OK,
                        f"Sample Rate: {sr_int:,} Hz",
                        "Standard rate — minimal CPU overhead",
                        "", f"{sr_int:,} Hz"))
                else:
                    out.append(Code("AB-ABL-004", SEV_WARN,
                        f"Sample Rate High: {sr_int:,} Hz",
                        "High sample rates multiply CPU load significantly",
                        "Use 44.1 kHz for music unless you need 96k for a specific reason",
                        f"{sr_int:,} Hz"))
        except Exception:
            pass

    return out


def check_cpu() -> List[Code]:
    out = []
    cpu_pct = psutil.cpu_percent(interval=0.8)
    cores   = psutil.cpu_percent(percpu=True)
    maxed   = sum(1 for c in cores if c > 90)

    if cpu_pct >= 90:
        out.append(Code("AB-CPU-001", SEV_CRIT,
            "CPU Overloaded",
            f"System at {cpu_pct:.0f}%  ·  {maxed}/{len(cores)} cores above 90%",
            "Increase buffer to 1024+ · Freeze ALL tracks · Kill all other apps NOW",
            f"{cpu_pct:.0f}%"))
    elif cpu_pct >= 72:
        out.append(Code("AB-CPU-001", SEV_WARN,
            "High CPU Load",
            f"System at {cpu_pct:.0f}%  ·  {maxed}/{len(cores)} cores above 90%",
            "Freeze instrument tracks · Increase buffer size · Close browser/Slack",
            f"{cpu_pct:.0f}%"))
    else:
        out.append(Code("AB-CPU-001", SEV_OK,
            "CPU Load Normal",
            f"System at {cpu_pct:.0f}%",
            "", f"{cpu_pct:.0f}%"))

    # Background CPU hogs
    SKIP = {"kernel_task", "WindowServer", "Ableton Live", "python3", "diagnose.py",
            "coreaudiod", "launchd", "logd", "mds"}
    hogs = []
    for p in psutil.process_iter(["name", "cpu_percent"]):
        try:
            pct  = p.cpu_percent(interval=None)
            name = (p.info.get("name") or "").strip()
            if pct and pct > 12 and name and name not in SKIP:
                hogs.append((name, pct))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if hogs:
        hogs.sort(key=lambda x: x[1], reverse=True)
        name, pct = hogs[0]
        out.append(Code("AB-CPU-003",
            SEV_CRIT if pct > 40 else SEV_WARN,
            "Background App Eating CPU",
            f"'{name}' is using {pct:.0f}% CPU",
            f"Quit '{name}' before your session for maximum headroom",
            f"{name} @ {pct:.0f}%",
            fix_cmd=f'killall "{name}" 2>/dev/null || pkill -f "{name}"'))

    # Thermal throttling (macOS pmset)
    therm = sh("pmset -g therm 2>/dev/null | grep CPU_Scheduler_Limit | awk '{print $NF}'")
    if therm and therm.isdigit() and int(therm) < 100:
        out.append(Code("AB-CPU-002", SEV_CRIT,
            "CPU Thermal Throttling!",
            f"macOS capped CPU speed to {therm}% due to heat",
            "Let Mac cool down · Use a cooling stand · Check thermal paste on older Macs",
            f"THROTTLED {therm}%"))

    return out


def check_memory() -> List[Code]:
    out = []
    mem  = psutil.virtual_memory()
    swap = psutil.swap_memory()
    free  = mem.available / 1024**3
    total = mem.total     / 1024**3

    if free < 1.0:
        out.append(Code("AB-MEM-001", SEV_CRIT,
            "Critical Low RAM",
            f"Only {free:.2f} GB free of {total:.0f} GB — expect crashes & dropouts",
            "Freeze ALL tracks · Close every non-essential app · Bounce tracks to audio",
            f"{free:.2f} GB free"))
    elif free < 2.5:
        out.append(Code("AB-MEM-001", SEV_WARN,
            "Low Available RAM",
            f"{free:.1f} GB free of {total:.0f} GB  ({mem.percent:.0f}% used)",
            "Freeze sample-heavy instruments · Close Chrome, Slack, Zoom",
            f"{free:.1f} GB free"))
    else:
        out.append(Code("AB-MEM-001", SEV_OK,
            "RAM OK",
            f"{free:.1f} GB free of {total:.0f} GB  ({mem.percent:.0f}% used)",
            "", f"{free:.1f} GB free"))

    sw_gb = swap.used / 1024**3
    if sw_gb > 1.0:
        out.append(Code("AB-MEM-002", SEV_CRIT,
            "Heavy Swap = Audio Dropouts",
            f"Swapping {sw_gb:.1f} GB to disk — disk latency kills audio timing",
            "Close all non-essential apps NOW · Freeze & bounce tracks",
            f"{sw_gb:.1f} GB swap"))
    elif sw_gb > 0.2:
        out.append(Code("AB-MEM-002", SEV_WARN,
            "Swap Activity Detected",
            f"Using {sw_gb:.2f} GB swap — RAM is tight",
            "Close browser tabs and unused background apps",
            f"{sw_gb:.2f} GB swap"))

    return out


def check_audio() -> List[Code]:
    out = []
    IFACE_KW = [
        "focusrite", "scarlett", "apollo", "universal audio", "ua ", "motu",
        "rme", "babyface", "fireface", "audient", "steinberg", "presonus",
        "behringer", "zoom h", "ssl", "neve", "evo ", "volt ", "clarett",
        "quantum", "arrow", "twin", "duet", "quartet", "octet", "saffire",
        "tascam", "roland ", "yamaha ag", "id4", "id14", "id22", "id44",
        "mackie", "solid state", "antelope", "lynx", "prism", "apogee",
    ]

    audio_json = sh("system_profiler SPAudioDataType -json", timeout=14)
    devices: List[str] = []
    iface_found: Optional[str] = None

    try:
        data = json.loads(audio_json)
        for section in data.get("SPAudioDataType", []):
            for item in section.get("_items", []):
                name = item.get("_name", "")
                devices.append(name)
                if iface_found is None and any(kw in name.lower() for kw in IFACE_KW):
                    iface_found = name
    except Exception:
        pass

    if iface_found:
        out.append(Code("AB-AUD-001", SEV_OK,
            "External Audio Interface Found",
            f"Detected: {iface_found}",
            "", iface_found[:28]))
    elif devices:
        out.append(Code("AB-AUD-001", SEV_WARN,
            "No External Audio Interface",
            "Using built-in Mac audio — high latency, no headroom",
            "Connect an interface (Focusrite Scarlett, Apollo Solo, Audient EVO, etc.)",
            "Built-in Audio"))
    else:
        out.append(Code("AB-AUD-001", SEV_INFO,
            "Could Not Query Audio Devices",
            "system_profiler returned no data",
            "Check System Settings → Sound",
            "Unknown"))

    # CoreAudio daemon
    ca_ok = any(
        p.info.get("name") == "coreaudiod"
        for p in psutil.process_iter(["name"])
    )
    if not ca_ok:
        out.append(Code("AB-AUD-002", SEV_CRIT,
            "CoreAudio Daemon is DOWN",
            "coreaudiod is not running — audio system is broken",
            "Restart your Mac to restore CoreAudio",
            "CRASHED"))
    else:
        out.append(Code("AB-AUD-002", SEV_OK,
            "CoreAudio Running",
            "coreaudiod is active and healthy",
            "", "OK"))

    return out


def check_system() -> List[Code]:
    out = []

    # Time Machine
    tm = sh("tmutil status 2>/dev/null")
    if '"Running" = 1' in tm or '"Stopping" = 1' in tm:
        out.append(Code("AB-SYS-001", SEV_WARN,
            "Time Machine Backup Running",
            "Actively writing to disk — causes I/O spikes & CPU competition",
            "Pause Time Machine: System Settings → General → Time Machine → Pause",
            "BACKING UP",
            fix_cmd="tmutil pauseautomaticbackup"))
    else:
        out.append(Code("AB-SYS-001", SEV_OK,
            "Time Machine Idle",
            "No backup in progress", "", "IDLE"))

    # Spotlight indexing
    sp_procs = ["mdworker", "mds_stores", "mds "]
    if any(
        any(sp in (p.info.get("name") or "") for sp in sp_procs)
        for p in psutil.process_iter(["name"])
    ):
        out.append(Code("AB-SYS-002", SEV_WARN,
            "Spotlight Indexing Active",
            "mdworker is consuming CPU & I/O while indexing files",
            "Wait for it, or add Library to Spotlight Privacy exclusions.",
            "INDEXING",
            fix_cmd="sudo mdutil -a -i off  # Re-enable later: sudo mdutil -a -i on"))

    # Low Power Mode
    lpm = sh("pmset -g 2>/dev/null | grep lowpowermode")
    if lpm.split() and lpm.split()[-1] == "1":
        out.append(Code("AB-SYS-003", SEV_CRIT,
            "Low Power Mode ENABLED",
            "macOS throttles CPU & memory bandwidth to save battery",
            "System Settings → Battery → uncheck Low Power Mode",
            "ON ⚠",
            fix_cmd="sudo pmset -a lowpowermode 0"))

    # Battery / AC power
    try:
        batt = psutil.sensors_battery()
        if batt is not None:
            if not batt.power_plugged:
                sev = SEV_CRIT if batt.percent < 15 else SEV_WARN
                out.append(Code("AB-SYS-004", sev,
                    "Running on Battery (Not Plugged In)",
                    f"macOS throttles CPU on battery  ·  {batt.percent:.0f}% remaining",
                    "Plug in your power adapter for maximum performance",
                    f"BAT {batt.percent:.0f}%"))
            else:
                out.append(Code("AB-SYS-004", SEV_OK,
                    "AC Power (Plugged In)",
                    "Mac is running on AC — full CPU boost available",
                    "", "AC POWER"))
    except Exception:
        pass

    # Bluetooth
    bt_state = sh("defaults read /Library/Preferences/com.apple.Bluetooth ControllerPowerState 2>/dev/null")
    if bt_state == "1":
        bt_audio = sh(
            "system_profiler SPBluetoothDataType 2>/dev/null | grep -i 'connected: yes' | head -5"
        )
        if bt_audio:
            out.append(Code("AB-NET-001", SEV_WARN,
                "Bluetooth Audio Device Connected",
                "BT audio adds latency and can cause dropouts",
                "Use wired headphones/monitors during recording & mixing",
                "BT AUDIO ON",
                fix_cmd="blueutil --power 0  # (install: brew install blueutil)"))
        else:
            out.append(Code("AB-NET-001", SEV_INFO,
                "Bluetooth Enabled (no audio device)",
                "BT is on but no audio device connected — low risk",
                "Disable BT if you experience dropouts",
                "BT ON"))

    # Disk space
    disk  = psutil.disk_usage("/")
    free  = disk.free  / 1024**3
    total = disk.total / 1024**3

    if free < 5:
        out.append(Code("AB-DSK-001", SEV_CRIT,
            "Critically Low Disk Space",
            f"Only {free:.1f} GB free of {total:.0f} GB — OS needs room for virtual memory",
            "Delete large files, empty trash, run Disk Diag or CleanMyMac",
            f"{free:.1f} GB free"))
    elif free < 20:
        out.append(Code("AB-DSK-001", SEV_WARN,
            "Low Disk Space",
            f"{free:.1f} GB free of {total:.0f} GB — sample streaming may stutter",
            "Free up at least 20 GB for comfortable audio work",
            f"{free:.1f} GB free"))
    else:
        out.append(Code("AB-DSK-001", SEV_OK,
            "Disk Space OK",
            f"{free:.1f} GB free of {total:.0f} GB",
            "", f"{free:.1f} GB"))

    # Disk I/O burst
    try:
        io1 = psutil.disk_io_counters()
        time.sleep(0.4)
        io2 = psutil.disk_io_counters()
        if io1 and io2:
            r_mbs = (io2.read_bytes  - io1.read_bytes)  / 0.4 / 1024**2
            w_mbs = (io2.write_bytes - io1.write_bytes) / 0.4 / 1024**2
            tot   = r_mbs + w_mbs
            if tot > 300:
                out.append(Code("AB-DSK-002", SEV_WARN,
                    "Heavy Disk Activity",
                    f"R: {r_mbs:.0f} MB/s  ·  W: {w_mbs:.0f} MB/s — competes with sample streaming",
                    "Check if Time Machine, Spotlight, or large file copies are running",
                    f"{tot:.0f} MB/s"))
    except Exception:
        pass

    return out


def run_scan(live_ref: Optional[Live] = None) -> List[Code]:
    steps = [
        ("Ableton Live",       check_ableton),
        ("CPU",                check_cpu),
        ("Memory / RAM",       check_memory),
        ("Audio / CoreAudio",  check_audio),
        ("System & Disk",      check_system),
    ]
    all_codes: List[Code] = []
    for name, fn in steps:
        if live_ref:
            live_ref.update(Panel(
                Text(f"\n  Scanning: {name} …\n", style="dim cyan"),
                title="[bold cyan]⚡ SCANNING[/bold cyan]",
                border_style="cyan"))
        all_codes.extend(fn())
    return sorted(all_codes, key=lambda c: -c.rank)


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKGROUND MONITOR
# ═══════════════════════════════════════════════════════════════════════════════

_monitor_stop  = threading.Event()
_monitor_thread: Optional[threading.Thread] = None

ALERT_THRESHOLDS = {
    "cpu_pct":    85.0,   # % system CPU
    "ram_free_gb": 1.5,   # GB free RAM
    "swap_gb":     1.0,   # GB swap used
    "disk_free_gb": 5.0,  # GB free disk
}
ALERT_COOLDOWN = 300  # seconds between repeat alerts for same issue

def _monitor_loop():
    last_alert: dict = {}
    while not _monitor_stop.is_set():
        now = time.time()
        cpu  = psutil.cpu_percent(interval=5)
        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage("/")

        def _alert(key: str, title: str, msg: str):
            if now - last_alert.get(key, 0) >= ALERT_COOLDOWN:
                notify(title, msg)
                last_alert[key] = now

        if cpu > ALERT_THRESHOLDS["cpu_pct"]:
            _alert("cpu", "Ableton Diagnostics — CPU Alert",
                   f"CPU at {cpu:.0f}% — consider freezing tracks or raising buffer size")

        free_gb = mem.available / 1024**3
        if free_gb < ALERT_THRESHOLDS["ram_free_gb"]:
            _alert("ram", "Ableton Diagnostics — Low RAM",
                   f"Only {free_gb:.1f} GB RAM free — freeze tracks or close other apps")

        sw_gb = swap.used / 1024**3
        if sw_gb > ALERT_THRESHOLDS["swap_gb"]:
            _alert("swap", "Ableton Diagnostics — Swap Alert",
                   f"Using {sw_gb:.1f} GB swap — audio dropouts likely")

        disk_free = disk.free / 1024**3
        if disk_free < ALERT_THRESHOLDS["disk_free_gb"]:
            _alert("disk", "Ableton Diagnostics — Disk Space Critical",
                   f"Only {disk_free:.1f} GB disk free — free space NOW")

        # Check every 30 seconds (5 seconds already spent in cpu_percent)
        _monitor_stop.wait(25)

def monitor_is_running() -> bool:
    return _monitor_thread is not None and _monitor_thread.is_alive()

def start_monitor():
    global _monitor_thread
    _monitor_stop.clear()
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True, name="ABL-Monitor")
    _monitor_thread.start()

def stop_monitor():
    _monitor_stop.set()


# ═══════════════════════════════════════════════════════════════════════════════
#  REPORT EXPORT
# ═══════════════════════════════════════════════════════════════════════════════

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

def export_report(codes: List[Code]) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    ts   = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(REPORTS_DIR, f"scan_{ts}.txt")

    macos_ver = sh("sw_vers -productVersion")
    model     = sh("sysctl -n hw.model")
    cpu_info  = sh("sysctl -n machdep.cpu.brand_string")
    mem_total = psutil.virtual_memory().total // 1024**3

    with open(path, "w") as f:
        f.write("═" * 65 + "\n")
        f.write("  ABLETON LIVE DIAGNOSTIC REPORT\n")
        f.write(f"  Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("═" * 65 + "\n\n")
        f.write(f"  macOS     : {macos_ver}\n")
        f.write(f"  Model     : {model}\n")
        f.write(f"  CPU       : {cpu_info}\n")
        f.write(f"  RAM       : {mem_total} GB\n\n")

        crits = [c for c in codes if c.sev == SEV_CRIT]
        warns = [c for c in codes if c.sev == SEV_WARN]
        f.write(f"  Summary: {len(crits)} critical · {len(warns)} warnings · "
                f"{len(codes) - len(crits) - len(warns)} OK\n\n")

        f.write("─" * 65 + "\n")
        f.write("  DIAGNOSTIC CODES\n")
        f.write("─" * 65 + "\n\n")

        for c in codes:
            f.write(f"  [{c.label:8s}] {c.code}  —  {c.title}\n")
            if c.cause:   f.write(f"             Cause   : {c.cause}\n")
            if c.value:   f.write(f"             Value   : {c.value}\n")
            if c.fix:     f.write(f"             Fix     : {c.fix}\n")
            if c.fix_cmd: f.write(f"             Command : {c.fix_cmd}\n")
            f.write("\n")

        f.write("─" * 65 + "\n")
        f.write("  Generated by DAW Doctor v2.0\n")
        f.write("  github.com/your-handle/ableton-diagnostics\n")

    return path


# ═══════════════════════════════════════════════════════════════════════════════
#  UI COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════

HEADER = """\
  ╔══════════════════════════════════════════════════════════════════╗
  ║   ⚕   DAW DOCTOR  v2.0  ·  macOS Audio Diagnostic Suite   ⚕   ║
  ║              "OBD for your DAW"  —  Performance & Health Scanner  ║
  ╚══════════════════════════════════════════════════════════════════╝\
"""

TIPS = [
    ("Buffer Size",       "256 while writing · 512–1024 while mixing · 64 only for live recording"),
    ("Sample Rate",       "44.1 kHz for music · 48 kHz only for video scoring — high rates = more CPU"),
    ("Freeze Tracks",     "Right-click instrument track → Freeze  to free CPU instantly"),
    ("Flatten Tracks",    "Freeze → then Flatten to convert permanently and free plugin RAM"),
    ("Wi-Fi",             "Turn off Wi-Fi during critical recording — it causes latency spikes"),
    ("Bluetooth",         "BT headphones can cause audio dropouts — use wired monitors in sessions"),
    ("USB Direct",        "Plug audio interface directly into Mac, NOT through a USB hub"),
    ("AC Power",          "Always plug in — battery mode throttles CPU significantly"),
    ("Low Power Mode",    "Disable Low Power Mode: System Settings → Battery, before every session"),
    ("Time Machine",      "Pause Time Machine before recording: System Settings → Time Machine"),
    ("Spotlight",         "Add Ableton Library to Spotlight Privacy exclusions to stop re-indexing"),
    ("Display Sleep",     "Set display sleep to 'Never' while recording to prevent audio glitches"),
    ("Plugin Count",      "Every active VST/AU costs CPU — right-click → disable unused ones"),
    ("Bounce Returns",    "Heavy reverbs/delays on return tracks: freeze the return track"),
    ("Frame Rate",        "Ableton Prefs → Display → reduce Frame Rate to 'Medium' to save GPU/CPU"),
    ("Thermal Throttle",  "Old MacBooks throttle badly when hot — use cooling stand & clean vents"),
    ("Monitor Latency",   "Ableton Pref → Audio: try disabling 'Reduced Latency When Monitoring'"),
    ("Plugin Scanning",   "Disable auto plugin scan in Prefs — rescan only after new installs"),
    ("Disk Streaming",    "Long samples need a fast drive (NVMe) — HDDs struggle with streaming"),
    ("Record Arming",     "Unarmed tracks still cost CPU — unarm all tracks when not recording"),
]


def bar(pct: float, w: int = 22) -> Text:
    filled = round(w * max(0.0, min(pct, 100.0)) / 100)
    color  = "green" if pct < 60 else ("yellow" if pct < 82 else "red")
    t = Text()
    t.append("█" * filled,       style=color)
    t.append("░" * (w - filled), style="dim")
    return t


def live_panel() -> Panel:
    cpu  = psutil.cpu_percent(interval=0.4)
    mem  = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    swap = psutil.swap_memory()
    abl  = any(
        "Ableton Live" in (p.info.get("name") or "")
        for p in psutil.process_iter(["name"])
    )
    disk_pct = disk.used / disk.total * 100

    t = Text()
    t.append("  CPU   ", style="bold white")
    t.append_text(bar(cpu))
    t.append(f"  {cpu:5.1f}%\n")

    t.append("  RAM   ", style="bold white")
    t.append_text(bar(mem.percent))
    t.append(f"  {mem.percent:5.1f}%  [{mem.available/1024**3:.1f} GB free]\n")

    t.append("  DISK  ", style="bold white")
    t.append_text(bar(disk_pct))
    t.append(f"  {disk_pct:5.1f}%  [{disk.free/1024**3:.1f} GB free]\n")

    if swap.used > 50 * 1024**2:
        t.append("  SWAP  ", style="bold white")
        t.append_text(bar(swap.percent))
        t.append(f"  {swap.used/1024**2:.0f} MB in use\n")

    t.append("\n  Ableton: ")
    if abl:
        t.append("● RUNNING", style="bold green")
    else:
        t.append("○ not detected", style="dim yellow")

    mon_status = "  ·  [green]BG Monitor: ON[/green]" if monitor_is_running() \
                 else "  ·  [dim]BG Monitor: off[/dim]"
    t.append(mon_status + f"   {time.strftime('%H:%M:%S')}", style="")

    return Panel(t,
        title="[bold cyan]⚡ LIVE MONITOR[/bold cyan]",
        border_style="cyan", padding=(0, 1))


def codes_table(codes: List[Code]) -> Table:
    tbl = Table(
        box=box.ROUNDED,
        border_style="dim white",
        show_header=True,
        header_style="bold dim white",
        expand=True,
        padding=(0, 1),
    )
    tbl.add_column("Code",    width=14, style="dim cyan",  no_wrap=True)
    tbl.add_column("Status",  width=10, justify="center",  no_wrap=True)
    tbl.add_column("Finding  /  Cause  /  Fix")
    tbl.add_column("Value",   width=18, justify="right",   style="dim")

    for c in codes:
        status  = Text(f"{c.icon} {c.label}", style=c.color)
        detail  = Text()
        title_style = f"bold {c.color}" if c.rank >= 2 else "bold white"
        detail.append(c.title + "\n", style=title_style)
        if c.cause:   detail.append(f" Cause  {c.cause}\n",    style="dim white")
        if c.fix:     detail.append(f" Fix    {c.fix}\n",      style="italic cyan")
        if c.fix_cmd: detail.append(f" Cmd    {c.fix_cmd}",    style="bold dim yellow")
        tbl.add_row(c.code, status, detail, c.value)

    return tbl


def fix_commands_panel(codes: List[Code]) -> Optional[Panel]:
    """Show a focused panel of runnable shell commands."""
    fixable = [c for c in codes if c.fix_cmd and c.rank >= 2]
    if not fixable:
        return None

    t = Text()
    t.append("\n  Copy & paste these commands to quickly address issues:\n\n", style="dim")
    for c in fixable:
        t.append(f"  # {c.title}\n", style="dim white")
        t.append(f"  {c.fix_cmd}\n\n", style="bold yellow")

    return Panel(t,
        title="[bold yellow]⚡ QUICK FIX COMMANDS[/bold yellow]",
        border_style="yellow", padding=(0, 1))


# ═══════════════════════════════════════════════════════════════════════════════
#  MODES
# ═══════════════════════════════════════════════════════════════════════════════

def mode_scan():
    console.clear()
    console.print(Text(HEADER, style="bold cyan"))
    console.print()
    codes: List[Code] = []
    with Live(console=console, refresh_per_second=4, transient=True) as live:
        codes = run_scan(live)

    console.print(codes_table(codes))
    console.print()

    # Quick Fix Commands panel
    fix_panel = fix_commands_panel(codes)
    if fix_panel:
        console.print(fix_panel)
        console.print()

    crits = sum(1 for c in codes if c.sev == SEV_CRIT)
    warns = sum(1 for c in codes if c.sev == SEV_WARN)
    oks   = sum(1 for c in codes if c.sev == SEV_OK)

    console.print(f"  Results:  [bold red]{crits} critical[/]  ·  "
                  f"[yellow]{warns} warnings[/]  ·  [green]{oks} OK[/]\n")

    if crits:
        console.rule(f"[bold red] ✖  {crits} CRITICAL issue(s) — fix these first [/]", style="red")
    elif warns:
        console.rule(f"[yellow] ⚠  {warns} warning(s) — review above [/]", style="yellow")
    else:
        console.rule("[green] ✓  All clear — no critical issues detected [/]", style="green")

    console.print()

    # Offer export
    try:
        export = input("  Export report to file? [y/N]: ").strip().lower()
        if export == "y":
            path = export_report(codes)
            console.print(f"\n  [green]✓ Report saved:[/green]  {path}\n")
    except (KeyboardInterrupt, EOFError):
        pass


def mode_monitor():
    console.clear()
    console.print(Text(HEADER, style="bold cyan"))
    console.print(Align.center(Text("  Press  Ctrl-C  to return to menu\n", style="dim")))
    try:
        with Live(live_panel(), console=console, refresh_per_second=2) as live:
            while True:
                time.sleep(0.5)
                live.update(live_panel())
    except KeyboardInterrupt:
        pass


def mode_tips():
    console.clear()
    console.print(Text(HEADER, style="bold cyan"))
    console.rule("[bold cyan] ABLETON PERFORMANCE TIPS [/]", style="cyan")
    console.print()

    tbl = Table(box=box.SIMPLE, show_header=False, expand=True,
                padding=(0, 1), border_style="dim")
    tbl.add_column("", width=22, style="bold cyan", no_wrap=True)
    tbl.add_column("", style="white")
    for tip, desc in TIPS:
        tbl.add_row(f"▸ {tip}", desc)

    console.print(tbl)
    console.print()
    console.print(Align.center(Text("Press Enter to return to menu", style="dim")))
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass


def mode_als():
    """Launch the .als project file analyzer."""
    als_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "als_analyzer.py")
    if not os.path.exists(als_script):
        console.print("\n  [red]als_analyzer.py not found.[/red]  Put it in the same folder.\n")
        try: input("  Press Enter to continue…")
        except: pass
        return

    console.clear()
    console.print(Text(HEADER, style="bold cyan"))
    console.rule("[bold cyan] .ALS PROJECT FILE ANALYZER [/]", style="cyan")
    console.print()
    console.print("  [dim]Drag an .als file here, or type the full path:[/dim]")
    try:
        raw = input("  Path: ").strip().strip("'\"")
    except (KeyboardInterrupt, EOFError):
        return

    if not raw:
        return

    if not os.path.exists(raw):
        console.print(f"\n  [red]File not found:[/red] {raw}\n")
        try: input("  Press Enter to continue…")
        except: pass
        return

    result = subprocess.run(
        [sys.executable, als_script, raw],
        capture_output=False   # let it print directly
    )
    try: input("\n  Press Enter to return to menu…")
    except: pass


def mode_background_monitor():
    """Toggle the background system monitor."""
    console.clear()
    console.print(Text(HEADER, style="bold cyan"))
    console.rule("[bold cyan] BACKGROUND MONITOR [/]", style="cyan")
    console.print()

    if monitor_is_running():
        console.print("  [green]● Background monitor is currently RUNNING[/green]\n")
        console.print("  It checks every 30 seconds and sends macOS notifications when:\n")
        console.print(f"    · CPU  > {ALERT_THRESHOLDS['cpu_pct']:.0f}%")
        console.print(f"    · RAM free < {ALERT_THRESHOLDS['ram_free_gb']:.1f} GB")
        console.print(f"    · Swap > {ALERT_THRESHOLDS['swap_gb']:.1f} GB")
        console.print(f"    · Disk free < {ALERT_THRESHOLDS['disk_free_gb']:.1f} GB")
        console.print()
        try:
            choice = input("  [S]top monitor  or  Enter to go back: ").strip().lower()
            if choice == "s":
                stop_monitor()
                console.print("\n  [yellow]Monitor stopped.[/yellow]\n")
                time.sleep(1)
        except (KeyboardInterrupt, EOFError):
            pass
    else:
        console.print("  [dim]○ Background monitor is not running[/dim]\n")
        console.print("  When running, it checks system health every 30 seconds\n"
                      "  and sends macOS notifications when thresholds are crossed:\n")
        console.print(f"    · CPU  > {ALERT_THRESHOLDS['cpu_pct']:.0f}%")
        console.print(f"    · RAM free < {ALERT_THRESHOLDS['ram_free_gb']:.1f} GB")
        console.print(f"    · Swap > {ALERT_THRESHOLDS['swap_gb']:.1f} GB")
        console.print(f"    · Disk free < {ALERT_THRESHOLDS['disk_free_gb']:.1f} GB")
        console.print()
        console.print("  [dim]The monitor runs in the background while this app is open.[/dim]")
        console.print("  [dim]For a persistent daemon, run:  python3 monitor.py[/dim]")
        console.print()
        try:
            choice = input("  [S]tart monitor  or  Enter to go back: ").strip().lower()
            if choice == "s":
                start_monitor()
                console.print("\n  [green]✓ Background monitor started![/green]")
                console.print("  [dim]macOS notifications will fire when thresholds are crossed.[/dim]\n")
                time.sleep(1.5)
        except (KeyboardInterrupt, EOFError):
            pass


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN MENU
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    while True:
        console.clear()
        console.print(Text(HEADER, style="bold cyan"))
        console.print()

        # Quick status strip
        cpu  = psutil.cpu_percent(interval=0.3)
        mem  = psutil.virtual_memory()
        abl  = any(
            "Ableton Live" in (p.info.get("name") or "")
            for p in psutil.process_iter(["name"])
        )

        status = Text("  ")
        status.append("CPU ", style="dim white")
        status.append_text(bar(cpu, 12))
        status.append(f" {cpu:.0f}%   ")
        status.append("RAM ", style="dim white")
        status.append_text(bar(mem.percent, 12))
        status.append(f" {mem.percent:.0f}%   ")
        status.append("Ableton: ")
        if abl:
            status.append("● RUNNING", style="bold green")
        else:
            status.append("○ not open", style="dim yellow")
        if monitor_is_running():
            status.append("   [green]BG MONITOR ON[/green]")
        console.print(Align.center(status))
        console.print()

        console.print("  [bold cyan][1][/bold cyan]  Run Full Diagnostic Scan")
        console.print("  [bold cyan][2][/bold cyan]  Live System Monitor")
        console.print("  [bold cyan][3][/bold cyan]  Analyze .als Project File")
        console.print("  [bold cyan][4][/bold cyan]  Background Monitor (macOS Alerts)")
        console.print("  [bold cyan][5][/bold cyan]  Optimization Tips")
        console.print("  [bold cyan][Q][/bold cyan]  Quit")
        console.print()

        try:
            choice = input("  Select: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            break

        if choice == "1":
            mode_scan()
            try: input("  Press Enter to return to menu…")
            except: pass
        elif choice == "2":
            mode_monitor()
        elif choice == "3":
            mode_als()
        elif choice == "4":
            mode_background_monitor()
        elif choice == "5":
            mode_tips()
        elif choice in ("q", "quit", "exit"):
            break

    if monitor_is_running():
        stop_monitor()

    console.print("\n  [dim]DAW Doctor out. Keep the bass up. ⚕[/dim]\n")


if __name__ == "__main__":
    main()
