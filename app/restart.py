"""SERVICE_RESTART: SSH to the VPS and restart the crashed Docker service.

The SSH private key is base64-decoded from settings into a temp file (mode 600)
for the duration of the call and removed afterwards. The key is never logged.
"""

from __future__ import annotations

import base64
import logging
import os
import subprocess
import tempfile

from app.config import get_settings

logger = logging.getLogger("guardian.restart")


def run_restart(incident: dict, service: str = "app") -> tuple[str, str]:
    """Return (remediation_status, remediation_detail)."""
    from app.remediation import poll_health  # local import avoids cycle

    settings = get_settings()

    if not settings.remediation_enabled:
        detail = (
            f"[dry-run] Would SSH to the VPS and run 'docker compose restart {service}' "
            f"(REMEDIATION_ENABLED is false)."
        )
        healthy = poll_health()
        return ("RECOVERED" if healthy else "FAILED_RECOVERY"), detail

    if not (settings.vps_ssh_key_b64 and settings.vps_host):
        return "FAILED_RECOVERY", "Restart aborted: SSH credentials (VPS_SSH_KEY_B64/VPS_HOST) not configured."

    try:
        key_bytes = base64.b64decode(settings.vps_ssh_key_b64)
    except Exception:  # noqa: BLE001
        return "FAILED_RECOVERY", "Restart aborted: VPS_SSH_KEY_B64 is not valid base64."

    # OpenSSH rejects a private key without a trailing newline ("error in libcrypto").
    if not key_bytes.endswith(b"\n"):
        key_bytes += b"\n"

    fd, key_path = tempfile.mkstemp(prefix="guardian_key_")
    try:
        os.write(fd, key_bytes)
        os.close(fd)
        os.chmod(key_path, 0o600)

        target = f"{settings.vps_user}@{settings.vps_host}"
        remote_cmd = f"cd {settings.project_dir} && docker compose restart {service}"
        ssh_cmd = [
            "ssh",
            "-i", key_path,
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=15",
            target,
            remote_cmd,
        ]
        proc = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "FAILED_RECOVERY", f"Restart aborted: SSH to {settings.vps_host} timed out."
    except Exception as exc:  # noqa: BLE001
        return "FAILED_RECOVERY", f"Restart aborted: {exc.__class__.__name__}."
    finally:
        try:
            os.remove(key_path)
        except OSError:
            pass

    # docker compose restart output never contains the key; safe to surface.
    out = (proc.stdout or "").strip()[-300:]
    err = (proc.stderr or "").strip()[-300:]
    if proc.returncode != 0:
        logger.warning("SSH restart of '%s' failed (rc=%s)", service, proc.returncode)
        return "FAILED_RECOVERY", f"SSH restart of '{service}' failed (rc={proc.returncode}): {err}"

    logger.info("SSH restart of '%s' succeeded; confirming recovery", service)
    healthy = poll_health()
    detail = f"Restarted '{service}' on the VPS via SSH. {out or err}".strip()
    return ("RECOVERED" if healthy else "FAILED_RECOVERY"), detail
