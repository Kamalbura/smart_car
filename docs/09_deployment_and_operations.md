# Deployment and Operations

## Document Information

| Attribute | Value |
|-----------|-------|
| Document | 09_deployment_and_operations.md |
| Version | 1.0 |
| Last Updated | 2026-02-01 |

---

## Overview

This document covers deployment procedures, operational commands, and maintenance tasks for the smart_car system running on Raspberry Pi.

---

## Prerequisites

### Hardware Requirements

| Component | Specification |
|-----------|---------------|
| Raspberry Pi | Model 4B, 4GB+ RAM |
| Storage | 32GB+ SD card |
| Camera | Pi Camera Module v2 |
| Microphone | USB microphone |
| Speaker | USB/3.5mm speaker |
| Network | WiFi or Ethernet |

### Software Requirements

| Requirement | Version |
|-------------|---------|
| Raspberry Pi OS | Bookworm (64-bit) |
| Python | 3.11+ |
| Git | 2.x |
| systemd | 247+ |

---

## Initial Setup

### 1. Clone Repository

```bash
cd /home/pi
git clone https://github.com/your-org/smart_car.git
cd smart_car
```

### 2. Create Virtual Environments

```bash
# Run the setup script
./setup_envs.sh
```

This creates:
- `venv-stte/` - Voice pipeline (STT, wakeword)
- `venv-llme/` - LLM runner
- `venv-ttse/` - TTS runner
- `venv-visn-py313/` - Vision runner

### 3. Install Dependencies

```bash
# Main environment
pip install -r requirements.txt

# Per-service environments
venv-stte/bin/pip install -r requirements-stte.txt
venv-llme/bin/pip install -r requirements-llme.txt
venv-ttse/bin/pip install -r requirements-ttse.txt
venv-visn-py313/bin/pip install -r requirements-visn.txt
```

### 4. Configure Environment Variables

```bash
# Create environment file
cat > /home/pi/smart_car/.env << 'EOF'
AZURE_SPEECH_KEY=your-speech-key
AZURE_SPEECH_REGION=eastus
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-openai-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o
PICOVOICE_ACCESS_KEY=your-picovoice-key
EOF

chmod 600 /home/pi/smart_car/.env
```

### 5. Install systemd Services

```bash
# Copy service files
sudo cp systemd/*.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable orchestrator remote-interface uart vision llm tts voice-pipeline display led-ring
```

### 6. Configure System

```bash
# Edit configuration
nano config/system.yaml
```

### 7. Start Services

```bash
# Start all services
sudo systemctl start orchestrator
sudo systemctl start remote-interface
sudo systemctl start uart
sudo systemctl start vision
sudo systemctl start llm
sudo systemctl start tts
sudo systemctl start voice-pipeline
sudo systemctl start display
sudo systemctl start led-ring
```

---

## Boot Sequence

### Service Start Order

```
1. orchestrator          (binds ZMQ ports)
    │
    ├── 2. remote-interface
    ├── 3. uart
    ├── 4. vision
    ├── 5. llm
    ├── 6. tts
    ├── 7. voice-pipeline
    ├── 8. display
    └── 9. led-ring
```

### Startup Timeline

| Time | Event |
|------|-------|
| T+0s | Pi boots |
| T+30s | Network available |
| T+35s | orchestrator starts, binds 6010/6011 |
| T+36s | Other services start connecting |
| T+40s | All services connected |
| T+45s | System ready (LED ring blue) |

### Startup Verification

```bash
# Check all services
sudo systemctl status orchestrator remote-interface uart vision llm tts voice-pipeline display led-ring

# Quick status
sudo systemctl is-active orchestrator remote-interface uart vision llm tts voice-pipeline display led-ring
```

---

## Service Management

### Start/Stop/Restart

```bash
# Individual service
sudo systemctl start orchestrator
sudo systemctl stop orchestrator
sudo systemctl restart orchestrator

# All services
sudo systemctl restart orchestrator remote-interface uart vision llm tts voice-pipeline display led-ring
```

### View Logs

```bash
# Real-time logs
sudo journalctl -u orchestrator -f

# Last 100 lines
sudo journalctl -u orchestrator -n 100

# All service logs
sudo journalctl -u orchestrator -u remote-interface -u uart -u vision -u llm -u tts -u voice-pipeline -f
```

### Check Status

```bash
# Detailed status
sudo systemctl status orchestrator

# Simple status check
sudo systemctl is-active orchestrator
```

---

## Health Checks

### HTTP Health Check

```bash
curl http://localhost:8770/health
# Expected: {"status": "ok"}
```

### Port Verification

```bash
# Check listening ports
ss -tlnp | grep -E '6010|6011|8770'

# Expected output:
# LISTEN  0  128  127.0.0.1:6010  *:*  users:(("python",pid=XXX))
# LISTEN  0  128  127.0.0.1:6011  *:*  users:(("python",pid=XXX))
# LISTEN  0  128  0.0.0.0:8770    *:*  users:(("python",pid=XXX))
```

### Process Verification

```bash
# List Python processes
ps aux | grep python

# Should show:
# orchestrator
# remote_interface
# motor_bridge
# vision_runner
# azure_openai_runner
# azure_tts_runner
# voice_service
# display_runner
# led_ring_runner
```

### Full Telemetry

```bash
curl http://localhost:8770/status | jq .
```

---

## Log Management

### Log Locations

| Log | Location |
|-----|----------|
| orchestrator | `/home/pi/smart_car/logs/orchestrator.log` |
| remote-interface | `/home/pi/smart_car/logs/remote-interface.log` |
| uart | `/home/pi/smart_car/logs/uart.log` |
| vision | `/home/pi/smart_car/logs/vision.log` |
| llm | `/home/pi/smart_car/logs/llm.log` |
| tts | `/home/pi/smart_car/logs/tts.log` |
| voice-pipeline | `/home/pi/smart_car/logs/voice-pipeline.log` |
| display | `/home/pi/smart_car/logs/display.log` |
| led-ring | `/home/pi/smart_car/logs/led-ring.log` |
| systemd | `/var/log/syslog` or `journalctl` |

### Log Rotation

Logs are configured with:
- Max size: 10 MB
- Backup count: 5

```yaml
# config/system.yaml
logging:
  max_bytes: 10485760
  backup_count: 5
```

### View Logs

```bash
# File logs
tail -f /home/pi/smart_car/logs/orchestrator.log

# Systemd journal
journalctl -u orchestrator -f

# All services combined
tail -f /home/pi/smart_car/logs/*.log
```

### Clear Logs

```bash
# Truncate all logs
for f in /home/pi/smart_car/logs/*.log; do > "$f"; done

# Clear journal (use with caution)
sudo journalctl --vacuum-time=1d
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check status for error
sudo systemctl status orchestrator

# Check journal for details
journalctl -u orchestrator -n 50 --no-pager

# Common issues:
# - Port already in use
# - Missing environment variables
# - Permission denied
# - Python module not found
```

### Connection Refused

```bash
# Is service running?
sudo systemctl is-active orchestrator

# Is port bound?
ss -tlnp | grep 6010

# Try restarting
sudo systemctl restart orchestrator
```

### UART Issues

```bash
# Check if ESP32 connected
ls -la /dev/ttyUSB*

# Check permissions
ls -la /dev/ttyUSB0
# Should be: crw-rw---- 1 root dialout

# Add user to dialout group
sudo usermod -aG dialout pi
# Then logout/login

# Test serial
screen /dev/ttyUSB0 115200
# Type STATUS and press Enter
# Should see DATA: response
# Exit: Ctrl+A then K
```

### Vision Issues

```bash
# Check camera
vcgencmd get_camera
# Expected: supported=1 detected=1

# Test camera
libcamera-still -o test.jpg

# Check vision venv
/home/pi/smart_car/venv-visn-py313/bin/python -c "import cv2; print(cv2.__version__)"
```

### Audio Issues

```bash
# List audio devices
arecord -l
aplay -l

# Test microphone
arecord -d 5 test.wav
aplay test.wav

# Check ALSA config
cat ~/.asoundrc
```

### Memory Issues

```bash
# Check memory
free -h

# Check swap
swapon -s

# Increase swap if needed
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Set CONF_SWAPSIZE=2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

---

## Network Configuration

### Tailscale VPN

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Start Tailscale
sudo tailscale up

# Check IP
tailscale ip -4
# Example: 100.111.13.60
```

### Firewall Rules

```bash
# Allow HTTP
sudo ufw allow 8770/tcp

# Check status
sudo ufw status
```

### Static IP (Optional)

```bash
# Edit dhcpcd.conf
sudo nano /etc/dhcpcd.conf

# Add:
interface wlan0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=8.8.8.8
```

---

## Updates

### Code Update

```bash
cd /home/pi/smart_car

# Stop services
sudo systemctl stop orchestrator remote-interface uart vision llm tts voice-pipeline display led-ring

# Pull updates
git pull origin main

# Update dependencies (if needed)
pip install -r requirements.txt

# Restart services
sudo systemctl start orchestrator remote-interface uart vision llm tts voice-pipeline display led-ring
```

### System Update

```bash
sudo apt update
sudo apt upgrade -y

# Reboot if kernel updated
sudo reboot
```

---

## Backup

### Configuration Backup

```bash
# Backup config and models
tar -czvf smart_car_backup.tar.gz \
  config/ \
  models/ \
  .env \
  systemd/
```

### Full Backup

```bash
# Backup entire project
tar -czvf smart_car_full_backup.tar.gz \
  --exclude='logs/*' \
  --exclude='*.pyc' \
  --exclude='__pycache__' \
  --exclude='venv*' \
  /home/pi/smart_car/
```

### Restore

```bash
cd /home/pi
tar -xzvf smart_car_backup.tar.gz
```

---

## Monitoring

### Resource Usage

```bash
# CPU and memory
htop

# Disk usage
df -h

# Temperature
vcgencmd measure_temp
```

### Service Watchdog

The systemd services are configured with:
- `Restart=always`
- `RestartSec=3`

This means services automatically restart on failure.

### External Monitoring

```bash
# Simple health check script
cat > /home/pi/check_health.sh << 'EOF'
#!/bin/bash
if curl -s http://localhost:8770/health | grep -q "ok"; then
    echo "OK"
    exit 0
else
    echo "FAIL"
    exit 1
fi
EOF

chmod +x /home/pi/check_health.sh
```

---

## Shutdown Procedures

### Graceful Shutdown

```bash
# Stop services first
sudo systemctl stop orchestrator remote-interface uart vision llm tts voice-pipeline display led-ring

# Then shutdown
sudo shutdown -h now
```

### Emergency Stop

If robot is moving unexpectedly:
1. Disconnect battery (physical)
2. Or: `echo "STOP" > /dev/ttyUSB0`
3. Or: `curl -X POST http://localhost:8770/intent -d '{"intent":"stop"}'`

---

## Security Notes

### Sensitive Files

| File | Protection |
|------|------------|
| `.env` | chmod 600 |
| `config/system.yaml` | Contains no secrets |
| `models/wakeword/*.ppn` | Licensed file |

### Network Exposure

| Port | Exposure | Risk |
|------|----------|------|
| 6010/6011 | localhost only | Low |
| 8770 | 0.0.0.0 | Medium (use Tailscale) |
| 22 (SSH) | Network | Secure with keys |

### Recommendations

1. Use Tailscale for remote access
2. Disable password SSH, use keys only
3. Keep `.env` file permissions restricted
4. Don't expose port 8770 to public internet

---

## References

| Document | Purpose |
|----------|---------|
| [05_services_reference.md](05_services_reference.md) | Service details |
| [06_configuration_reference.md](06_configuration_reference.md) | Configuration |
| [10_git_and_sync_model.md](10_git_and_sync_model.md) | Code sync |
