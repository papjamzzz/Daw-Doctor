#!/usr/bin/env python3
"""
Ableton Live .als Project File Analyzer

Parses a gzip-compressed .als file and reports:
  · Track count and types (MIDI, Audio, Return, Master)
  · Instrument and effect chains per track
  · External plugins (VST/VST3/AU)
  · Frozen tracks
  · Sample file references
  · Tempo, time signature
  · Estimated CPU complexity score

Usage:
  python3 als_analyzer.py /path/to/project.als
  (or drag a .als file onto this script)
"""

import sys
import os
import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Dict

# ── Bootstrap ──────────────────────────────────────────────────────────────────
import subprocess
def _bootstrap():
    try: from rich.console import Console  # noqa
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "rich", "-q",
                        "--disable-pip-version-check"], check=True)
_bootstrap()

from rich.console import Console
from rich.panel   import Panel
from rich.table   import Table
from rich.text    import Text
from rich.rule    import Rule
from rich.align   import Align
from rich         import box

console = Console()

# ── Known device tags ──────────────────────────────────────────────────────────
# (tag, display name, cpu_weight)
INSTRUMENT_TAGS = {
    "Simpler":              ("Simpler",              1.0),
    "Sampler":              ("Sampler",              1.5),
    "MultiSampler":         ("Sampler",              1.5),
    "Operator":             ("Operator",             1.5),
    "Analog":               ("Analog",               2.5),
    "Collision":            ("Collision",            3.0),
    "Tension":              ("Tension",              3.0),
    "Electric":             ("Electric",             2.0),
    "Drift":                ("Drift",                1.5),
    "Meld":                 ("Meld",                 2.0),
    "Wavetable":            ("Wavetable",            2.0),
    "DrumGroupDevice":      ("Drum Rack",            1.5),
    "InstrumentGroupDevice":("Instrument Rack",      0.5),
    "OriginalSimpler":      ("Classic Simpler",      1.0),
    "MxDeviceMidi":         ("Max for Live (MIDI)",  2.0),
    "MxDeviceInstrument":   ("Max for Live (Instr)", 2.0),
}

EFFECT_TAGS = {
    "Reverb":               ("Reverb",               1.0),
    "Redux2":               ("Redux",                0.3),
    "Redux":                ("Redux",                0.3),
    "StereoGain":           ("Utility",              0.1),
    "Eq8":                  ("EQ Eight",             0.3),
    "Compressor2":          ("Compressor",           0.3),
    "GlueCompressor":       ("Glue Compressor",      0.5),
    "AutoFilter":           ("Auto Filter",          0.5),
    "FilterDelay":          ("Filter Delay",         0.7),
    "PingPong":             ("Ping Pong Delay",      0.5),
    "StereoDelay":          ("Delay",                0.5),
    "Echo":                 ("Echo",                 0.8),
    "SpectralResonator":    ("Spectral Resonator",   3.0),  # HEAVY
    "SpectralBlur":         ("Spectral Blur",        3.0),  # HEAVY
    "ConvolutionReverb":    ("Convolution Reverb",   3.5),  # VERY HEAVY
    "Resonator":            ("Resonator",            1.0),
    "FrequencyShifter":     ("Freq Shifter",         0.8),
    "Vocoder":              ("Vocoder",              1.5),
    "Chorus":               ("Chorus",               0.5),
    "Flanger":              ("Flanger",              0.5),
    "Phaser":               ("Phaser",               0.5),
    "Beat":                 ("Beat Repeat",          0.7),
    "Amp":                  ("Amp",                  0.8),
    "Cabinet":              ("Cabinet",              0.5),
    "Overdrive":            ("Overdrive",            0.3),
    "Saturator":            ("Saturator",            0.5),
    "Redux":                ("Redux",                0.3),
    "Vinyl":                ("Vinyl Distortion",     0.3),
    "AutoPan":              ("Auto Pan",             0.3),
    "Tremolo":              ("Tremolo",              0.2),
    "Tuner":                ("Tuner",                0.2),
    "Spectrum":             ("Spectrum",             0.5),
    "Erosion":              ("Erosion",              0.5),
    "Gate":                 ("Gate",                 0.3),
    "Limiter":              ("Limiter",              0.3),
    "MultibandDynamics":    ("Multiband Dynamics",   0.8),
    "AudioEffectGroupDevice":("Effect Rack",         0.3),
    "MxDeviceAudioEffect":  ("Max for Live (FX)",    2.0),
}

PLUGIN_TAGS = {"PluginDevice", "VstPluginInfo", "Vst3PluginInfo", "AuPluginInfo"}


@dataclass
class DeviceInfo:
    name: str
    weight: float
    is_plugin: bool = False
    frozen: bool = False


@dataclass
class TrackInfo:
    kind: str          # MidiTrack, AudioTrack, ReturnTrack, MasterTrack, GroupTrack
    name: str
    frozen: bool
    devices: List[DeviceInfo] = field(default_factory=list)
    samples: List[str] = field(default_factory=list)

    @property
    def cpu_weight(self) -> float:
        base = {"MidiTrack": 1.0, "AudioTrack": 0.5, "ReturnTrack": 1.5,
                "MasterTrack": 0.2, "GroupTrack": 0.2}.get(self.kind, 0.5)
        device_weight = sum(d.weight for d in self.devices)
        total = base + device_weight
        return total * 0.15 if self.frozen else total  # frozen = 85% CPU saving


def _get_name(el: ET.Element) -> str:
    """Get track/device display name from XML element."""
    for tag in ("UserName", "EffectiveName", "Name"):
        n = el.find(f".//{tag}")
        if n is not None:
            v = n.get("Value", "").strip()
            if v:
                return v
    return el.tag.replace("Track", "").replace("Device", "")


def _parse_devices(chain_el: ET.Element) -> List[DeviceInfo]:
    """Extract all instruments and effects from a device chain."""
    devices = []
    if chain_el is None:
        return devices

    for el in chain_el.iter():
        tag = el.tag

        if tag in INSTRUMENT_TAGS:
            display, weight = INSTRUMENT_TAGS[tag]
            devices.append(DeviceInfo(display, weight))

        elif tag in EFFECT_TAGS:
            display, weight = EFFECT_TAGS[tag]
            devices.append(DeviceInfo(display, weight))

        elif tag == "PluginDevice":
            # Try to find plugin name from VstPluginInfo/AuPluginInfo/Vst3PluginInfo
            name = "Unknown Plugin"
            for sub in el.iter():
                if sub.tag in ("PlugName", "ProductName", "Manufacturer"):
                    v = sub.get("Value", "").strip()
                    if v:
                        name = v
                        break
            devices.append(DeviceInfo(name, 2.5, is_plugin=True))

    return devices


def parse_als(path: str) -> dict:
    """Parse a .als file and return structured project info."""
    try:
        with gzip.open(path, "rb") as f:
            xml_data = f.read()
    except (OSError, gzip.BadGzipFile) as e:
        return {"error": f"Could not open file: {e}"}

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}"}

    tracks: List[TrackInfo] = []
    TRACK_TYPES = ["MidiTrack", "AudioTrack", "ReturnTrack", "MasterTrack", "GroupTrack"]

    # Collect all tracks
    for track_type in TRACK_TYPES:
        for track_el in root.iter(track_type):
            name   = _get_name(track_el)
            frozen = track_el.find(".//Freeze") is not None and \
                     track_el.find(".//Freeze").get("Value", "false").lower() == "true"

            # Device chain
            chain_el = track_el.find(".//DeviceChain")
            devices  = _parse_devices(chain_el) if chain_el is not None else []

            # Sample references
            samples = []
            for ref in track_el.iter("FileRef"):
                rel = ref.find("RelativePath")
                name_el = ref.find("Name")
                sample_name = (name_el.get("Value") if name_el is not None else
                               (rel.get("Value") if rel is not None else "unknown"))
                if sample_name:
                    samples.append(sample_name)

            tracks.append(TrackInfo(
                kind=track_type,
                name=name,
                frozen=frozen,
                devices=devices,
                samples=list(set(samples)),
            ))

    # Tempo
    tempo_el = root.find(".//Tempo/Manual")
    tempo = tempo_el.get("Value", "?") if tempo_el is not None else "?"

    # Time signature
    num_el = root.find(".//TimeSignature/TimeSignatures/AutomationEvent/Value")
    # simpler approach
    ts_num = root.find(".//TimeSignature")
    ts_str = "?"
    if ts_num is not None:
        n = ts_num.find(".//Numerator/Manual")
        d = ts_num.find(".//Denominator/Manual")
        if n is not None and d is not None:
            ts_str = f"{n.get('Value', '4')}/{d.get('Value', '4')}"

    # Scenes/clips
    scenes = list(root.iter("Scene"))

    return {
        "tracks":    tracks,
        "tempo":     tempo,
        "time_sig":  ts_str,
        "scene_count": len(scenes),
    }


def complexity_score(tracks: List[TrackInfo]) -> float:
    return sum(t.cpu_weight for t in tracks)


def score_label(score: float):
    if score < 20:  return ("Light",     "green",  "✓")
    if score < 50:  return ("Moderate",  "yellow", "◐")
    if score < 90:  return ("Heavy",     "red",    "⚠")
    return              ("Very Heavy", "bold red","✖")


def print_report(path: str, data: dict):
    filename = os.path.basename(path)
    tracks   = data.get("tracks", [])

    console.print()
    console.rule(f"[bold cyan] {filename} [/]", style="cyan")
    console.print()

    if not tracks:
        console.print("  [dim]No tracks found.[/dim]\n")
        return

    # ── Overview ──────────────────────────────────────────────────────────────
    midi_tracks   = [t for t in tracks if t.kind == "MidiTrack"]
    audio_tracks  = [t for t in tracks if t.kind == "AudioTrack"]
    return_tracks = [t for t in tracks if t.kind == "ReturnTrack"]
    group_tracks  = [t for t in tracks if t.kind == "GroupTrack"]
    frozen_tracks = [t for t in tracks if t.frozen]
    plugin_devs   = [d for t in tracks for d in t.devices if d.is_plugin]
    total_devices = sum(len(t.devices) for t in tracks)
    total_samples = sum(len(t.samples) for t in tracks)

    score = complexity_score(tracks)
    s_label, s_color, s_icon = score_label(score)

    ov = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    ov.add_column("", style="bold cyan", width=24, no_wrap=True)
    ov.add_column("", style="white")
    ov.add_row("Tempo",         f"{data['tempo']} BPM  ·  {data['time_sig']}")
    ov.add_row("Scenes / Clips",f"{data['scene_count']}")
    ov.add_row("MIDI Tracks",   str(len(midi_tracks)))
    ov.add_row("Audio Tracks",  str(len(audio_tracks)))
    ov.add_row("Return Tracks", str(len(return_tracks)))
    ov.add_row("Group Tracks",  str(len(group_tracks)))
    ov.add_row("Frozen Tracks", f"{len(frozen_tracks)}  {'(saving CPU!)' if frozen_tracks else ''}")
    ov.add_row("Total Devices", str(total_devices))
    ov.add_row("External Plugins", f"{len(plugin_devs)}  VST / AU / VST3")
    ov.add_row("Sample References", str(total_samples))
    ov.add_row("CPU Complexity", Text(f"{s_icon}  {s_label}  (score: {score:.0f})", style=s_color))
    console.print(Panel(ov, title="[bold white]Project Overview[/bold white]", border_style="cyan"))

    # ── Track breakdown ───────────────────────────────────────────────────────
    console.print()
    tbl = Table(
        box=box.ROUNDED, border_style="dim", show_header=True,
        header_style="bold dim white", expand=True, padding=(0, 1)
    )
    tbl.add_column("Track",       style="white",     width=26, no_wrap=True)
    tbl.add_column("Type",        style="dim cyan",  width=12, no_wrap=True)
    tbl.add_column("Frozen",      width=8,  justify="center")
    tbl.add_column("Devices",     style="dim white")
    tbl.add_column("CPU Weight",  width=10, justify="right")

    for t in tracks:
        if t.kind == "MasterTrack":
            continue
        frozen_cell = Text("● YES", style="green") if t.frozen else Text("", style="dim")
        devices_str = ", ".join(
            (f"[bold red]{d.name}[/bold red]" if d.is_plugin else d.name)
            for d in t.devices[:6]
        ) or "[dim]—[/dim]"
        if len(t.devices) > 6:
            devices_str += f" +{len(t.devices)-6} more"

        w = t.cpu_weight
        w_color = "green" if w < 5 else ("yellow" if w < 12 else "red")
        weight_cell = Text(f"{w:.1f}", style=w_color)

        tbl.add_row(t.name[:25], t.kind.replace("Track",""), frozen_cell,
                    Text.from_markup(devices_str), weight_cell)

    console.print(tbl)

    # ── Heavy hitters ────────────────────────────────────────────────────────
    heavy = sorted(tracks, key=lambda t: t.cpu_weight, reverse=True)[:5]
    heavy = [t for t in heavy if t.cpu_weight > 2]
    if heavy:
        console.print()
        console.rule("[yellow] Heaviest Tracks [/]", style="yellow")
        for t in heavy:
            _, sc, si = score_label(t.cpu_weight)
            heavy_devs = [d.name for d in t.devices if d.weight > 1.5]
            note = f"  [{sc}]{si} CPU weight {t.cpu_weight:.1f}[/{sc}]"
            if heavy_devs:
                note += f"  ·  heavy devices: {', '.join(heavy_devs)}"
            if t.frozen:
                note += "  [green](frozen — not costing CPU)[/green]"
            console.print(f"  [bold white]{t.name}[/bold white]{note}")
        console.print()

    # ── External plugins list ─────────────────────────────────────────────────
    if plugin_devs:
        console.print()
        console.rule("[yellow] External Plugins Detected [/]", style="yellow")
        plugin_names = sorted(set(d.name for d in plugin_devs))
        for pn in plugin_names:
            count = sum(1 for d in plugin_devs if d.name == pn)
            console.print(f"  [bold yellow]◈[/bold yellow]  {pn}"
                          + (f"  [dim]×{count}[/dim]" if count > 1 else ""))
        console.print()

    # ── Recommendations ───────────────────────────────────────────────────────
    recs = []
    unfrozen_heavy = [t for t in tracks
                      if t.cpu_weight > 8 and not t.frozen and t.kind == "MidiTrack"]
    if unfrozen_heavy:
        recs.append(f"Freeze these heavy instrument tracks: "
                    f"{', '.join(t.name for t in unfrozen_heavy[:4])}")

    heavy_effects = [(t, d) for t in tracks for d in t.devices if d.weight >= 3.0]
    if heavy_effects:
        recs.append("Heavy effects detected (Convolution Reverb, Spectral Resonator): "
                    "bounce return tracks or use lighter alternatives")

    many_plugins = len(plugin_devs)
    if many_plugins > 10:
        recs.append(f"{many_plugins} external plugin instances — disable unused ones "
                    "or bounce stems to audio")

    if len(return_tracks) > 4:
        recs.append(f"{len(return_tracks)} return tracks — freeze any with heavy effects")

    if score > 80 and not frozen_tracks:
        recs.append("Very heavy project with no frozen tracks — "
                    "Freeze everything you're not actively editing")

    if recs:
        console.print()
        console.rule("[bold cyan] Recommendations [/]", style="cyan")
        for i, r in enumerate(recs, 1):
            console.print(f"  [cyan]{i}.[/cyan]  {r}")
        console.print()


def main():
    if len(sys.argv) < 2:
        console.print(
            "\n  [bold cyan]Ableton .als Project Analyzer[/bold cyan]\n\n"
            "  Usage:  python3 als_analyzer.py /path/to/project.als\n"
        )
        sys.exit(1)

    path = sys.argv[1].strip().strip("'\"")

    if not os.path.exists(path):
        console.print(f"\n  [red]File not found:[/red]  {path}\n")
        sys.exit(1)

    if not path.lower().endswith(".als"):
        console.print(f"\n  [yellow]Warning:[/yellow]  Expected a .als file, got: {path}\n")

    console.print(f"\n  [dim]Parsing {os.path.basename(path)} …[/dim]")
    data = parse_als(path)

    if "error" in data:
        console.print(f"\n  [red]Error:[/red]  {data['error']}\n")
        sys.exit(1)

    print_report(path, data)


if __name__ == "__main__":
    main()
