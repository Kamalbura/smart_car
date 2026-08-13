---
name: audit_system_logs
description: Forensic analysis of what went wrong.
---

# Audit System Logs

The detective work.

## When to use
- Post-boot check.
- After a crash.
- Periodic health check.

## Step-by-Step Instructions
1. **Target Logs**: `logs/setup.log`, journalctl, `reports/*.log`.
2. **Scan Keywords**: "Error", "Exception", "Traceback", "Failed", "Time-out".
3. **Correlate**: Match timestamps across different log files (e.g., did Vision fail same time as Audio?).

## Verification Checklist
- [ ] Root cause identified for any "Error".
- [ ] "Warning" noise level is acceptable.

## Rules & Constraints
- Timestamps are the source of truth.
- Don't ignore "Warnings" involving memory or temperature.
