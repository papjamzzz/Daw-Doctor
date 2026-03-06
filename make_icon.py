#!/usr/bin/env python3
"""
DAW Doctor — Icon Generator & App Brander

Converts logo.png into a macOS .icns file at all required sizes
and applies it to the DAW Doctor.app bundle.

Usage:
  python3 make_icon.py               # full branding: icon + apply to .app
  python3 make_icon.py --icon-only   # just generate daw_doctor.icns
"""

import sys, subprocess, shutil, plistlib, argparse
from pathlib import Path

# ── Bootstrap Pillow ──────────────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw
except ImportError:
    print("  Installing Pillow …")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "Pillow", "-q",
         "--disable-pip-version-check"],
        check=True
    )
    from PIL import Image, ImageDraw

TOOL_DIR   = Path(__file__).parent
APP_PATH   = Path.home() / "Applications" / "DAW Doctor.app"
ICNS_PATH  = TOOL_DIR / "daw_doctor.icns"
LOGO_PATH  = TOOL_DIR / "logo.png"

# ── Icon renderer ─────────────────────────────────────────────────────────────
C_BG = (15, 23, 42, 255)   # dark navy

def draw_icon(size: int) -> Image.Image:
    """Crop symbol from logo.png, strip white, place on dark navy squircle."""
    src = Image.open(LOGO_PATH).convert("RGBA")
    w, h = src.size

    # Crop to just the top symbol — skip all text (top ~42% of image)
    symbol = src.crop((0, 0, w, int(h * 0.42)))

    # Strip near-white background pixels → transparent
    data = symbol.getdata()
    symbol.putdata([
        (r, g, b, 0) if r > 200 and g > 200 and b > 200 else (r, g, b, a)
        for r, g, b, a in data
    ])

    # Dark navy squircle background
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bg)
    draw.rounded_rectangle(
        [0, 0, size - 1, size - 1],
        radius=int(size * 0.22),
        fill=C_BG
    )

    # Fit symbol into icon with padding, keeping aspect ratio
    sw, sh = symbol.size
    pad = int(size * 0.14)
    avail = size - 2 * pad
    scale = min(avail / sw, avail / sh)
    tw, th = max(1, int(sw * scale)), max(1, int(sh * scale))
    symbol = symbol.resize((tw, th), Image.LANCZOS)

    # Paste centred
    x = (size - tw) // 2
    y = (size - th) // 2
    bg.paste(symbol, (x, y), symbol)

    return bg

# ── .icns builder ─────────────────────────────────────────────────────────────
ICONSET_SIZES = {
    "icon_16x16":       16,
    "icon_16x16@2x":    32,
    "icon_32x32":       32,
    "icon_32x32@2x":    64,
    "icon_128x128":     128,
    "icon_128x128@2x":  256,
    "icon_256x256":     256,
    "icon_256x256@2x":  512,
    "icon_512x512":     512,
    "icon_512x512@2x":  1024,
}

def build_icns(out_path: Path) -> Path:
    iconset = out_path.with_suffix(".iconset")
    iconset.mkdir(exist_ok=True)

    print(f"  Rendering {len(ICONSET_SIZES)} icon sizes …")
    for name, px in ICONSET_SIZES.items():
        draw_icon(px).save(iconset / f"{name}.png")
        print(f"    {px:4d}px  ✓")

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(out_path)],
        check=True, capture_output=True
    )
    shutil.rmtree(iconset)
    print(f"  ✓  Icon saved: {out_path}")
    return out_path

# ── Apply icon to .app ────────────────────────────────────────────────────────
def apply_to_app(icns_path: Path, app_path: Path):
    if not app_path.exists():
        print(f"  ✗  .app not found at {app_path}")
        print(f"     Run ./setup.sh first to create it.")
        return False

    # Replace the icon file
    res_dir = app_path / "Contents" / "Resources"
    shutil.copy2(str(icns_path), str(res_dir / "applet.icns"))

    # Patch Info.plist — set bundle name + display name
    plist_path = app_path / "Contents" / "Info.plist"
    if plist_path.exists():
        with open(plist_path, "rb") as f:
            pl = plistlib.load(f)
        pl["CFBundleName"]        = "DAW Doctor"
        pl["CFBundleDisplayName"] = "DAW Doctor"
        pl["CFBundleVersion"]     = "2.0"
        pl["NSHumanReadableCopyright"] = "DAW Doctor v2.0"
        with open(plist_path, "wb") as f:
            plistlib.dump(pl, f)

    # Touch the .app to force Finder / Dock refresh
    subprocess.run(["touch", str(app_path)], capture_output=True)

    # Clear macOS icon cache and restart Dock
    subprocess.run(
        ["find", str(Path.home() / "Library/Caches"),
         "-name", "com.apple.dock.iconcache", "-delete"],
        capture_output=True
    )
    subprocess.run(["killall", "Dock"], capture_output=True)

    print(f"  ✓  Icon applied to: {app_path}")
    print(f"     Dock restarted — icon should update within a few seconds.")
    return True

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="DAW Doctor — Icon Generator")
    p.add_argument("--icon-only", action="store_true",
                   help="Only generate the .icns file, don't touch the .app")
    p.add_argument("--app", type=str, default=str(APP_PATH),
                   help=f"Path to the .app (default: {APP_PATH})")
    args = p.parse_args()

    print()
    print("  ⚕  DAW Doctor — Icon Generator")
    print("  ─────────────────────────────────")
    print()

    icns = build_icns(ICNS_PATH)

    if not args.icon_only:
        print()
        apply_to_app(icns, Path(args.app))

    print()

if __name__ == "__main__":
    main()
