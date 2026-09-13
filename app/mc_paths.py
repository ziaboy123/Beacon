"""Helpers for locating and reading the Paper server's on-disk files."""

import os
import subprocess

from .config import settings


def read_server_properties() -> dict[str, str]:
    path = os.path.join(settings.mc_server_dir, "server.properties")
    props: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                props[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return props


def get_world_dir() -> str:
    """The world save directory, named by server.properties' level-name
    (defaults to "world" if the file can't be read) rather than assumed.
    """
    props = read_server_properties()
    level_name = props.get("level-name", "world")
    return os.path.join(settings.mc_server_dir, level_name)


def get_systemd_active_since(unit: str) -> str | None:
    try:
        result = subprocess.run(
            ["systemctl", "show", unit, "--property=ActiveEnterTimestamp", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        value = result.stdout.strip()
        return value or None
    except Exception:
        return None


def get_disk_usage(paths: list[str]) -> list[dict[str, str]]:
    results = []
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            result = subprocess.run(["du", "-sh", path], capture_output=True, text=True, timeout=15)
            size = result.stdout.split()[0] if result.stdout.strip() else "?"
        except Exception:
            size = "?"
        results.append({"path": path, "size": size})
    return results
