from __future__ import annotations

import subprocess
from pathlib import Path


def _container_name(persona: str) -> str:
    return f"{persona}-agent"


def spawn_agent_container(
    project_root: Path,
    persona: str,
    force_recreate: bool,
    dry_run: bool,
) -> dict[str, str | int | bool]:
    script_path = project_root / "management" / "backend" / "scripts" / "spawn_agent.sh"

    proc = subprocess.run(
        [
            str(script_path),
            str(project_root),
            persona,
            "true" if force_recreate else "false",
            "true" if dry_run else "false",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    return {
        "success": proc.returncode == 0,
        "return_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def terminate_agent_container(persona: str, remove: bool = True) -> dict[str, str | int | bool]:
    container_name = _container_name(persona)

    stop_proc = subprocess.run(
        ["docker", "stop", container_name],
        capture_output=True,
        text=True,
        check=False,
    )

    stop_missing = "No such container" in (stop_proc.stderr or "") or "No such container" in (stop_proc.stdout or "")
    stop_ok = stop_proc.returncode == 0 or stop_missing

    remove_proc = None
    remove_missing = False
    if remove:
        remove_proc = subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            text=True,
            check=False,
        )
        remove_missing = "No such container" in (remove_proc.stderr or "") or "No such container" in (remove_proc.stdout or "")

    return {
        "success": stop_ok and (remove_proc is None or remove_proc.returncode == 0 or remove_missing),
        "return_code": remove_proc.returncode if remove_proc is not None else stop_proc.returncode,
        "stdout": "\n".join(filter(None, [stop_proc.stdout, remove_proc.stdout if remove_proc else ""])),
        "stderr": "\n".join(filter(None, [stop_proc.stderr, remove_proc.stderr if remove_proc else ""])),
        "container_name": container_name,
        "removed": bool(remove),
    }


def restart_agent_container(persona: str) -> dict[str, str | int | bool]:
    container_name = _container_name(persona)

    proc = subprocess.run(
        ["docker", "restart", container_name],
        capture_output=True,
        text=True,
        check=False,
    )

    missing = "No such container" in (proc.stderr or "") or "No such container" in (proc.stdout or "")

    return {
        "success": proc.returncode == 0,
        "return_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "container_name": container_name,
        "exists": not missing,
    }
