---
name: manage_processes
description: Start, stop, and restart systemd services and check their status.
---

# Manage System Processes

This skill allows the Orchestrator to control the lifecycle of the smart_car systemd services.

## When to use
- Use when initializing the system to ensure core services are running.
- Use when a service is reported as failed or stuck.
- Use to restart a subsystem (e.g., `systemctl restart voice-pipeline`) after a configuration change.

## Step-by-Step Instructions
1. **Identify the Service**: Determine the exact unit name (e.g., `orchestrator.service`, `vision.service`).
2. **Check Status First**:
   ```bash
   systemctl status <service_name> --no-pager
   ```
3. **Perform Action**:
   - To Start: `sudo systemctl start <service_name>`
   - To Stop: `sudo systemctl stop <service_name>`
   - To Restart: `sudo systemctl restart <service_name>`
4. **Verify**:
   - Run `systemctl is-active <service_name>` to confirm the new state.
   - Check logs with `journalctl -u <service_name> -n 20 --no-pager` for immediate errors.

## Verification Checklist
- [ ] Command returned exit code 0.
- [ ] Status command confirms the desired state (active/inactive).
- [ ] Logs show no immediate crash loop.

## Rules & Constraints
- ALWAYS use `sudo` for systemctl control commands.
- NEVER restart `orchestrator.service` unless explicitly instructed (it might kill you).
- Only touch services in the `systemd/` folder scope.
