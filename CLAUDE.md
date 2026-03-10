# DAW Doctor — Project Re-Entry File
*Claude: read this before touching anything.*

---

## What This Is
An Ableton Live diagnostics tool for Mac.
Analyzes .als project files, monitors system health, helps users troubleshoot DAW problems.
Packaged as a Mac .app with a launcher.

## Re-Entry Phrase
> "Re-entry: DAW Doctor"

## Current Status — ✅ Built, needs GitHub
- Diagnostics engine: `diagnose.py`
- ALS file analyzer: `als_analyzer.py`
- System monitor: `monitor.py`
- Installer: `install.sh`, `setup.sh`
- Launcher: `launch.command`
- Logo: `logo.png` (+ high-res versions in ~/Downloads)
- Icon: `daw_doctor.icns`
- Packaged: `Ableton-Diagnostics-v2.0.dmg`
- GitHub: **not yet set up**

## File Structure
```
ableton-diagnostics/
├── diagnose.py         ← Main diagnostics runner
├── als_analyzer.py     ← Ableton .als project file parser
├── monitor.py          ← System/DAW health monitor
├── install.sh          ← User installer script
├── setup.sh            ← Dev setup script
├── launch.command      ← Mac double-click launcher
├── run.sh              ← Run script
├── package.sh          ← Build/package script
├── make_icon.py        ← Icon generator
├── requirements.txt
├── README.md
├── logo.png            ← App logo
└── dist-package/       ← Built distribution
```

## What's Next (pick up here)
- [ ] Create GitHub repo (papjamzzz/daw-doctor)
- [ ] First commit and push
- [ ] Update README with real description
- [ ] Review logo assets — high-res versions in ~/Downloads

## How to Run
```bash
cd ~/ableton-diagnostics
# double-click launch.command OR:
bash run.sh
```

## Pushing Changes to GitHub (once repo is created)
```bash
cd ~/ableton-diagnostics
git add .
git commit -m "describe what changed"
git push origin main
# Username: papjamzzz
# Password: mac-push token (saved in Notes)
```

---
*Last updated: 2026-03-10*
