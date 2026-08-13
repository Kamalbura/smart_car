# Git and Sync Model

## Document Information

| Attribute | Value |
|-----------|-------|
| Document | 10_git_and_sync_model.md |
| Version | 1.0 |
| Last Updated | 2026-02-01 |

---

## Overview

The smart_car project uses Git for version control, with development occurring primarily on a Windows PC and deployment to a Raspberry Pi. This document describes the repository structure, branching model, and synchronization procedures.

---

## Repository Locations

| Location | Path | Purpose |
|----------|------|---------|
| Developer PC | `C:\Users\burak\ptojects\smart_car` | Primary development |
| Raspberry Pi | `/home/pi/smart_car` | Deployment & runtime |
| Remote (GitHub) | `origin` | Central repository |

---

## Repository Structure

```
smart_car/
├── .git/                    # Git repository
├── .gitignore               # Ignore patterns
├── src/                     # Python source code
├── config/                  # Configuration files
├── systemd/                 # Service definitions
├── scripts/                 # Utility scripts
├── tools/                   # Development tools
├── docs/                    # Documentation (legacy)
├── documentation/           # Official documentation
├── mobile_app/              # Android app source
├── models/                  # ML models & wakeword
├── book/                    # LaTeX book source
├── reports/                 # Analysis reports
├── logs/                    # Runtime logs (ignored)
└── requirements*.txt        # Python dependencies
```

---

## .gitignore Configuration

The following patterns are typically ignored:

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
venv*/
.venv/

# Logs
logs/
*.log

# Environment
.env
.env.local

# IDE
.vscode/
.idea/
*.swp

# Cache
.cache/
*.cache

# Models (large files)
models/*.pt
models/*.onnx
!models/*.ppn  # Keep wakeword models

# Build artifacts
build/
dist/
*.egg-info/

# Temporary
tmp/
temp/
```

---

## Branching Model

### Branch Structure

```
main (or master)
 │
 ├── feature/voice-pipeline
 ├── feature/vision-improvements
 ├── fix/uart-timeout
 └── dev/experimental
```

### Branch Conventions

| Branch | Purpose |
|--------|---------|
| `main` | Stable, deployable code |
| `feature/*` | New features |
| `fix/*` | Bug fixes |
| `dev/*` | Experimental changes |

---

## Development Workflow

### Standard Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DEVELOPER PC                                     │
│                                                                             │
│   1. Edit code                                                              │
│   2. Test locally (where possible)                                          │
│   3. Commit changes                                                         │
│   4. Push to origin                                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ git push
                                    ▼
                          ┌─────────────────┐
                          │     GitHub      │
                          │   (origin)      │
                          └────────┬────────┘
                                   │
                                   │ git pull
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            RASPBERRY PI                                     │
│                                                                             │
│   1. Pull changes                                                           │
│   2. Restart services                                                       │
│   3. Test on hardware                                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Commands

**On PC:**
```powershell
# Make changes, then
git add .
git commit -m "feat: add new vision mode"
git push origin main
```

**On Pi:**
```bash
cd /home/pi/smart_car

# Stop services
sudo systemctl stop orchestrator remote-interface uart vision llm tts voice-pipeline display led-ring

# Pull changes
git pull origin main

# Restart services
sudo systemctl start orchestrator remote-interface uart vision llm tts voice-pipeline display led-ring
```

---

## Current Divergence Status

### Observed During Analysis (2026-02-01)

**PC Status:**
```
Changes not staged for commit:
  modified:   src/core/orchestrator.py
  modified:   src/remote/remote_interface.py
  modified:   src/uart/motor_bridge.py
```

**Pi Status:**
```
Changes not staged for commit:
  modified:   src/core/orchestrator.py
  modified:   src/llm/azure_openai_runner.py
  modified:   src/remote/remote_interface.py
  modified:   src/uart/motor_bridge.py
  modified:   src/vision/vision_runner.py
```

### Divergence Analysis

| File | PC Changes | Pi Changes | Conflict Risk |
|------|------------|------------|---------------|
| orchestrator.py | Yes | Yes (+580/-418) | HIGH |
| remote_interface.py | Yes | Yes (+503/-403) | HIGH |
| motor_bridge.py | Yes | Yes (+615/-670) | HIGH |
| azure_openai_runner.py | No | Yes | Medium |
| vision_runner.py | No | Yes | Medium |

### Resolution Strategy

1. **Identify authoritative version** (likely Pi - more recent runtime)
2. **Compare diffs** between PC and Pi versions
3. **Merge manually** or choose one version
4. **Commit and push** from authoritative source
5. **Pull** on other machine

---

## Synchronization Commands

### Check Status (Both Machines)

```bash
git status
git log --oneline -5
git diff --stat
```

### Pull with Stash (Safe)

```bash
# Save local changes
git stash

# Pull remote
git pull origin main

# Reapply local changes
git stash pop

# Resolve conflicts if any
```

### Force Sync from Remote

**Warning: Overwrites local changes**

```bash
# Discard all local changes
git fetch origin
git reset --hard origin/main
```

### Force Push Local to Remote

**Warning: Overwrites remote**

```bash
git add .
git commit -m "sync: local changes"
git push --force origin main
```

---

## Sync Script

### deploy.sh (On Pi)

```bash
#!/bin/bash
set -e

echo "=== Stopping services ==="
sudo systemctl stop orchestrator remote-interface uart vision llm tts voice-pipeline display led-ring

echo "=== Pulling changes ==="
cd /home/pi/smart_car
git pull origin main

echo "=== Updating dependencies ==="
pip install -r requirements.txt

echo "=== Starting services ==="
sudo systemctl start orchestrator remote-interface uart vision llm tts voice-pipeline display led-ring

echo "=== Done ==="
sudo systemctl status orchestrator --no-pager
```

### push.ps1 (On PC)

```powershell
# PowerShell script for PC
$ErrorActionPreference = "Stop"

Write-Host "=== Checking status ===" -ForegroundColor Green
git status

$message = Read-Host "Commit message"
if ([string]::IsNullOrWhiteSpace($message)) {
    Write-Host "No commit message, aborting" -ForegroundColor Red
    exit 1
}

Write-Host "=== Committing ===" -ForegroundColor Green
git add .
git commit -m $message

Write-Host "=== Pushing ===" -ForegroundColor Green
git push origin main

Write-Host "=== Done ===" -ForegroundColor Green
```

---

## Configuration File Sync

### Files That Should Sync

| File | Sync Required |
|------|---------------|
| `config/system.yaml` | Yes |
| `config/logging.yaml` | Yes |
| `systemd/*.service` | Yes |
| `requirements*.txt` | Yes |

### Files That Should NOT Sync

| File | Reason |
|------|--------|
| `.env` | Contains secrets |
| `logs/*` | Runtime data |
| `models/*.pt` | Large binaries |
| `venv*/` | Platform-specific |

---

## Model File Handling

### Large Files

Model files (YOLO weights, etc.) are typically:
- Excluded from Git via `.gitignore`
- Downloaded separately
- Or stored in Git LFS

### Download Models (On Pi)

```bash
cd /home/pi/smart_car/models

# YOLO model
wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt

# Or from project storage
scp user@server:/path/to/yolov8n.pt .
```

### Wakeword Models

Porcupine `.ppn` files are small and licensed per-device. These ARE tracked in Git:

```
models/wakeword/
└── hey-robo_en_raspberry-pi_v3_0_0.ppn
```

---

## Conflict Resolution

### Common Conflicts

1. **Same file edited on both machines**
2. **Different features developed in parallel**
3. **Configuration divergence**

### Resolution Steps

```bash
# 1. Fetch latest
git fetch origin

# 2. See differences
git diff HEAD origin/main

# 3. Merge (creates conflict markers)
git merge origin/main

# 4. Edit conflicted files
# Look for <<<<<<< HEAD ... ======= ... >>>>>>> origin/main

# 5. Mark resolved
git add <resolved-files>

# 6. Complete merge
git commit -m "merge: resolved conflicts"
```

### Using VSCode for Conflicts

1. Open conflicted file in VSCode
2. Use "Accept Current/Incoming/Both" buttons
3. Save file
4. Stage and commit

---

## Best Practices

### For Development

1. **Pull before editing**: Always `git pull` before starting work
2. **Commit frequently**: Small, focused commits
3. **Write clear messages**: `feat:`, `fix:`, `docs:` prefixes
4. **Test before pushing**: Verify changes work

### For Deployment

1. **Stop services before pull**: Avoid runtime errors
2. **Check service status after**: Verify restart success
3. **Keep logs**: Don't clear logs right after deploy
4. **Have rollback plan**: Know how to revert

### For Sync

1. **One authoritative source**: Choose PC or Pi as primary
2. **Regular sync**: Don't let divergence grow
3. **Backup before force operations**: Save work first
4. **Document changes**: Track what's on each machine

---

## SSH Access for Git

### From PC to Pi

```powershell
# Configure SSH
ssh-keygen -t ed25519
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh pi@100.111.13.60 "cat >> ~/.ssh/authorized_keys"

# Test
ssh pi@100.111.13.60 "cd /home/pi/smart_car && git status"
```

### Remote Commands

```powershell
# Pull on Pi from PC
ssh pi@100.111.13.60 "cd /home/pi/smart_car && git pull"

# Restart services on Pi from PC
ssh pi@100.111.13.60 "sudo systemctl restart orchestrator"
```

---

## GitHub Actions (Optional)

### Auto-Deploy on Push

```yaml
# .github/workflows/deploy.yml
name: Deploy to Pi

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Pi
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PI_HOST }}
          username: pi
          key: ${{ secrets.PI_SSH_KEY }}
          script: |
            cd /home/pi/smart_car
            git pull origin main
            sudo systemctl restart orchestrator
```

---

## References

| Document | Purpose |
|----------|---------|
| [09_deployment_and_operations.md](09_deployment_and_operations.md) | Deployment procedures |
| [12_known_unknowns.md](12_known_unknowns.md) | Unresolved issues |
